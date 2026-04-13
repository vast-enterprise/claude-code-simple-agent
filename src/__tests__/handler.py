"""handler 模块测试"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.handler import should_respond, handle_message, compute_session_id, BOT_MENTION
from src.config import OWNER_ID
from src.pool import ClientPool
from claude_agent_sdk.types import AssistantMessage, ResultMessage, TextBlock
import src.permissions as permissions


def run_async(coro):
    return asyncio.run(coro)


class TestShouldRespond:
    def test_responds_to_p2p_user_message(self):
        assert should_respond({"chat_type": "p2p", "content": "hello", "sender_type": "user"}) is True

    def test_ignores_bot_message(self):
        assert should_respond({"chat_type": "p2p", "content": "hello", "sender_type": "bot"}) is False

    def test_responds_to_group_at_bot(self):
        assert should_respond({"chat_type": "group", "content": f"{BOT_MENTION} 帮我查一下", "sender_type": "user"}) is True

    def test_ignores_group_without_at(self):
        assert should_respond({"chat_type": "group", "content": "今天天气不错", "sender_type": "user"}) is False

    def test_ignores_group_at_all(self):
        assert should_respond({"chat_type": "group", "content": "@_all 开会了", "sender_type": "user"}) is False

    def test_responds_to_empty_p2p(self):
        assert should_respond({"chat_type": "p2p", "content": "", "sender_type": "user"}) is True

    def test_ignores_missing_fields(self):
        assert should_respond({}) is False


class TestComputeSessionId:
    def test_p2p_uses_sender_id(self):
        assert compute_session_id({"chat_type": "p2p", "sender_id": "ou_abc"}) == "p2p_ou_abc"

    def test_group_uses_chat_id_and_sender_id(self):
        assert compute_session_id({"chat_type": "group", "chat_id": "oc_xyz", "sender_id": "ou_abc"}) == "group_oc_xyz_ou_abc"

    def test_group_different_users_get_different_sessions(self):
        event_a = {"chat_type": "group", "chat_id": "oc_xyz", "sender_id": "ou_alice"}
        event_b = {"chat_type": "group", "chat_id": "oc_xyz", "sender_id": "ou_bob"}
        assert compute_session_id(event_a) != compute_session_id(event_b)

    def test_group_without_chat_id_falls_back(self):
        assert compute_session_id({"chat_type": "group", "sender_id": "ou_abc"}) == "group_unknown_ou_abc"

    def test_defaults_to_p2p(self):
        assert compute_session_id({"sender_id": "ou_abc"}) == "p2p_ou_abc"


def _make_mock_pool(messages, claude_session_id=None):
    """构造 mock pool：pool.get() 返回一个 mock client，client.receive_response() 产出 messages"""
    client = MagicMock()
    client.query = AsyncMock()

    async def fake_receive():
        for msg in messages:
            yield msg

    client.receive_response = fake_receive

    pool = MagicMock(spec=ClientPool)
    pool.get = AsyncMock(return_value=client)
    pool.get_claude_session_id = MagicMock(return_value=claude_session_id)
    pool.save_claude_session_id = MagicMock()
    return pool, client


class TestHandleMessage:
    """handle_message 从 pool 获取独立 client，用 receive_response() 读回复"""

    def _event(self, content="hello", sender_id=None, chat_type="p2p"):
        return {
            "content": content,
            "message_id": "om_test",
            "sender_id": sender_id or OWNER_ID,
            "chat_type": chat_type,
        }

    @patch("src.handler.reply_message")
    @patch("src.handler.remove_reaction")
    @patch("src.handler.add_reaction", return_value="r_abc")
    def test_full_flow_replies_and_cleans_reaction(self, mock_add, mock_remove, mock_reply):
        messages = [
            AssistantMessage(content=[TextBlock(text="回复内容")], model="sonnet"),
            ResultMessage(subtype="result", duration_ms=100, duration_api_ms=80, is_error=False, num_turns=1, session_id="x"),
        ]
        pool, client = _make_mock_pool(messages)

        run_async(handle_message(pool, self._event()))

        client.query.assert_called_once()
        mock_add.assert_called_once_with("om_test")
        mock_remove.assert_called_once_with("om_test", "r_abc")
        mock_reply.assert_called_once_with("om_test", "回复内容")

    @patch("src.handler.reply_message")
    @patch("src.handler.remove_reaction")
    @patch("src.handler.add_reaction", return_value="r_abc")
    def test_p2p_routes_to_correct_session(self, mock_add, mock_remove, mock_reply):
        messages = [
            AssistantMessage(content=[TextBlock(text="ok")], model="sonnet"),
            ResultMessage(subtype="result", duration_ms=100, duration_api_ms=80, is_error=False, num_turns=1, session_id="x"),
        ]
        pool, client = _make_mock_pool(messages)

        run_async(handle_message(pool, self._event(sender_id="ou_user_123")))

        pool.get.assert_called_once_with("p2p_ou_user_123")
        pool.get_claude_session_id.assert_called_once_with("p2p_ou_user_123")

    @patch("src.handler.reply_message")
    @patch("src.handler.remove_reaction")
    @patch("src.handler.add_reaction", return_value="r_abc")
    def test_saves_claude_session_id(self, mock_add, mock_remove, mock_reply):
        messages = [
            AssistantMessage(content=[TextBlock(text="ok")], model="sonnet", session_id="claude_abc"),
            ResultMessage(subtype="result", duration_ms=100, duration_api_ms=80, is_error=False, num_turns=1, session_id="claude_abc"),
        ]
        pool, client = _make_mock_pool(messages)

        run_async(handle_message(pool, self._event()))

        pool.save_claude_session_id.assert_called_with(f"p2p_{OWNER_ID}", "claude_abc")

    @patch("src.handler.reply_message")
    @patch("src.handler.remove_reaction")
    @patch("src.handler.add_reaction", return_value="r_abc")
    def test_resumes_with_stored_claude_session_id(self, mock_add, mock_remove, mock_reply):
        messages = [
            AssistantMessage(content=[TextBlock(text="ok")], model="sonnet"),
            ResultMessage(subtype="result", duration_ms=100, duration_api_ms=80, is_error=False, num_turns=1, session_id="x"),
        ]
        pool, client = _make_mock_pool(messages, claude_session_id="stored_session_123")

        run_async(handle_message(pool, self._event()))

        _, kwargs = client.query.call_args
        assert kwargs["session_id"] == "stored_session_123"

    @patch("src.handler.reply_message")
    @patch("src.handler.remove_reaction")
    @patch("src.handler.add_reaction", return_value="r_abc")
    def test_group_routes_correctly(self, mock_add, mock_remove, mock_reply):
        messages = [
            AssistantMessage(content=[TextBlock(text="ok")], model="sonnet"),
            ResultMessage(subtype="result", duration_ms=100, duration_api_ms=80, is_error=False, num_turns=1, session_id="x"),
        ]
        pool, client = _make_mock_pool(messages)

        event = self._event(content=f"{BOT_MENTION} hello", chat_type="group")
        event["chat_id"] = "oc_group_456"
        run_async(handle_message(pool, event))

        pool.get.assert_called_once_with(f"group_oc_group_456_{OWNER_ID}")

    @patch("src.handler.reply_message")
    @patch("src.handler.add_reaction")
    def test_skips_empty_content(self, mock_add, mock_reply):
        pool = MagicMock(spec=ClientPool)
        run_async(handle_message(pool, self._event(content="")))
        pool.get.assert_not_called()

    @patch("src.handler.reply_message")
    @patch("src.handler.remove_reaction")
    @patch("src.handler.add_reaction", return_value=None)
    def test_replies_error_on_failure(self, mock_add, mock_remove, mock_reply):
        messages = [
            ResultMessage(subtype="result", duration_ms=100, duration_api_ms=80, is_error=True, num_turns=0, session_id="x"),
        ]
        pool, client = _make_mock_pool(messages)

        run_async(handle_message(pool, self._event()))
        mock_reply.assert_called_once_with("om_test", "抱歉，处理时出了点问题。")
        mock_remove.assert_not_called()

    @patch("src.handler.reply_message")
    @patch("src.handler.remove_reaction")
    @patch("src.handler.add_reaction", return_value="r_abc")
    def test_cleans_at_mention_from_prompt(self, mock_add, mock_remove, mock_reply):
        messages = [
            AssistantMessage(content=[TextBlock(text="ok")], model="sonnet"),
            ResultMessage(subtype="result", duration_ms=100, duration_api_ms=80, is_error=False, num_turns=1, session_id="x"),
        ]
        pool, client = _make_mock_pool(messages)

        run_async(handle_message(pool, self._event(content=f"{BOT_MENTION} 帮我查一下", chat_type="group")))

        prompt = client.query.call_args[0][0]
        assert BOT_MENTION not in prompt
        assert "帮我查一下" in prompt

    @patch("src.handler.reply_message")
    @patch("src.handler.remove_reaction")
    @patch("src.handler.add_reaction", return_value="r_abc")
    def test_concurrent_sessions_get_different_clients(self, mock_add, mock_remove, mock_reply):
        """两个并发 session 从 pool 获取不同 client"""
        messages_a = [
            AssistantMessage(content=[TextBlock(text="reply_A")], model="sonnet"),
            ResultMessage(subtype="result", duration_ms=100, duration_api_ms=80, is_error=False, num_turns=1, session_id="x"),
        ]
        messages_b = [
            AssistantMessage(content=[TextBlock(text="reply_B")], model="sonnet"),
            ResultMessage(subtype="result", duration_ms=100, duration_api_ms=80, is_error=False, num_turns=1, session_id="x"),
        ]

        client_a = MagicMock()
        client_a.query = AsyncMock()
        async def recv_a():
            for m in messages_a: yield m
        client_a.receive_response = recv_a

        client_b = MagicMock()
        client_b.query = AsyncMock()
        async def recv_b():
            for m in messages_b: yield m
        client_b.receive_response = recv_b

        clients = {"p2p_" + OWNER_ID: client_a, "p2p_ou_other": client_b}
        pool = MagicMock(spec=ClientPool)
        pool.get = AsyncMock(side_effect=lambda sid: clients[sid])
        pool.get_claude_session_id = MagicMock(return_value=None)
        pool.save_claude_session_id = MagicMock()

        async def run():
            event_a = {"content": "hello_a", "message_id": "om_a", "sender_id": OWNER_ID, "chat_type": "p2p"}
            event_b = {"content": "hello_b", "message_id": "om_b", "sender_id": "ou_other", "chat_type": "p2p"}
            await asyncio.gather(
                handle_message(pool, event_a),
                handle_message(pool, event_b),
            )

        run_async(run())

        calls = mock_reply.call_args_list
        reply_map = {c[0][0]: c[0][1] for c in calls}
        assert reply_map.get("om_a") == "reply_A"
        assert reply_map.get("om_b") == "reply_B"


class TestParseCommand:
    """parse_command 解析 / 开头的指令"""

    def test_parse_command_clear(self):
        from src.handler import parse_command
        assert parse_command("/clear") == "clear"

    def test_parse_command_unknown(self):
        from src.handler import parse_command
        assert parse_command("/unknown") is None

    def test_parse_command_normal_message(self):
        from src.handler import parse_command
        assert parse_command("hello world") is None

    def test_parse_command_with_args(self):
        from src.handler import parse_command
        assert parse_command("/status some args") == "status"

    def test_parse_command_case_insensitive(self):
        from src.handler import parse_command
        assert parse_command("/CLEAR") == "clear"


class TestHandleCommand:
    """handle_command 处理指令，直接回复飞书"""

    def _event(self, content="/clear", sender_id=None, chat_type="p2p"):
        return {
            "content": content,
            "message_id": "om_cmd",
            "sender_id": sender_id or OWNER_ID,
            "chat_type": chat_type,
        }

    @patch("src.handler.reply_message")
    def test_handle_command_clear_removes_session(self, mock_reply):
        from src.handler import handle_command
        pool = MagicMock(spec=ClientPool)
        pool.remove = AsyncMock(return_value=True)
        metrics = MagicMock()

        run_async(handle_command(pool, metrics, self._event(), "clear"))

        pool.remove.assert_called_once()
        mock_reply.assert_called_once_with("om_cmd", "已清除当前会话。下次发消息将开始新对话。")

    @patch("src.handler.reply_message")
    def test_handle_command_clear_no_session(self, mock_reply):
        from src.handler import handle_command
        pool = MagicMock(spec=ClientPool)
        pool.remove = AsyncMock(return_value=False)
        metrics = MagicMock()

        run_async(handle_command(pool, metrics, self._event(), "clear"))

        mock_reply.assert_called_once_with("om_cmd", "当前没有活跃会话。")

    @patch("src.handler.reply_message")
    def test_handle_command_sessions_non_owner(self, mock_reply):
        from src.handler import handle_command
        pool = MagicMock(spec=ClientPool)
        metrics = MagicMock()

        run_async(handle_command(pool, metrics, self._event(sender_id="ou_non_owner"), "sessions"))

        mock_reply.assert_called_once_with("om_cmd", "仅所有者可查看 session 列表。")

    @patch("src.handler.reply_message")
    def test_handle_command_status_non_owner(self, mock_reply):
        from src.handler import handle_command
        pool = MagicMock(spec=ClientPool)
        metrics = MagicMock()

        run_async(handle_command(pool, metrics, self._event(sender_id="ou_non_owner"), "status"))

        mock_reply.assert_called_once_with("om_cmd", "仅所有者可查看系统状态。")
