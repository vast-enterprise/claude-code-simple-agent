"""handler 模块测试"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.handler import should_respond, handle_message, compute_session_id, BOT_MENTION
from src.config import OWNER_ID
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


class TestHandleMessage:
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
        client = MagicMock()
        client.query = AsyncMock()

        async def fake_response():
            yield AssistantMessage(content=[TextBlock(text="回复内容")], model="sonnet")
            yield ResultMessage(subtype="result", duration_ms=100, duration_api_ms=80, is_error=False, num_turns=1, session_id="default")

        client.receive_response = fake_response
        run_async(handle_message(client, self._event()))

        client.query.assert_called_once()
        mock_add.assert_called_once_with("om_test")
        mock_remove.assert_called_once_with("om_test", "r_abc")
        mock_reply.assert_called_once_with("om_test", "回复内容")

    @patch("src.handler.reply_message")
    @patch("src.handler.remove_reaction")
    @patch("src.handler.add_reaction", return_value="r_abc")
    def test_p2p_uses_sender_id_as_session(self, mock_add, mock_remove, mock_reply):
        client = MagicMock()
        client.query = AsyncMock()

        async def fake_response():
            yield AssistantMessage(content=[TextBlock(text="ok")], model="sonnet")
            yield ResultMessage(subtype="result", duration_ms=100, duration_api_ms=80, is_error=False, num_turns=1, session_id="default")

        client.receive_response = fake_response
        run_async(handle_message(client, self._event(sender_id="ou_user_123")))

        _, kwargs = client.query.call_args
        assert kwargs["session_id"] == "p2p_ou_user_123"

    @patch("src.handler.reply_message")
    @patch("src.handler.remove_reaction")
    @patch("src.handler.add_reaction", return_value="r_abc")
    def test_group_uses_chat_id_as_session(self, mock_add, mock_remove, mock_reply):
        client = MagicMock()
        client.query = AsyncMock()

        async def fake_response():
            yield AssistantMessage(content=[TextBlock(text="ok")], model="sonnet")
            yield ResultMessage(subtype="result", duration_ms=100, duration_api_ms=80, is_error=False, num_turns=1, session_id="default")

        client.receive_response = fake_response
        event = self._event(content=f"{BOT_MENTION} hello", chat_type="group")
        event["chat_id"] = "oc_group_456"
        run_async(handle_message(client, event))

        _, kwargs = client.query.call_args
        assert kwargs["session_id"] == "group_oc_group_456_" + OWNER_ID

    @patch("src.handler.reply_message")
    @patch("src.handler.remove_reaction")
    @patch("src.handler.add_reaction", return_value="r_abc")
    def test_group_without_chat_id_falls_back(self, mock_add, mock_remove, mock_reply):
        client = MagicMock()
        client.query = AsyncMock()

        async def fake_response():
            yield AssistantMessage(content=[TextBlock(text="ok")], model="sonnet")
            yield ResultMessage(subtype="result", duration_ms=100, duration_api_ms=80, is_error=False, num_turns=1, session_id="default")

        client.receive_response = fake_response
        run_async(handle_message(client, self._event(chat_type="group")))

        _, kwargs = client.query.call_args
        assert kwargs["session_id"] == "group_unknown_" + OWNER_ID

    @patch("src.handler.reply_message")
    @patch("src.handler.add_reaction")
    def test_skips_empty_content(self, mock_add, mock_reply):
        client = MagicMock()
        run_async(handle_message(client, self._event(content="")))
        client.query.assert_not_called()

    @patch("src.handler.reply_message")
    @patch("src.handler.remove_reaction")
    @patch("src.handler.add_reaction", return_value=None)
    def test_replies_error_on_failure(self, mock_add, mock_remove, mock_reply):
        client = MagicMock()
        client.query = AsyncMock()

        async def fake_error():
            yield ResultMessage(subtype="result", duration_ms=100, duration_api_ms=80, is_error=True, num_turns=0, session_id="default")

        client.receive_response = fake_error
        run_async(handle_message(client, self._event()))
        mock_reply.assert_called_once_with("om_test", "抱歉，处理时出了点问题。")
        mock_remove.assert_not_called()

    @patch("src.handler.reply_message")
    @patch("src.handler.remove_reaction")
    @patch("src.handler.add_reaction", return_value="r_abc")
    def test_cleans_at_mention_from_prompt(self, mock_add, mock_remove, mock_reply):
        client = MagicMock()
        client.query = AsyncMock()

        async def fake_response():
            yield AssistantMessage(content=[TextBlock(text="ok")], model="sonnet")
            yield ResultMessage(subtype="result", duration_ms=100, duration_api_ms=80, is_error=False, num_turns=1, session_id="default")

        client.receive_response = fake_response
        run_async(handle_message(client, self._event(content=f"{BOT_MENTION} 帮我查一下", chat_type="group")))

        prompt = client.query.call_args[0][0]
        assert BOT_MENTION not in prompt
        assert "帮我查一下" in prompt
