"""消息过滤与处理：query/response 解耦架构

发送端 (send_message)：收到飞书消息后立即 query 推送给 Claude，不等响应。
接收端 (session_reader)：per-session 后台 reader task，持续读取 response 并回复飞书。
两者通过 ClientPool 的 per-session FIFO 对齐消息 → 回复映射。
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from claude_agent_sdk.types import AssistantMessage, ResultMessage, TextBlock

import src.permissions as permissions
from src.config import OWNER_ID, BOT_NAME, log_debug, log_error
from src.lark import add_reaction, remove_reaction, reply_message, send_to_target, resolve_user_name, resolve_chat_name
from src.pool import ClientPool

if TYPE_CHECKING:
    from src.metrics import MetricsCollector

BOT_MENTION = f"@{BOT_NAME}"


def _format_with_suffix(text: str, suffix: str | None) -> str:
    """给回复文本附加 suffix 前缀（共用，reply 分支和 echo 分支都调它）。

    有 suffix → 返回 "来自 {suffix} 的回复：\n{text}"
    无 suffix → 原样返回
    """
    if suffix:
        return f"来自 {suffix} 的回复：\n{text}"
    return text


def _is_internal_message(message_id: str) -> bool:
    """判断 message_id 是否为控制平面虚构 ID（不对应真实飞书消息）。

    HTTP 控制平面端点（POST /sessions/{owner_id}/create，以及后续的 /message）
    会构造虚拟事件，其 message_id 形如 "internal-<uuid>"。session_reader
    必须跳过所有针对此类 message_id 的 lark-cli 副作用（add_reaction /
    remove_reaction / reply_message）——否则每条 Claude 响应都会对不存在的
    message_id 触发 2-3 次 lark-cli subprocess 失败，日志污染 + 运维噪音。

    核心状态机（dequeue_message / set_processing / save_claude_session_id /
    metrics.record_message）仍照常推进——只跳过用户侧可见的 lark 反馈。
    """
    return isinstance(message_id, str) and message_id.startswith("internal-")


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


def _build_prompt(pool: ClientPool, event: dict, session_id: str, content: str) -> str:
    """构造带发送者上下文的 prompt，包含名字和 ID 供后续 API 交互使用。

    格式示例：
      [所有者·郭凯南 (ou_xxx)] 在私聊中说：你好
      [同事·张三 (ou_yyy)] 在「CMS 需求跟进群」(oc_zzz) 中说：帮我查一下
    """
    sender_id = event.get("sender_id", "")
    chat_type = event.get("chat_type", "p2p")
    chat_id = event.get("chat_id", "")

    # 角色 + 名字
    role = "所有者" if sender_id == OWNER_ID else "同事"
    sender_name = ""
    chat_name = ""
    if pool._store:
        meta = pool._store.load_all().get(session_id, {})
        sender_name = meta.get("sender_name", "")
        chat_name = meta.get("chat_name", "")

    sender_part = f"{role}·{sender_name}" if sender_name else role
    sender_tag = f"[{sender_part} ({sender_id})]" if sender_id else f"[{sender_part}]"

    # 场景
    if chat_type == "group":
        chat_label = f"「{chat_name}」({chat_id})" if chat_name else f"群聊({chat_id})"
        scene = f"在{chat_label}中说"
    else:
        scene = "在私聊中说"

    return f"{sender_tag} {scene}：{content}"


async def send_message(
    pool: ClientPool, event: dict, session_id: str, content: str,
    *, metrics: MetricsCollector | None = None,
):
    """发送端：立即将消息推送给 Claude，不等响应。

    session_id 和 content 由 router 计算后传入。
    普通消息和 slash commands 直接 query 推送，由 session_reader 异步处理响应。
    """
    message_id = event.get("message_id", "")
    sender_id = event.get("sender_id", "")

    if not content or not message_id:
        return

    permissions.set_sender(sender_id)

    # 首次遇到新 session 时解析并存储 sender_name / chat_name（需要在构造 prompt 之前）
    _ensure_display_names(pool, event, session_id)

    # / 开头的消息直接发给 Claude Code（内置 slash command 如 /compact /context /model）
    # 普通消息加上发送者上下文（含 ID，供后续 API 交互使用）
    if content.startswith("/"):
        prompt = content
    else:
        prompt = _build_prompt(pool, event, session_id, content)

    try:
        client = await pool.get(session_id)

        # query 仅写 stdin，不阻塞
        claude_sid = pool.get_claude_session_id(session_id)
        log_debug(f"[{session_id}] query: resume={claude_sid!r} pending_before={pool.pending_count(session_id)}")
        await client.query(prompt, session_id=claude_sid)

        # query 成功写入 stdin 后，session 进入 PROCESSING 状态——
        # 等待 session_reader 读到对应的 ResultMessage 才会翻回 READY。
        # 放在 query 之后、enqueue 之前：query 抛异常时不会留下 stuck True。
        pool.set_processing(session_id, True)

        # 入队 FIFO，reader task 据此匹配 response → 飞书回复
        pool.enqueue_message(session_id, message_id, content)
        log_debug(f"[{session_id}] query 已发送: {content[:50]}")

    except Exception as e:
        log_error(f"[{session_id}] send_message 失败: {e}")
        reply_message(message_id, "抱歉，发送消息时出了点问题。")
        if metrics:
            metrics.record_message(session_id, content, False, "")


async def session_reader(
    session_id: str, pool: ClientPool, *,
    suffix: str | None = None,
    metrics: MetricsCollector | None = None,
):
    """接收端：per-session 后台 reader，持续从 Claude 读取响应并回复飞书。

    每个 ResultMessage dequeue FIFO 队头一条消息，回复到该消息。
    Claude 可能合并多条 query 到一个 turn，此时回复内容覆盖多个问题，
    但 dequeue 仍只弹一条——后续 turn 会处理剩余消息。
    """
    turn_count = 0
    while True:
        client = pool.get_client(session_id)
        if not client:
            log_debug(f"[{session_id}] reader: client 不存在，退出")
            return

        reply_texts: list[str] = []
        reaction_id = None
        current_msg = None
        success = True
        claude_session_saved = False

        try:
            msg_index = 0
            async for msg in client.receive_response():
                msg_index += 1
                log_debug(f"[{session_id}] msg#{msg_index} type={type(msg).__name__} pending={pool.pending_count(session_id)}")
                # 从 FIFO 队头获取当前处理的飞书消息
                if current_msg is None:
                    current_msg = pool.peek_pending(session_id)

                if isinstance(msg, AssistantMessage):
                    log_debug(f"[{session_id}] AssistantMessage: session_id={msg.session_id!r} saved={claude_session_saved} blocks={len(msg.content)}")
                    if not claude_session_saved and msg.session_id:
                        log_debug(f"[{session_id}] claude session: {msg.session_id}")
                        pool.save_claude_session_id(session_id, msg.session_id)
                        claude_session_saved = True
                    if reaction_id is None and current_msg:
                        # 控制平面虚构 message_id 跳过 lark 副作用
                        if not _is_internal_message(current_msg["message_id"]):
                            reaction_id = add_reaction(current_msg["message_id"])
                    # 每个 AssistantMessage 的文本收集为独立条目
                    turn_text = ""
                    for block in msg.content:
                        if isinstance(block, TextBlock):
                            turn_text += block.text
                    if turn_text.strip():
                        reply_texts.append(turn_text.strip())

                elif isinstance(msg, ResultMessage):
                    log_debug(f"[{session_id}] ResultMessage: session_id={msg.session_id!r} saved={claude_session_saved} is_error={msg.is_error}")
                    if not claude_session_saved and msg.session_id:
                        log_debug(f"[{session_id}] claude session: {msg.session_id}")
                        pool.save_claude_session_id(session_id, msg.session_id)
                    if msg.is_error and not reply_texts:
                        reply_texts.append("抱歉，处理时出了点问题。")
                        success = False

                    # dequeue 一条，逐条回复到该消息
                    if current_msg:
                        mid = current_msg["message_id"]
                        is_internal = _is_internal_message(mid)
                        if reaction_id and not is_internal:
                            remove_reaction(mid, reaction_id)

                        prefixed_texts = [_format_with_suffix(t, suffix) for t in reply_texts]

                        # 二选一分流：internal-* → send_to_target(OWNER_ID)；真实消息 → reply_message
                        for text in prefixed_texts:
                            if is_internal:
                                try:
                                    send_to_target(OWNER_ID, text)
                                except Exception as send_err:
                                    log_error(f"[{session_id}] send_to_target 失败: {send_err}")
                            else:
                                reply_message(mid, text)

                        if metrics:
                            summary = reply_texts[0][:50] if reply_texts else ""
                            metrics.record_message(session_id, current_msg.get("content", ""), success, summary)
                        pool.dequeue_message(session_id)
                        log_debug(f"[{session_id}] turn#{turn_count} 完成: replied={len(reply_texts)} dequeued=1 remaining={pool.pending_count(session_id)} internal={is_internal}")

                    # turn 完成：session 翻回 READY（即使没匹配到 current_msg，
                    # Claude 侧的本轮 query 也已经结束）
                    pool.set_processing(session_id, False)

                    # 重置状态，准备处理下一条
                    reply_texts = []
                    reaction_id = None
                    current_msg = None
                    success = True
                    claude_session_saved = False
                    turn_count += 1

        except asyncio.CancelledError:
            # 取消路径（/clear / eviction / shutdown）：CancelledError 不是 Exception 的子类，
            # 不会被下面的 except Exception 拦下。必须单独处理，确保 PROCESSING 不变式
            # （每个 True 都有对应的 False）自洽于 handler，不依赖 pool.py 的 pop 兜底。
            # raise 保留给上游 _reader_wrapper 做任务级清理。
            pool.set_processing(session_id, False)
            raise
        except Exception as e:
            log_error(f"[{session_id}] reader 异常: {e}")
            if reaction_id and current_msg and not _is_internal_message(current_msg["message_id"]):
                remove_reaction(current_msg["message_id"], reaction_id)
            if current_msg and metrics:
                metrics.record_message(session_id, current_msg.get("content", ""), False, "")
                pool.dequeue_message(session_id)
            # 异常路径也必须把 session 翻回 READY，防止 stuck PROCESSING
            pool.set_processing(session_id, False)
