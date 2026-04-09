"""permissions 模块测试"""

import asyncio
from unittest.mock import MagicMock

import pytest

from src.permissions import permission_gate, PermissionResultAllow, PermissionResultDeny
from src.config import OWNER_ID
import src.permissions as permissions


def run_async(coro):
    return asyncio.run(coro)


class TestPermissionGate:
    @pytest.fixture(autouse=True)
    def _ctx(self):
        self.ctx = MagicMock()

    def test_owner_allowed_on_deploy(self):
        permissions._current_sender_id = OWNER_ID
        result = run_async(permission_gate("Bash", {"command": "deploy staging"}, self.ctx))
        assert isinstance(result, PermissionResultAllow)

    def test_non_owner_blocked_on_deploy(self):
        permissions._current_sender_id = "ou_other"
        result = run_async(permission_gate("Bash", {"command": "deploy staging"}, self.ctx))
        assert isinstance(result, PermissionResultDeny)

    def test_non_owner_allowed_on_safe_command(self):
        permissions._current_sender_id = "ou_other"
        result = run_async(permission_gate("Bash", {"command": "ls -la"}, self.ctx))
        assert isinstance(result, PermissionResultAllow)

    def test_non_bash_tool_always_allowed(self):
        permissions._current_sender_id = "ou_other"
        result = run_async(permission_gate("Read", {"file_path": "/etc/passwd"}, self.ctx))
        assert isinstance(result, PermissionResultAllow)

    @pytest.mark.parametrize("cmd", [
        "git push origin main",
        "git merge feature",
        "git reset --hard",
        "rm -rf /tmp/data",
    ])
    def test_non_owner_blocked_on_sensitive_commands(self, cmd):
        permissions._current_sender_id = "ou_other"
        result = run_async(permission_gate("Bash", {"command": cmd}, self.ctx))
        assert isinstance(result, PermissionResultDeny)
