"""permissions 模块测试"""

import asyncio
from unittest.mock import MagicMock

import pytest

from src.permissions import permission_gate, set_sender, PermissionResultAllow, PermissionResultDeny
from src.config import OWNER_ID
import src.permissions as permissions


def run_async(coro):
    return asyncio.run(coro)


class TestPermissionGate:
    @pytest.fixture(autouse=True)
    def _ctx(self):
        self.ctx = MagicMock()
        # 每个测试前重置 ContextVar，防止跨测试污染
        permissions._current_sender_id.set(None)

    def test_owner_allowed_on_deploy(self):
        set_sender(OWNER_ID)
        result = run_async(permission_gate("Bash", {"command": "deploy staging"}, self.ctx))
        assert isinstance(result, PermissionResultAllow)

    def test_non_owner_blocked_on_deploy(self):
        set_sender("ou_other")
        result = run_async(permission_gate("Bash", {"command": "deploy staging"}, self.ctx))
        assert isinstance(result, PermissionResultDeny)

    def test_non_owner_allowed_on_safe_command(self):
        set_sender("ou_other")
        result = run_async(permission_gate("Bash", {"command": "ls -la"}, self.ctx))
        assert isinstance(result, PermissionResultAllow)

    def test_non_bash_tool_always_allowed(self):
        set_sender("ou_other")
        result = run_async(permission_gate("Read", {"file_path": "/etc/passwd"}, self.ctx))
        assert isinstance(result, PermissionResultAllow)

    @pytest.mark.parametrize("cmd", [
        "git push origin main",
        "git merge feature",
        "git reset --hard",
        "rm -rf /tmp/data",
    ])
    def test_non_owner_blocked_on_sensitive_commands(self, cmd):
        set_sender("ou_other")
        result = run_async(permission_gate("Bash", {"command": cmd}, self.ctx))
        assert isinstance(result, PermissionResultDeny)

    def test_concurrent_sender_isolation(self):
        """验证 contextvars 在并发 task 中的隔离性"""
        results = {}

        async def check_as(sender_id, label):
            set_sender(sender_id)
            await asyncio.sleep(0.01)  # 让出控制权，模拟并发交错
            result = await permission_gate("Bash", {"command": "deploy staging"}, self.ctx)
            results[label] = type(result).__name__

        async def run():
            await asyncio.gather(
                check_as(OWNER_ID, "owner"),
                check_as("ou_other", "other"),
            )

        run_async(run())
        assert results["owner"] == "PermissionResultAllow"
        assert results["other"] == "PermissionResultDeny"

    def test_unknown_sender_denied_on_bash(self):
        """sender 为 None（context 丢失）时，Bash 调用一律 deny"""
        # 新的 asyncio.run 会创建全新 context，_current_sender_id 为默认值 None
        result = run_async(permission_gate("Bash", {"command": "ls -la"}, self.ctx))
        assert isinstance(result, PermissionResultDeny)

    def test_unknown_sender_allowed_on_non_bash(self):
        """sender 为 None 时，非 Bash 工具仍然放行"""
        result = run_async(permission_gate("Read", {"file_path": "/tmp"}, self.ctx))
        assert isinstance(result, PermissionResultAllow)
