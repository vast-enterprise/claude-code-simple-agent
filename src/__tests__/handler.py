"""handler 模块测试：send_message + session_reader"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.handler import should_respond, send_message, session_reader, compute_session_id, BOT_MENTION
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


def _make_mock_pool(claude_session_id=None):
    """构造 mock pool：pool.get() 返回一个 mock client"""
    client = MagicMock()
    client.query = AsyncMock()

    pool = MagicMock(spec=ClientPool)
    pool.get = AsyncMock(return_value=client)
    pool.get_client = MagicMock(return_value=client)
    pool.get_claude_session_id = MagicMock(return_value=claude_session_id)
    pool.save_claude_session_id = MagicMock()
    pool.enqueue_message = MagicMock()
    pool.peek_pending = MagicMock(return_value=None)
    pool.dequeue_message = MagicMock(return_value=None)
    pool.has_pending = MagicMock(return_value=False)
    pool.remove = AsyncMock(return_value=True)
    pool._store = None  # 跳过 display name 解析
    return pool, client


def _event(content="hello", sender_id=None, chat_type="p2p"):
    return {
        "content": content,
        "message_id": "om_test",
        "sender_id": sender_id or OWNER_ID,
        "chat_type": chat_type,
    }


class TestSendMessage:
    """send_message 立即 query + 入队 FIFO"""

    @patch("src.handler.reply_message")
    def test_query_called_and_enqueued(self, mock_reply):
        pool, client = _make_mock_pool()

        run_async(send_message(pool, _event()))

        client.query.assert_called_once()
        pool.enqueue_message.assert_called_once()
        # 普通消息不直接 reply
        mock_reply.assert_not_called()

    @patch("src.handler.reply_message")
    def test_routes_to_correct_session(self, mock_reply):
        pool, client = _make_mock_pool()

        run_async(send_message(pool, _event(sender_id="ou_user_123")))

        pool.get.assert_called_once_with("p2p_ou_user_123")
        pool.enqueue_message.assert_called_once()
        args = pool.enqueue_message.call_args[0]
        assert args[0] == "p2p_ou_user_123"  # session_id
        assert args[1] == "om_test"  # message_id

    @patch("src.handler.reply_message")
    def test_resumes_with_stored_session_id(self, mock_reply):
        pool, client = _make_mock_pool(claude_session_id="stored_123")

        run_async(send_message(pool, _event()))

        _, kwargs = client.query.call_args
        assert kwargs["session_id"] == "stored_123"

    @patch("src.handler.reply_message")
    def test_slash_command_sent_raw(self, mock_reply):
        pool, client = _make_mock_pool()

        run_async(send_message(pool, _event(content="/status")))

        prompt = client.query.call_args[0][0]
        assert prompt == "/status"

    @patch("src.handler.reply_message")
    def test_normal_message_has_prefix(self, mock_reply):
        pool, client = _make_mock_pool()

        run_async(send_message(pool, _event(content="hello")))

        prompt = client.query.call_args[0][0]
        assert "所有者" in prompt
        assert "hello" in prompt

    @patch("src.handler.reply_message")
    def test_cleans_at_mention(self, mock_reply):
        pool, client = _make_mock_pool()

        run_async(send_message(pool, _event(content=f"{BOT_MENTION} 帮我查一下", chat_type="group")))

        prompt = client.query.call_args[0][0]
        assert BOT_MENTION not in prompt
        assert "帮我查一下" in prompt

    @patch("src.handler.reply_message")
    def test_skips_empty_content(self, mock_reply):
        pool, _ = _make_mock_pool()
        run_async(send_message(pool, _event(content="")))
        pool.get.assert_not_called()

    @patch("src.handler.reply_message")
    def test_clear_removes_session(self, mock_reply):
        pool, _ = _make_mock_pool()

        run_async(send_message(pool, _event(content="/clear")))

        pool.remove.assert_called_once()
        mock_reply.assert_called_once()
        assert "已清除" in mock_reply.call_args[0][1]

    @patch("src.handler.reply_message")
    def test_interrupt_calls_client_interrupt(self, mock_reply):
        pool, client = _make_mock_pool()
        client.interrupt = AsyncMock()

        run_async(send_message(pool, _event(content="/interrupt")))

        client.interrupt.assert_called_once()
        mock_reply.assert_called_once()
        assert "已中断" in mock_reply.call_args[0][1]

    @patch("src.handler.reply_message")
    def test_interrupt_no_client(self, mock_reply):
        pool, _ = _make_mock_pool()
        pool.get_client = MagicMock(return_value=None)

        run_async(send_message(pool, _event(content="/interrupt")))

        mock_reply.assert_called_once()
        assert "没有活跃任务" in mock_reply.call_args[0][1]

    @patch("src.handler.reply_message")
    def test_group_routes_correctly(self, mock_reply):
        pool, client = _make_mock_pool()

        event = _event(content=f"{BOT_MENTION} hello", chat_type="group")
        event["chat_id"] = "oc_group_456"
        run_async(send_message(pool, event))

        pool.get.assert_called_once_with(f"group_oc_group_456_{OWNER_ID}")


class TestSessionReader:
    """session_reader 后台持续读取 response 并回复飞书"""

    def _setup_reader(self, messages, pending_entry=None):
        """构造 mock pool + client，client.receive_response() 产出 messages。

        get_client 在第一次调用后返回 None，使 reader 在一轮后退出。
        """
        pool, client = _make_mock_pool()

        async def fake_receive():
            for msg in messages:
                yield msg

        client.receive_response = fake_receive

        call_count = [0]
        def get_client_once(sid):
            call_count[0] += 1
            return client if call_count[0] <= 1 else None
        pool.get_client = MagicMock(side_effect=get_client_once)

        if pending_entry:
            pool.peek_pending = MagicMock(return_value=pending_entry)
            pool.dequeue_message = MagicMock(return_value=pending_entry)
        return pool

    @patch("src.handler.reply_message")
    @patch("src.handler.remove_reaction")
    @patch("src.handler.add_reaction", return_value="r_abc")
    def test_full_flow_reaction_and_reply(self, mock_add, mock_remove, mock_reply):
        messages = [
            AssistantMessage(content=[TextBlock(text="回复内容")], model="sonnet"),
            ResultMessage(subtype="result", duration_ms=100, duration_api_ms=80, is_error=False, num_turns=1, session_id="x"),
        ]
        pending = {"message_id": "om_test", "content": "hello"}
        pool = self._setup_reader(messages, pending)

        run_async(session_reader("p2p_test", pool))

        mock_add.assert_called_once_with("om_test")
        mock_remove.assert_called_once_with("om_test", "r_abc")
        mock_reply.assert_called_once_with("om_test", "回复内容")

    @patch("src.handler.reply_message")
    @patch("src.handler.remove_reaction")
    @patch("src.handler.add_reaction", return_value=None)
    def test_error_result_replies_error(self, mock_add, mock_remove, mock_reply):
        messages = [
            ResultMessage(subtype="result", duration_ms=100, duration_api_ms=80, is_error=True, num_turns=0, session_id="x"),
        ]
        pending = {"message_id": "om_test", "content": "hello"}
        pool = self._setup_reader(messages, pending)

        run_async(session_reader("p2p_test", pool))

        mock_reply.assert_called_once_with("om_test", "抱歉，处理时出了点问题。")

    @patch("src.handler.reply_message")
    @patch("src.handler.remove_reaction")
    @patch("src.handler.add_reaction", return_value="r_abc")
    def test_saves_claude_session_id(self, mock_add, mock_remove, mock_reply):
        messages = [
            AssistantMessage(content=[TextBlock(text="ok")], model="sonnet", session_id="claude_abc"),
            ResultMessage(subtype="result", duration_ms=100, duration_api_ms=80, is_error=False, num_turns=1, session_id="claude_abc"),
        ]
        pending = {"message_id": "om_test", "content": "hello"}
        pool = self._setup_reader(messages, pending)

        run_async(session_reader("p2p_test", pool))

        pool.save_claude_session_id.assert_called_with("p2p_test", "claude_abc")

    @patch("src.handler.reply_message")
    @patch("src.handler.remove_reaction")
    @patch("src.handler.add_reaction", return_value="r_abc")
    def test_dequeues_after_result(self, mock_add, mock_remove, mock_reply):
        messages = [
            AssistantMessage(content=[TextBlock(text="ok")], model="sonnet"),
            ResultMessage(subtype="result", duration_ms=100, duration_api_ms=80, is_error=False, num_turns=1, session_id="x"),
        ]
        pending = {"message_id": "om_test", "content": "hello"}
        pool = self._setup_reader(messages, pending)

        run_async(session_reader("p2p_test", pool))

        pool.dequeue_message.assert_called_once_with("p2p_test")

    @patch("src.handler.reply_message")
    @patch("src.handler.remove_reaction")
    @patch("src.handler.add_reaction", return_value="r_abc")
    def test_records_metrics(self, mock_add, mock_remove, mock_reply):
        messages = [
            AssistantMessage(content=[TextBlock(text="ok")], model="sonnet"),
            ResultMessage(subtype="result", duration_ms=100, duration_api_ms=80, is_error=False, num_turns=1, session_id="x"),
        ]
        pending = {"message_id": "om_test", "content": "hello world"}
        pool = self._setup_reader(messages, pending)
        metrics = MagicMock()

        run_async(session_reader("p2p_test", pool, metrics=metrics))

        metrics.record_message.assert_called_once()
        args = metrics.record_message.call_args[0]
        assert args[0] == "p2p_test"  # session_id
        assert args[1] == "hello world"  # content
        assert args[2] is True  # success

    @patch("src.handler.reply_message")
    @patch("src.handler.add_reaction")
    def test_returns_when_no_client(self, mock_add, mock_reply):
        """reader 在 client 不存在时返回"""
        pool, _ = _make_mock_pool()
        pool.get_client = MagicMock(return_value=None)

        run_async(session_reader("p2p_test", pool))

        mock_add.assert_not_called()
        mock_reply.assert_not_called()
