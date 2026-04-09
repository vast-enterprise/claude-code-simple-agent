"""权限判断"""

import contextvars

from claude_agent_sdk.types import (
    PermissionResultAllow, PermissionResultDeny, ToolPermissionContext,
)

from src.config import OWNER_ID

SENSITIVE = ["deploy", "git push", "git merge", "git reset", "rm -rf", "drop "]

# per-task 上下文隔离，支持并发场景
_current_sender_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "_current_sender_id", default=None
)


def set_sender(sender_id: str):
    """设置当前请求的发送者 ID"""
    _current_sender_id.set(sender_id)


def get_sender() -> str | None:
    """获取当前请求的发送者 ID"""
    return _current_sender_id.get()


async def permission_gate(
    tool_name: str, tool_input: dict, context: ToolPermissionContext
) -> PermissionResultAllow | PermissionResultDeny:
    """非所有者禁止敏感操作"""
    if tool_name == "Bash" and _current_sender_id.get() != OWNER_ID:
        cmd = tool_input.get("command", "")
        if any(p in cmd for p in SENSITIVE):
            return PermissionResultDeny(
                message="这个操作需要凯南本人确认，我没有权限执行。"
            )
    return PermissionResultAllow()
