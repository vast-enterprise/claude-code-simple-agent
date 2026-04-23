# src/router.py
"""命令路由层：统一处理所有飞书命令，决定消息发往哪个 session"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.config import BOT_NAME, log_debug
from src.handler import compute_session_id
from src.lark import reply_message

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
    # TODO: 实现命令路由
    pass
