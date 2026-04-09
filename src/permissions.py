"""权限判断"""

from claude_agent_sdk.types import (
    PermissionResultAllow, PermissionResultDeny, ToolPermissionContext,
)

from src.config import OWNER_ID

SENSITIVE = ["deploy", "git push", "git merge", "git reset", "rm -rf", "drop "]

# WARNING: 全局状态，仅适用于串行处理。并发迭代时必须改为 per-request context 传递。
_current_sender_id: str | None = None


async def permission_gate(
    tool_name: str, tool_input: dict, context: ToolPermissionContext
) -> PermissionResultAllow | PermissionResultDeny:
    """非所有者禁止敏感操作"""
    if tool_name == "Bash" and _current_sender_id != OWNER_ID:
        cmd = tool_input.get("command", "")
        if any(p in cmd for p in SENSITIVE):
            return PermissionResultDeny(
                message="这个操作需要凯南本人确认，我没有权限执行。"
            )
    return PermissionResultAllow()
