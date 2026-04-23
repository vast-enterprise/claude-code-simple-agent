# src/router.py
"""命令路由层：统一处理所有飞书命令，决定消息发往哪个 session"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.config import BOT_NAME, log_debug
from src.handler import compute_session_id, send_message, session_reader, should_respond
from src.lark import reply_message, resolve_rich_content

if TYPE_CHECKING:
    from src.defaults_store import DefaultsStore
    from src.metrics import MetricsCollector
    from src.pool import ClientPool
    from src.session import SessionDispatcher

BOT_MENTION = f"@{BOT_NAME}"


def _compute_base_session_id(event: dict) -> str:
    """计算原始 session_id（不带 suffix），复用 handler.compute_session_id"""
    return compute_session_id(event)


def _compute_full_session_id(base: str, suffix: str | None) -> str:
    """base + suffix 拼接，suffix 为 None 时返回 base"""
    if suffix is None:
        return base
    return f"{base}_{suffix}"


def _extract_suffix_from_session_id(session_id: str, base: str) -> str | None:
    """从完整 session_id 中提取 suffix，无 suffix 返回 None"""
    if session_id == base:
        return None
    if session_id.startswith(base + "_"):
        return session_id[len(base) + 1 :]
    return None


async def route_message(
    pool: ClientPool,
    event: dict,
    dispatcher: SessionDispatcher,
    defaults: DefaultsStore,
    *,
    metrics: MetricsCollector | None = None,
) -> None:
    """路由消息到对应 session 或处理命令"""
    if not should_respond(event):
        return

    content = event.get("content", "").strip()
    content = content.replace(BOT_MENTION, "").strip()
    message_id = event.get("message_id", "")

    # 富消息解析
    rich = resolve_rich_content(event)
    if rich is not None:
        content = rich

    if not content or not message_id:
        return

    base_session_id = _compute_base_session_id(event)

    # 1. /new {suffix} {message}
    if content.startswith("/new ") or content == "/new":
        await _handle_new_command(pool, event, dispatcher, base_session_id, content, metrics)
        return

    # 2. /switch {suffix?}
    if content.startswith("/switch") and (len(content) == 7 or content[7] == " "):
        await _handle_switch_command(pool, event, defaults, base_session_id, content)
        return

    # 3. $suffix {message}
    if content.startswith("$"):
        await _handle_dollar_prefix(pool, event, dispatcher, base_session_id, content, metrics)
        return

    # 4. /sessions
    if content == "/sessions":
        await _handle_sessions_command(pool, event, defaults, base_session_id)
        return

    # 5. /clear {suffix?}
    if content.startswith("/clear") and (len(content) == 6 or content[6] == " "):
        await _handle_clear_command(pool, event, dispatcher, defaults, base_session_id, content)
        return

    # 6. /clear-all
    if content == "/clear-all":
        await _handle_clear_all_command(pool, event, dispatcher, defaults, base_session_id)
        return

    # 7. /interrupt {suffix?}
    if content.startswith("/interrupt") and (len(content) == 10 or content[10] == " "):
        await _handle_interrupt_command(pool, event, dispatcher, base_session_id, content)
        return

    # 8. 普通消息或其他 slash cmd → 默认 session
    default_suffix = defaults.get_default(base_session_id)
    target_session_id = _compute_full_session_id(base_session_id, default_suffix)
    await _dispatch_to_session(
        pool, event, dispatcher, target_session_id, content, default_suffix, metrics=metrics
    )


async def _handle_new_command(pool, event, dispatcher, base, content, metrics):
    """处理 /new {suffix} {message}"""
    parts = content.split(None, 2)  # ["/new", "suffix", "message"]
    if len(parts) < 3:
        reply_message(
            event["message_id"],
            "用法：/new {会话名称} {消息内容}\n"
            "示例：/new cms翻译 查查这个需求的状态",
        )
        return

    suffix = parts[1]
    message = parts[2]
    target_session_id = _compute_full_session_id(base, suffix)

    await _dispatch_to_session(
        pool, event, dispatcher, target_session_id, message, suffix, metrics=metrics
    )


async def _handle_switch_command(pool, event, defaults, base, content):
    """处理 /switch {suffix?}"""
    parts = content.split(None, 1)
    suffix = parts[1] if len(parts) > 1 else None

    if suffix is None:
        # 切回原始会话
        defaults.set_default(base, None)
        reply_message(event["message_id"], "已切换回原始会话。")
        return

    # 检查目标会话是否存在
    target_session_id = _compute_full_session_id(base, suffix)
    all_sessions = pool.list_sessions()
    if target_session_id not in all_sessions:
        reply_message(event["message_id"], f"会话「{suffix}」不存在，请先 /new 创建。")
        return

    defaults.set_default(base, suffix)
    reply_message(event["message_id"], f"已切换默认会话到「{suffix}」。后续消息将发送到此会话。")


async def _handle_dollar_prefix(pool, event, dispatcher, base, content, metrics):
    """处理 $suffix {message}"""
    # 提取 suffix（到第一个空格）
    if " " not in content[1:]:
        reply_message(event["message_id"], "用法：$会话名称 消息内容")
        return

    suffix, message = content[1:].split(None, 1)
    target_session_id = _compute_full_session_id(base, suffix)

    # 检查会话是否存在
    all_sessions = pool.list_sessions()
    if target_session_id not in all_sessions:
        reply_message(
            event["message_id"],
            f"会话「{suffix}」不存在，请先 /new {suffix} {{消息}} 创建。",
        )
        return

    await _dispatch_to_session(
        pool, event, dispatcher, target_session_id, message, suffix, metrics=metrics
    )


async def _dispatch_to_session(pool, event, dispatcher, session_id, content, suffix, *, metrics):
    """内部 dispatch 封装"""
    await dispatcher.dispatch(
        session_id,
        send_message(pool, event, session_id, content, metrics=metrics),
        reader_factory=lambda sid=session_id, sfx=suffix: session_reader(
            sid, pool, suffix=sfx, metrics=metrics
        ),
    )


async def _handle_sessions_command(pool, event, defaults, base):
    """处理 /sessions：列出当前用户的所有会话"""
    all_sessions = pool.list_sessions()
    user_sessions = [
        (sid, data)
        for sid, data in all_sessions.items()
        if sid.startswith(base)
    ]

    if not user_sessions:
        reply_message(event["message_id"], "当前没有活跃会话。")
        return

    # 按创建时间排序
    user_sessions.sort(key=lambda x: x[1].get("created_at", ""))

    lines = ["当前会话列表："]
    default_suffix = defaults.get_default(base)

    for sid, data in user_sessions:
        suffix = _extract_suffix_from_session_id(sid, base)
        label = suffix if suffix else "（原始会话）"
        is_default = " [默认]" if suffix == default_suffix else ""
        created = data.get("created_at", "未知")
        lines.append(f"• {label}{is_default} - 创建于 {created}")

    reply_message(event["message_id"], "\n".join(lines))


async def _handle_clear_command(pool, event, dispatcher, defaults, base, content):
    """处理 /clear {suffix?}：清除指定会话或当前默认会话"""
    parts = content.split(None, 1)
    suffix = parts[1] if len(parts) > 1 else None

    # 如果没有指定 suffix，使用当前默认会话
    if suffix is None:
        suffix = defaults.get_default(base)

    target_session_id = _compute_full_session_id(base, suffix)

    # 检查会话是否存在
    all_sessions = pool.list_sessions()
    if target_session_id not in all_sessions:
        label = suffix if suffix else "原始会话"
        reply_message(event["message_id"], f"会话「{label}」不存在。")
        return

    # 取消 reader task
    dispatcher.cancel_reader(target_session_id)

    # 移除 client 和 store 记录
    removed = await pool.remove(target_session_id)

    # 如果清除的是当前默认会话，重置为 None
    if suffix == defaults.get_default(base):
        defaults.set_default(base, None)

    label = suffix if suffix else "原始会话"
    if removed:
        reply_message(event["message_id"], f"已清除会话「{label}」。")
    else:
        reply_message(event["message_id"], f"清除会话「{label}」失败。")


async def _handle_clear_all_command(pool, event, dispatcher, defaults, base):
    """处理 /clear-all：清除当前用户的所有会话"""
    all_sessions = pool.list_sessions()
    user_sessions = [
        sid for sid in all_sessions.keys()
        if sid.startswith(base)
    ]

    if not user_sessions:
        reply_message(event["message_id"], "当前没有活跃会话。")
        return

    # 取消所有 reader tasks
    for sid in user_sessions:
        dispatcher.cancel_reader(sid)

    # 移除所有 sessions
    removed_count = 0
    for sid in user_sessions:
        if await pool.remove(sid):
            removed_count += 1

    # 重置默认会话
    defaults.remove_user(base)

    reply_message(event["message_id"], f"已清除 {removed_count} 个会话。")


async def _handle_interrupt_command(pool, event, dispatcher, base, content):
    """处理 /interrupt {suffix?}：中断指定会话或当前默认会话的执行"""
    parts = content.split(None, 1)
    suffix = parts[1] if len(parts) > 1 else None

    target_session_id = _compute_full_session_id(base, suffix)

    # 检查会话是否存在
    client = pool.get_client(target_session_id)
    if client is None:
        label = suffix if suffix else "原始会话"
        reply_message(event["message_id"], f"会话「{label}」不存在或未激活。")
        return

    # 发送 interrupt
    try:
        await client.interrupt()
        label = suffix if suffix else "原始会话"
        reply_message(event["message_id"], f"已向会话「{label}」发送中断信号。")
    except Exception as e:
        log_error(f"interrupt {target_session_id} 失败: {e}")
        reply_message(event["message_id"], "中断失败，请稍后重试。")
