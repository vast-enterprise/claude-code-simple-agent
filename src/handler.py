"""消息过滤与处理"""

from __future__ import annotations

from typing import TYPE_CHECKING

from claude_agent_sdk.types import AssistantMessage, ResultMessage, TextBlock

import src.permissions as permissions
from src.config import OWNER_ID, BOT_NAME, log_debug
from src.lark import add_reaction, remove_reaction, reply_message, resolve_user_name, resolve_chat_name
from src.pool import ClientPool

if TYPE_CHECKING:
    from src.metrics import MetricsCollector

BOT_MENTION = f"@{BOT_NAME}"

_COMMANDS = frozenset(("clear", "compact"))


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


def parse_command(content: str) -> str | None:
    """解析 / 开头的指令，返回指令名或 None"""
    if not content.startswith("/"):
        return None
    cmd = content.split()[0].lstrip("/").lower()
    if cmd in _COMMANDS:
        return cmd
    return None


async def _do_compact(pool: ClientPool, session_id: str) -> str:
    """向 Claude Code 发送 /compact 内置命令，触发原生会话压缩"""
    claude_sid = pool.get_claude_session_id(session_id)
    if not claude_sid:
        return "当前没有活跃会话，无需压缩。"

    try:
        client = await pool.get(session_id)
        await client.query("/compact", session_id=claude_sid)

        async for msg in client.receive_response():
            if isinstance(msg, ResultMessage):
                if msg.is_error:
                    return "压缩失败，请稍后重试。"
                break

        return "会话已压缩。"
    except Exception as e:
        return f"压缩失败: {e}"


async def handle_command(
    pool: ClientPool, metrics: MetricsCollector, event: dict, command: str
) -> None:
    """处理飞书指令，直接回复，不经过 Claude"""
    message_id = event.get("message_id", "")
    sender_id = event.get("sender_id", "")
    session_id = compute_session_id(event)

    if command == "clear":
        removed = await pool.remove(session_id)
        text = "已清除当前会话。下次发消息将开始新对话。" if removed else "当前没有活跃会话。"

    elif command == "compact":
        text = await _do_compact(pool, session_id)

    else:
        text = f"未知指令: /{command}"

    reply_message(message_id, text)


async def handle_message(
    pool: ClientPool, event: dict, *, metrics: MetricsCollector | None = None
):
    """处理单条飞书消息，从 pool 获取独立 client 实现会话隔离"""
    content = event.get("content", "").strip()
    message_id = event.get("message_id", "")
    sender_id = event.get("sender_id", "")
    chat_type = event.get("chat_type", "p2p")

    if not content or not message_id:
        return

    content = content.replace(BOT_MENTION, "").strip()

    # 指令检测：/ 开头的指令直接处理，不经过 Claude
    cmd = parse_command(content)
    if cmd is not None:
        await handle_command(pool, metrics, event, cmd)
        return

    permissions.set_sender(sender_id)

    # / 开头的消息直接发给 Claude Code（可能是内置 slash command 如 /status /compact）
    # 非 / 开头的普通消息加上发送者上下文
    if content.startswith("/"):
        prompt = content
    else:
        sender_label = "所有者" if sender_id == OWNER_ID else "同事"
        prompt = f"[{sender_label}] 在{'群聊' if chat_type == 'group' else '私聊'}中说：{content}"

    session_id = compute_session_id(event)

    # 首次遇到新 session 时解析并存储 sender_name / chat_name
    _ensure_display_names(pool, event, session_id)

    reply_text = ""
    success = True

    try:
        client = await pool.get(session_id)

        # 用存储的 Claude session_id resume，没有则首次创建
        claude_sid = pool.get_claude_session_id(session_id)
        await client.query(prompt, session_id=claude_sid)

        # 从该 client 的独立 stream 收集回复
        reaction_id = None
        claude_session_saved = False
        async for msg in client.receive_response():
            if isinstance(msg, AssistantMessage):
                if not claude_session_saved and msg.session_id:
                    log_debug(f"[{session_id}] claude session: {msg.session_id}")
                    pool.save_claude_session_id(session_id, msg.session_id)
                    claude_session_saved = True
                if reaction_id is None:
                    reaction_id = add_reaction(message_id)
                for block in msg.content:
                    if isinstance(block, TextBlock):
                        reply_text += block.text
            elif isinstance(msg, ResultMessage):
                if not claude_session_saved and msg.session_id:
                    log_debug(f"[{session_id}] claude session: {msg.session_id}")
                    pool.save_claude_session_id(session_id, msg.session_id)
                if msg.is_error and not reply_text:
                    reply_text = "抱歉，处理时出了点问题。"
                    success = not msg.is_error
                break

        if reaction_id:
            remove_reaction(message_id, reaction_id)

        if reply_text.strip():
            reply_message(message_id, reply_text.strip())

    except Exception:
        success = False
        raise
    finally:
        if metrics:
            metrics.record_message(session_id, content, success, reply_text[:50])
