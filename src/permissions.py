"""权限判断"""

import contextvars

from claude_agent_sdk.types import (
    PermissionResultAllow, PermissionResultDeny, ToolPermissionContext,
)

from src.config import OWNER_ID, DISALLOWED_SKILLS

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
    # 拦截黑名单中的 Skill 工具调用（disallowed_tools 无法精确到 skill 参数）
    if tool_name == "Skill" and DISALLOWED_SKILLS:
        skill_name = tool_input.get("skill", "")
        if skill_name in DISALLOWED_SKILLS:
            return PermissionResultDeny(
                message=f"Skill '{skill_name}' 在当前环境下不可用。"
            )

    sender = _current_sender_id.get()
    if tool_name == "Bash" and sender != OWNER_ID:
        if sender is None:
            return PermissionResultDeny(
                message="无法识别请求来源，拒绝执行敏感操作。"
            )
        cmd = tool_input.get("command", "")
        if any(p in cmd for p in SENSITIVE):
            return PermissionResultDeny(
                message="这个操作需要凯南本人确认，我没有权限执行。"
            )
    return PermissionResultAllow()
