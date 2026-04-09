"""avatar 单元测试"""

import asyncio
import importlib.util
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# avatar/ 不是 Python 包，直接从文件路径加载模块
_spec = importlib.util.spec_from_file_location("avatar_mod", str(Path(__file__).parent / "avatar.py"))
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)
import sys
sys.modules["avatar_mod"] = mod  # 注册到 sys.modules，让 patch() 能找到

# mock 路径前缀（importlib 加载的模块名）
MOD = "avatar_mod"


def run_async(coro):
    """Python 3.14 兼容的 async 测试辅助"""
    return asyncio.run(coro)


# ── should_respond ──────────────────────────────────────────────

class TestShouldRespond:
    def test_p2p_user_message(self):
        assert mod.should_respond({"chat_type": "p2p", "content": "hello", "sender_type": "user"}) is True

    def test_p2p_bot_message_ignored(self):
        assert mod.should_respond({"chat_type": "p2p", "content": "hello", "sender_type": "bot"}) is False

    def test_group_at_bot(self):
        assert mod.should_respond({"chat_type": "group", "content": "@_user_1 帮我查一下", "sender_type": "user"}) is True

    def test_group_no_at(self):
        assert mod.should_respond({"chat_type": "group", "content": "今天天气不错", "sender_type": "user"}) is False

    def test_group_at_all_not_triggered(self):
        """@_all 不应触发响应（I3 修复验证）"""
        assert mod.should_respond({"chat_type": "group", "content": "@_all 开会了", "sender_type": "user"}) is False

    def test_empty_content(self):
        assert mod.should_respond({"chat_type": "p2p", "content": "", "sender_type": "user"}) is True

    def test_missing_fields(self):
        assert mod.should_respond({}) is False


# ── permission_gate ─────────────────────────────────────────────

class TestPermissionGate:
    @pytest.fixture(autouse=True)
    def _mock_context(self):
        self.ctx = MagicMock()

    def test_owner_can_deploy(self):
        mod._current_sender_id = mod.OWNER_ID
        result = run_async(mod.permission_gate("Bash", {"command": "deploy staging"}, self.ctx))
        assert isinstance(result, mod.PermissionResultAllow)

    def test_non_owner_blocked_on_deploy(self):
        mod._current_sender_id = "ou_other"
        result = run_async(mod.permission_gate("Bash", {"command": "deploy staging"}, self.ctx))
        assert isinstance(result, mod.PermissionResultDeny)

    def test_non_owner_allowed_on_safe_command(self):
        mod._current_sender_id = "ou_other"
        result = run_async(mod.permission_gate("Bash", {"command": "ls -la"}, self.ctx))
        assert isinstance(result, mod.PermissionResultAllow)

    def test_non_bash_tool_always_allowed(self):
        mod._current_sender_id = "ou_other"
        result = run_async(mod.permission_gate("Read", {"file_path": "/etc/passwd"}, self.ctx))
        assert isinstance(result, mod.PermissionResultAllow)

    @pytest.mark.parametrize("cmd", [
        "git push origin main",
        "git merge feature",
        "git reset --hard",
        "rm -rf /tmp/data",
    ])
    def test_non_owner_blocked_on_sensitive_commands(self, cmd):
        mod._current_sender_id = "ou_other"
        result = run_async(mod.permission_gate("Bash", {"command": cmd}, self.ctx))
        assert isinstance(result, mod.PermissionResultDeny)


# ── reply_message ───────────────────────────────────────────────

class TestReplyMessage:
    @patch(f"{MOD}.subprocess")
    def test_sends_correct_command(self, mock_sp):
        mock_sp.run.return_value = MagicMock(returncode=0)
        mod.reply_message("om_123", "hello")
        mock_sp.run.assert_called_once()
        args = mock_sp.run.call_args[0][0]
        assert "lark-cli" in args
        assert "om_123" in args[3]

    @patch(f"{MOD}.subprocess")
    def test_truncates_long_text(self, mock_sp):
        mock_sp.run.return_value = MagicMock(returncode=0)
        mod.reply_message("om_123", "x" * 5000)
        sent_data = json.loads(mock_sp.run.call_args[0][0][5])  # --data value
        content = json.loads(sent_data["content"])
        assert len(content["text"]) < 4100
        assert "截断" in content["text"]

    @patch(f"{MOD}.subprocess")
    def test_logs_failure(self, mock_sp, capsys):
        mock_sp.run.return_value = MagicMock(returncode=1, stderr="API error")
        mod.reply_message("om_123", "hello")
        captured = capsys.readouterr()
        assert "回复消息失败" in captured.err


# ── add_reaction / remove_reaction ──────────────────────────────

class TestReactions:
    @patch(f"{MOD}.subprocess")
    def test_add_reaction_returns_id(self, mock_sp):
        mock_sp.run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({"data": {"reaction_id": "r_abc"}})
        )
        assert mod.add_reaction("om_123") == "r_abc"

    @patch(f"{MOD}.subprocess")
    def test_add_reaction_returns_none_on_failure(self, mock_sp):
        mock_sp.run.return_value = MagicMock(returncode=1, stdout="")
        assert mod.add_reaction("om_123") is None

    @patch(f"{MOD}.subprocess")
    def test_remove_reaction_logs_failure(self, mock_sp, capsys):
        mock_sp.run.return_value = MagicMock(returncode=1, stderr="not found")
        mod.remove_reaction("om_123", "r_abc")
        captured = capsys.readouterr()
        assert "移除表情失败" in captured.err


# ── handle_message ──────────────────────────────────────────────

class TestHandleMessage:
    def _make_event(self, content="hello", sender_id=None, chat_type="p2p"):
        return {
            "content": content,
            "message_id": "om_test",
            "sender_id": sender_id or mod.OWNER_ID,
            "chat_type": chat_type,
        }

    @patch(f"{MOD}.reply_message")
    @patch(f"{MOD}.remove_reaction")
    @patch(f"{MOD}.add_reaction", return_value="r_abc")
    def test_full_flow(self, mock_add, mock_remove, mock_reply):
        client = MagicMock()
        client.query = AsyncMock()

        async def fake_response():
            yield mod.AssistantMessage(content=[mod.TextBlock(text="回复内容")], model="sonnet")
            yield mod.ResultMessage(
                subtype="result", duration_ms=100, duration_api_ms=80,
                is_error=False, num_turns=1, session_id="default",
            )

        client.receive_response = fake_response
        run_async(mod.handle_message(client, self._make_event()))

        client.query.assert_called_once()
        mock_add.assert_called_once_with("om_test")
        mock_remove.assert_called_once_with("om_test", "r_abc")
        mock_reply.assert_called_once_with("om_test", "回复内容")

    @patch(f"{MOD}.reply_message")
    @patch(f"{MOD}.add_reaction")
    def test_skips_empty_content(self, mock_add, mock_reply):
        client = MagicMock()
        run_async(mod.handle_message(client, self._make_event(content="")))
        client.query.assert_not_called()
        mock_reply.assert_not_called()

    @patch(f"{MOD}.reply_message")
    @patch(f"{MOD}.remove_reaction")
    @patch(f"{MOD}.add_reaction", return_value=None)
    def test_error_response(self, mock_add, mock_remove, mock_reply):
        client = MagicMock()
        client.query = AsyncMock()

        async def fake_error_response():
            yield mod.ResultMessage(
                subtype="result", duration_ms=100, duration_api_ms=80,
                is_error=True, num_turns=0, session_id="default",
            )

        client.receive_response = fake_error_response
        run_async(mod.handle_message(client, self._make_event()))

        mock_reply.assert_called_once_with("om_test", "抱歉，处理时出了点问题。")
        mock_remove.assert_not_called()

    @patch(f"{MOD}.reply_message")
    @patch(f"{MOD}.remove_reaction")
    @patch(f"{MOD}.add_reaction", return_value="r_abc")
    def test_at_mention_cleaned(self, mock_add, mock_remove, mock_reply):
        client = MagicMock()
        client.query = AsyncMock()

        async def fake_response():
            yield mod.AssistantMessage(content=[mod.TextBlock(text="ok")], model="sonnet")
            yield mod.ResultMessage(
                subtype="result", duration_ms=100, duration_api_ms=80,
                is_error=False, num_turns=1, session_id="default",
            )

        client.receive_response = fake_response
        run_async(mod.handle_message(client, self._make_event(content="@_user_1 帮我查一下", chat_type="group")))

        prompt_arg = client.query.call_args[0][0]
        assert "@_user_1" not in prompt_arg
        assert "帮我查一下" in prompt_arg
