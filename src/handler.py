"""消息过滤与处理：query/response 解耦架构

发送端 (send_message)：收到飞书消息后立即 query 推送给 Claude，不等响应。
接收端 (session_reader)：per-session 后台 reader task，持续读取 response 并回复飞书。
两者通过 ClientPool 的 per-session FIFO 对齐消息 → 回复映射。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from claude_agent_sdk.types import AssistantMessage, ResultMessage, TextBlock

import src.permissions as permissions
from src.config import OWNER_ID, BOT_NAME, log_debug, log_error
from src.lark import add_reaction, remove_reaction, reply_message, resolve_rich_content, resolve_user_name, resolve_chat_name
from src.pool import ClientPool

if TYPE_CHECKING:
    from src.metrics import MetricsCollector

BOT_MENTION = f"@{BOT_NAME}"


def compute_session_id(event: dict) -> str:
    """根据事件计算 session ID：P2P 按用户，群聊按群+用户"""
    chat_type = event.get("chat_type", "p2p")
    sender_id = event.get("sender_id", "")
    chat_id = event.get("chat_id", "unknown")
    if chat_type == "p2p":
        return f"p2p_{sender_id}"
    return f"group_{chat_id}_{sender_id}"


def should_respond(event: dict) -> bool:
    """判断是否应该响应这条消息"""
    if event.get("sender_type") == "bot":
        return False

    chat_type = event.get("chat_type", "")
    content = event.get("content", "")

    if chat_type == "p2p":
        return True

    if chat_type == "group":
        if BOT_MENTION in content:
            return True

    return False


def _ensure_display_names(pool: ClientPool, event: dict, session_id: str) -> None:
    """首次遇到新 session 时，解析 sender_name 和 chat_name 并存入 store"""
    if not pool._store:
        return
    existing = pool._store.load_all().get(session_id, {})
    if existing.get("sender_name"):
        return  # 已有名字，跳过

    meta: dict = {}
    sender_id = event.get("sender_id", "")
    if sender_id:
        name = resolve_user_name(sender_id)
        if name:
            meta["sender_name"] = name

    chat_type = event.get("chat_type", "")
    chat_id = event.get("chat_id", "")
    if chat_type == "group" and chat_id:
        chat_name = resolve_chat_name(chat_id)
        if chat_name:
            meta["chat_name"] = chat_name

    if meta:
        pool._store.save(session_id, meta)


async def send_message(
    pool: ClientPool, event: dict, *, metrics: MetricsCollector | None = None
):
    """发送端：立即将消息推送给 Claude，不等响应。

    处理 /clear 和 /interrupt 特殊指令。
    普通消息和 slash commands 直接 query 推送，由 session_reader 异步处理响应。
    """
    content = event.get("content", "").strip()
    message_id = event.get("message_id", "")
    sender_id = event.get("sender_id", "")
    chat_type = event.get("chat_type", "p2p")

    # 富消息解析：merge_forward / image / file 等非纯文本类型
    rich = resolve_rich_content(event)
    if rich is not None:
        content = rich

    if not content or not message_id:
        return

    content = content.replace(BOT_MENTION, "").strip()
    session_id = compute_session_id(event)

    # /clear 自行处理（Claude Code 的 /clear 会被权限拦截）
    if content.strip().lower() == "/clear":
        removed = await pool.remove(session_id)
        text = "已清除当前会话。下次发消息将开始新对话。" if removed else "当前没有活跃会话。"
        reply_message(message_id, text)
        return

    # /interrupt 中断当前正在执行的任务
    if content.strip().lower() == "/interrupt":
        client = pool.get_client(session_id)
        if client:
            try:
                await client.interrupt()
                reply_message(message_id, "已中断当前任务。")
            except Exception as e:
                log_error(f"interrupt {session_id} 失败: {e}")
                reply_message(message_id, f"中断失败：{e}")
        else:
            reply_message(message_id, "当前没有活跃任务。")
        return

    permissions.set_sender(sender_id)

    # / 开头的消息直接发给 Claude Code（内置 slash command 如 /compact /context /model）
    # 普通消息加上发送者上下文
    if content.startswith("/"):
        prompt = content
    else:
        sender_label = "所有者" if sender_id == OWNER_ID else "同事"
        prompt = f"[{sender_label}] 在{'群聊' if chat_type == 'group' else '私聊'}中说：{content}"

    # 首次遇到新 session 时解析并存储 sender_name / chat_name
    _ensure_display_names(pool, event, session_id)

    try:
        client = await pool.get(session_id)

        # query 仅写 stdin，不阻塞
        claude_sid = pool.get_claude_session_id(session_id)
        await client.query(prompt, session_id=claude_sid)

        # 入队 FIFO，reader task 据此匹配 response → 飞书回复
        pool.enqueue_message(session_id, message_id, content)
        log_debug(f"[{session_id}] query 已发送: {content[:50]}")

    except Exception as e:
        log_error(f"[{session_id}] send_message 失败: {e}")
        reply_message(message_id, "抱歉，发送消息时出了点问题。")
        if metrics:
            metrics.record_message(session_id, content, False, "")


async def session_reader(
    session_id: str, pool: ClientPool, *, metrics: MetricsCollector | None = None
):
    """接收端：per-session 后台 reader，持续从 Claude 读取响应并回复飞书。

    每个 ResultMessage dequeue FIFO 队头一条消息，回复到该消息。
    Claude 可能合并多条 query 到一个 turn，此时回复内容覆盖多个问题，
    但 dequeue 仍只弹一条——后续 turn 会处理剩余消息。
    """
    while True:
        client = pool.get_client(session_id)
        if not client:
            log_debug(f"[{session_id}] reader: client 不存在，退出")
            return

        reply_text = ""
        reaction_id = None
        current_msg = None
        success = True
        claude_session_saved = False

        try:
            async for msg in client.receive_response():
                # 从 FIFO 队头获取当前处理的飞书消息
                if current_msg is None:
                    current_msg = pool.peek_pending(session_id)

                if isinstance(msg, AssistantMessage):
                    if not claude_session_saved and msg.session_id:
                        log_debug(f"[{session_id}] claude session: {msg.session_id}")
                        pool.save_claude_session_id(session_id, msg.session_id)
                        claude_session_saved = True
                    if reaction_id is None and current_msg:
                        reaction_id = add_reaction(current_msg["message_id"])
                    for block in msg.content:
                        if isinstance(block, TextBlock):
                            reply_text += block.text

                elif isinstance(msg, ResultMessage):
                    if not claude_session_saved and msg.session_id:
                        log_debug(f"[{session_id}] claude session: {msg.session_id}")
                        pool.save_claude_session_id(session_id, msg.session_id)
                    if msg.is_error and not reply_text:
                        reply_text = "抱歉，处理时出了点问题。"
                        success = False

                    # dequeue 一条，回复到该消息
                    if current_msg:
                        mid = current_msg["message_id"]
                        if reaction_id:
                            remove_reaction(mid, reaction_id)
                        if reply_text.strip():
                            reply_message(mid, reply_text.strip())
                        if metrics:
                            metrics.record_message(session_id, current_msg.get("content", ""), success, reply_text[:50])
                        pool.dequeue_message(session_id)

                    # 重置状态，准备处理下一条
                    reply_text = ""
                    reaction_id = None
                    current_msg = None
                    success = True
                    claude_session_saved = False

        except Exception as e:
            log_error(f"[{session_id}] reader 异常: {e}")
            if reaction_id and current_msg:
                remove_reaction(current_msg["message_id"], reaction_id)
            if current_msg and metrics:
                metrics.record_message(session_id, current_msg.get("content", ""), False, "")
                pool.dequeue_message(session_id)
