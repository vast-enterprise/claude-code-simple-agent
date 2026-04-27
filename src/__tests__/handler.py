"""handler 模块测试：send_message + session_reader"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from src.handler import should_respond, send_message, session_reader, compute_session_id, _build_prompt, BOT_MENTION
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


class TestBuildPrompt:
    """_build_prompt: 构造带发送者上下文的 prompt"""

    def _pool_with_store(self, session_data: dict):
        pool = MagicMock()
        pool._store.load_all.return_value = session_data
        return pool

    def test_owner_p2p_with_name(self):
        pool = self._pool_with_store({"p2p_owner": {"sender_name": "郭凯南"}})
        event = {"sender_id": OWNER_ID, "chat_type": "p2p", "chat_id": ""}
        result = _build_prompt(pool, event, "p2p_owner", "你好")
        assert "所有者" in result
        assert "郭凯南" in result
        assert OWNER_ID in result
        assert "私聊" in result
        assert "你好" in result

    def test_colleague_group_with_names(self):
        pool = self._pool_with_store({
            "group_oc_xyz_ou_def": {"sender_name": "张三", "chat_name": "CMS群"},
        })
        event = {"sender_id": "ou_def", "chat_type": "group", "chat_id": "oc_xyz"}
        result = _build_prompt(pool, event, "group_oc_xyz_ou_def", "帮我查")
        assert "同事" in result
        assert "张三" in result
        assert "ou_def" in result
        assert "CMS群" in result
        assert "oc_xyz" in result

    def test_no_store_fallback(self):
        pool = MagicMock()
        pool._store = None
        event = {"sender_id": "ou_new", "chat_type": "p2p", "chat_id": ""}
        result = _build_prompt(pool, event, "p2p_ou_new", "测试")
        assert "同事" in result
        assert "ou_new" in result
        assert "测试" in result

    def test_group_without_chat_name(self):
        pool = self._pool_with_store({"group_oc_abc_ou_x": {}})
        event = {"sender_id": "ou_x", "chat_type": "group", "chat_id": "oc_abc"}
        result = _build_prompt(pool, event, "group_oc_abc_ou_x", "hi")
        assert "群聊" in result
        assert "oc_abc" in result


class TestSendMessage:
    """send_message 接受 session_id + content，立即 query + 入队 FIFO"""

    @patch("src.handler.reply_message")
    def test_query_called_and_enqueued(self, mock_reply):
        pool, client = _make_mock_pool()
        run_async(send_message(pool, _event(), "p2p_test", "hello"))
        client.query.assert_called_once()
        pool.enqueue_message.assert_called_once()
        mock_reply.assert_not_called()

    @patch("src.handler.reply_message")
    def test_resumes_with_stored_session_id(self, mock_reply):
        pool, client = _make_mock_pool(claude_session_id="stored_123")
        run_async(send_message(pool, _event(), "p2p_test", "hello"))
        _, kwargs = client.query.call_args
        assert kwargs["session_id"] == "stored_123"

    @patch("src.handler.reply_message")
    def test_slash_command_sent_raw(self, mock_reply):
        pool, client = _make_mock_pool()
        run_async(send_message(pool, _event(), "p2p_test", "/status"))
        prompt = client.query.call_args[0][0]
        assert prompt == "/status"

    @patch("src.handler.reply_message")
    def test_normal_message_has_prefix(self, mock_reply):
        pool, client = _make_mock_pool()
        run_async(send_message(pool, _event(), "p2p_test", "hello"))
        prompt = client.query.call_args[0][0]
        assert "所有者" in prompt
        assert "hello" in prompt

    @patch("src.handler.reply_message")
    def test_skips_empty_content(self, mock_reply):
        pool, _ = _make_mock_pool()
        run_async(send_message(pool, _event(), "p2p_test", ""))
        pool.get.assert_not_called()

    @patch("src.handler.reply_message")
    def test_sets_processing_true_after_successful_query(self, mock_reply):
        """成功 query 后 pool.set_processing(session_id, True) 被调用一次。"""
        pool, client = _make_mock_pool()

        run_async(send_message(pool, _event(sender_id="ou_proc_user"), "p2p_ou_proc_user", "hello"))

        pool.set_processing.assert_called_once_with("p2p_ou_proc_user", True)

    @patch("src.handler.reply_message")
    def test_set_processing_called_after_query_and_before_enqueue(self, mock_reply):
        """调用顺序：client.query -> pool.set_processing -> pool.enqueue_message。"""
        pool, client = _make_mock_pool()

        # 用 parent mock 统一捕获所有相关调用顺序
        parent = MagicMock()
        parent.attach_mock(client.query, "query")
        parent.attach_mock(pool.set_processing, "set_processing")
        parent.attach_mock(pool.enqueue_message, "enqueue_message")

        run_async(send_message(pool, _event(), "p2p_test", "hello"))

        names = [call[0] for call in parent.mock_calls]
        assert "query" in names
        assert "set_processing" in names
        assert "enqueue_message" in names
        # query 必须先于 set_processing，set_processing 必须先于 enqueue_message
        assert names.index("query") < names.index("set_processing")
        assert names.index("set_processing") < names.index("enqueue_message")

    @patch("src.handler.reply_message")
    def test_set_processing_not_called_when_query_raises(self, mock_reply):
        """client.query 抛异常时，set_processing 不应被调用。"""
        pool, client = _make_mock_pool()
        client.query = AsyncMock(side_effect=RuntimeError("boom"))

        run_async(send_message(pool, _event(), "p2p_test", "hello"))

        pool.set_processing.assert_not_called()
        pool.enqueue_message.assert_not_called()
        # 走的是 except 分支：回复了错误提示
        mock_reply.assert_called_once()

    @patch("src.handler.reply_message")
    def test_set_processing_not_called_when_pool_get_raises(self, mock_reply):
        """pool.get 抛异常时，set_processing 不应被调用。"""
        pool, client = _make_mock_pool()
        pool.get = AsyncMock(side_effect=RuntimeError("pool exhausted"))

        run_async(send_message(pool, _event(), "p2p_test", "hello"))

        pool.set_processing.assert_not_called()
        pool.enqueue_message.assert_not_called()
        mock_reply.assert_called_once()

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
    def test_dequeues_one_per_result(self, mock_add, mock_remove, mock_reply):
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

    @patch("src.handler.reply_message")
    @patch("src.handler.remove_reaction")
    @patch("src.handler.add_reaction", return_value="r_abc")
    def test_reply_with_suffix_prefix(self, mock_add, mock_remove, mock_reply):
        messages = [
            AssistantMessage(content=[TextBlock(text="回复内容")], model="sonnet"),
            ResultMessage(subtype="result", duration_ms=100, duration_api_ms=80,
                          is_error=False, num_turns=1, session_id="x"),
        ]
        pending = {"message_id": "om_test", "content": "hello"}
        pool = self._setup_reader(messages, pending)
        run_async(session_reader("p2p_test_cms", pool, suffix="cms"))
        mock_reply.assert_called_once()
        reply_text = mock_reply.call_args[0][1]
        assert reply_text.startswith("来自 cms 的回复：")
        assert "回复内容" in reply_text

    @patch("src.handler.reply_message")
    @patch("src.handler.remove_reaction")
    @patch("src.handler.add_reaction", return_value="r_abc")
    def test_reply_without_suffix_no_prefix(self, mock_add, mock_remove, mock_reply):
        messages = [
            AssistantMessage(content=[TextBlock(text="回复内容")], model="sonnet"),
            ResultMessage(subtype="result", duration_ms=100, duration_api_ms=80,
                          is_error=False, num_turns=1, session_id="x"),
        ]
        pending = {"message_id": "om_test", "content": "hello"}
        pool = self._setup_reader(messages, pending)
        run_async(session_reader("p2p_test", pool, suffix=None))
        mock_reply.assert_called_once_with("om_test", "回复内容")

    @patch("src.handler.reply_message")
    @patch("src.handler.remove_reaction")
    @patch("src.handler.add_reaction", return_value="r_abc")
    def test_sets_processing_false_on_result_message(self, mock_add, mock_remove, mock_reply):
        """ResultMessage 到达时 pool.set_processing(session_id, False) 被调用恰好一次。"""
        messages = [
            AssistantMessage(content=[TextBlock(text="回复")], model="sonnet"),
            ResultMessage(subtype="result", duration_ms=100, duration_api_ms=80, is_error=False, num_turns=1, session_id="x"),
        ]
        pending = {"message_id": "om_test", "content": "hello"}
        pool = self._setup_reader(messages, pending)

        run_async(session_reader("p2p_test", pool))

        # set_processing(sid, False) 必须在一次 turn 完成后被调用一次
        false_calls = [c for c in pool.set_processing.call_args_list if c.args[1] is False]
        assert len(false_calls) == 1, f"expected 1 False flip, got {pool.set_processing.call_args_list}"
        assert false_calls[0].args[0] == "p2p_test"

    @patch("src.handler.reply_message")
    @patch("src.handler.remove_reaction")
    @patch("src.handler.add_reaction", return_value="r_abc")
    def test_sets_processing_false_on_exception(self, mock_add, mock_remove, mock_reply):
        """reader 的 async-for 抛异常时也必须把 session 翻回 READY。"""
        pool, client = _make_mock_pool()

        async def failing_receive():
            # 先 yield 一个 AssistantMessage 让 reader 进到循环体，再抛异常
            yield AssistantMessage(content=[TextBlock(text="部分回复")], model="sonnet")
            raise RuntimeError("upstream boom")

        client.receive_response = failing_receive

        call_count = [0]
        def get_client_once(sid):
            call_count[0] += 1
            return client if call_count[0] <= 1 else None
        pool.get_client = MagicMock(side_effect=get_client_once)

        pending = {"message_id": "om_test", "content": "hello"}
        pool.peek_pending = MagicMock(return_value=pending)
        pool.dequeue_message = MagicMock(return_value=pending)

        run_async(session_reader("p2p_test", pool))

        false_calls = [c for c in pool.set_processing.call_args_list if c.args[1] is False]
        assert len(false_calls) == 1, f"expected exactly 1 False flip on exception path, got {pool.set_processing.call_args_list}"
        assert false_calls[0].args[0] == "p2p_test"

    @patch("src.handler.reply_message")
    @patch("src.handler.remove_reaction")
    @patch("src.handler.add_reaction", return_value="r_abc")
    def test_sets_processing_false_on_cancellation(self, mock_add, mock_remove, mock_reply):
        """reader task 被 cancel（/clear、eviction、shutdown）时，必须翻回 READY 并把
        CancelledError 向上抛，让 _reader_wrapper 能正常清理。
        """
        pool, client = _make_mock_pool()

        async def hung_generator():
            # 先 yield 一个 AssistantMessage 让 reader 进入 try 块
            yield AssistantMessage(content=[TextBlock(text="部分")], model="sonnet")
            # 然后无限挂起，等待外部 cancel
            await asyncio.Event().wait()

        client.receive_response = hung_generator

        call_count = [0]
        def get_client_once(sid):
            call_count[0] += 1
            return client if call_count[0] <= 1 else None
        pool.get_client = MagicMock(side_effect=get_client_once)

        pending = {"message_id": "om_test", "content": "hello"}
        pool.peek_pending = MagicMock(return_value=pending)

        async def run():
            task = asyncio.create_task(session_reader("p2p_test", pool))
            # 让 task 进入 async for 并挂起在 Event().wait()
            await asyncio.sleep(0.01)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

        run_async(run())

        # (b) False flip 必须在 CancelledError 向上抛之前发生
        false_calls = [
            c for c in pool.set_processing.call_args_list
            if c == call("p2p_test", False)
        ]
        assert len(false_calls) == 1, (
            f"expected exactly 1 False flip on cancellation, got {pool.set_processing.call_args_list}"
        )

    @patch("src.handler.reply_message")
    @patch("src.handler.remove_reaction")
    @patch("src.handler.add_reaction", return_value="r_abc")
    def test_skips_lark_side_effects_for_internal_message_id(
        self, mock_add, mock_remove, mock_reply
    ):
        """message_id 以 "internal-" 开头（控制平面虚构 ID）时，
        reader 必须跳过所有 lark 副作用（add/remove_reaction、reply_message），
        但核心状态机仍要推进：dequeue_message + set_processing(False)。
        """
        messages = [
            AssistantMessage(content=[TextBlock(text="Claude 回复")], model="sonnet"),
            ResultMessage(
                subtype="result", duration_ms=100, duration_api_ms=80,
                is_error=False, num_turns=1, session_id="x",
            ),
        ]
        pending = {"message_id": "internal-abc123", "content": "hi"}
        pool = self._setup_reader(messages, pending)

        run_async(session_reader("p2p_ou_owner_REQ-1", pool, suffix="REQ-1"))

        # 所有 lark 副作用都必须跳过
        mock_add.assert_not_called()
        mock_remove.assert_not_called()
        mock_reply.assert_not_called()

        # 但核心状态机照常推进
        pool.dequeue_message.assert_called_once_with("p2p_ou_owner_REQ-1")
        false_calls = [c for c in pool.set_processing.call_args_list if c.args[1] is False]
        assert len(false_calls) == 1

    @patch("src.handler.reply_message")
    @patch("src.handler.remove_reaction")
    @patch("src.handler.add_reaction", return_value="r_abc")
    def test_sets_processing_false_once_per_turn_not_on_next_assistant(
        self, mock_add, mock_remove, mock_reply
    ):
        """多条消息在同一个 async-for 中流动时，False 翻转按 turn 计数（每个 ResultMessage 一次），
        不因为下一个 turn 开始时的 AssistantMessage 而多翻一次。"""
        messages = [
            # 第一个 turn
            AssistantMessage(content=[TextBlock(text="回复1")], model="sonnet"),
            ResultMessage(subtype="result", duration_ms=100, duration_api_ms=80, is_error=False, num_turns=1, session_id="x"),
            # 第二个 turn（新 AssistantMessage，但这里不产出 ResultMessage）
            AssistantMessage(content=[TextBlock(text="回复2中...")], model="sonnet"),
        ]
        pending = {"message_id": "om_test", "content": "hello"}
        pool = self._setup_reader(messages, pending)

        run_async(session_reader("p2p_test", pool))

        # 只有 1 个 ResultMessage，所以只有 1 次 False
        false_calls = [c for c in pool.set_processing.call_args_list if c.args[1] is False]
        assert len(false_calls) == 1, (
            f"expected exactly 1 False flip (per ResultMessage, not per AssistantMessage), "
            f"got {pool.set_processing.call_args_list}"
        )


# ── echo_chat_id 分支测试 ──────────────────────────────────────────

def _make_mock_pool_with_store(store_data: dict | None = None):
    """构造 mock pool，并配置带 store 支持的版本"""
    pool, client = _make_mock_pool()
    store = MagicMock()
    store.load_all = MagicMock(return_value=store_data or {})
    pool._store = store
    return pool, client


class TestSessionReaderEcho:
    """session_reader echo_chat_id 分支：ResultMessage 时 send_to_target 被调"""

    def _setup_reader_with_store(self, messages, pending_entry, store_data):
        """构造 mock pool + store + client"""
        pool, client = _make_mock_pool_with_store(store_data)

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

    def _result_messages(self, text="回复内容"):
        return [
            AssistantMessage(content=[TextBlock(text=text)], model="sonnet"),
            ResultMessage(
                subtype="result", duration_ms=100, duration_api_ms=80,
                is_error=False, num_turns=1, session_id="x",
            ),
        ]

    @patch("src.handler.send_to_target")
    @patch("src.handler.reply_message")
    @patch("src.handler.remove_reaction")
    @patch("src.handler.add_reaction", return_value="r_abc")
    def test_reader_echo_on_result_message(
        self, mock_add, mock_remove, mock_reply, mock_send_to_target
    ):
        """store 里 echo_chat_id=ou_xxx，internal-* message_id → send_to_target 被调"""
        session_id = "p2p_ou_owner_REQ-1"
        store_data = {session_id: {"echo_chat_id": "ou_xxx"}}
        pending = {"message_id": f"internal-{session_id}", "content": "hi"}
        pool = self._setup_reader_with_store(
            self._result_messages(), pending, store_data
        )
        run_async(session_reader(session_id, pool, suffix="REQ-1"))
        mock_send_to_target.assert_called_once()
        call_args = mock_send_to_target.call_args
        assert call_args.args[0] == "ou_xxx"

    @patch("src.handler.send_to_target")
    @patch("src.handler.reply_message")
    @patch("src.handler.remove_reaction")
    @patch("src.handler.add_reaction", return_value="r_abc")
    def test_reader_no_echo_when_target_empty(
        self, mock_add, mock_remove, mock_reply, mock_send_to_target
    ):
        """store 里 echo_chat_id="" → send_to_target 不调"""
        session_id = "p2p_ou_owner_REQ-2"
        store_data = {session_id: {"echo_chat_id": ""}}
        pending = {"message_id": f"internal-uuid", "content": "hi"}
        pool = self._setup_reader_with_store(
            self._result_messages(), pending, store_data
        )
        run_async(session_reader(session_id, pool))
        mock_send_to_target.assert_not_called()

    @patch("src.handler.send_to_target")
    @patch("src.handler.reply_message")
    @patch("src.handler.remove_reaction")
    @patch("src.handler.add_reaction", return_value="r_abc")
    def test_reader_echoes_to_owner_when_target_missing(
        self, mock_add, mock_remove, mock_reply, mock_send_to_target
    ):
        """store 里没有 echo_chat_id 字段（旧 session）→ 默认回传 OWNER_ID"""
        session_id = "p2p_ou_owner_REQ-3"
        store_data = {session_id: {}}  # 无 echo_chat_id 键
        pending = {"message_id": "internal-uuid2", "content": "hi"}
        pool = self._setup_reader_with_store(
            self._result_messages(), pending, store_data
        )
        run_async(session_reader(session_id, pool))
        mock_send_to_target.assert_called_once()
        call_args = mock_send_to_target.call_args
        assert call_args.args[0] == OWNER_ID

    @patch("src.handler.send_to_target")
    @patch("src.handler.reply_message")
    @patch("src.handler.remove_reaction")
    @patch("src.handler.add_reaction", return_value="r_abc")
    def test_reader_echo_with_suffix_prefix(
        self, mock_add, mock_remove, mock_reply, mock_send_to_target
    ):
        """suffix=REQ-foo → echo 文本带 `来自 REQ-foo 的回复：\n` 前缀"""
        session_id = "p2p_ou_owner_REQ-foo"
        store_data = {session_id: {"echo_chat_id": "ou_target"}}
        pending = {"message_id": "internal-uuid3", "content": "hi"}
        pool = self._setup_reader_with_store(
            self._result_messages("具体内容"), pending, store_data
        )
        run_async(session_reader(session_id, pool, suffix="REQ-foo"))
        mock_send_to_target.assert_called_once()
        sent_text = mock_send_to_target.call_args.args[1]
        assert sent_text.startswith("来自 REQ-foo 的回复：")
        assert "具体内容" in sent_text

    @patch("src.handler.send_to_target")
    @patch("src.handler.reply_message")
    @patch("src.handler.remove_reaction")
    @patch("src.handler.add_reaction", return_value="r_abc")
    def test_reader_echo_not_triggered_on_assistant_message(
        self, mock_add, mock_remove, mock_reply, mock_send_to_target
    ):
        """仅 AssistantMessage 出现（无 ResultMessage）→ send_to_target 不调"""
        session_id = "p2p_ou_owner_REQ-4"
        store_data = {session_id: {"echo_chat_id": "ou_target"}}
        pending = {"message_id": "internal-uuid4", "content": "hi"}
        # 只有 AssistantMessage，没有 ResultMessage
        messages = [AssistantMessage(content=[TextBlock(text="中间回复")], model="sonnet")]
        pool = self._setup_reader_with_store(messages, pending, store_data)
        run_async(session_reader(session_id, pool))
        mock_send_to_target.assert_not_called()

    @patch("src.handler.send_to_target")
    @patch("src.handler.reply_message")
    @patch("src.handler.remove_reaction")
    @patch("src.handler.add_reaction", return_value="r_abc")
    def test_reader_echo_not_triggered_on_exception(
        self, mock_add, mock_remove, mock_reply, mock_send_to_target
    ):
        """reader 抛异常路径 → send_to_target 不调"""
        session_id = "p2p_ou_owner_REQ-5"
        store_data = {session_id: {"echo_chat_id": "ou_target"}}
        pending = {"message_id": "om_real", "content": "hi"}

        pool, client = _make_mock_pool_with_store(store_data)

        async def failing_receive():
            yield AssistantMessage(content=[TextBlock(text="部分")], model="sonnet")
            raise RuntimeError("boom")

        client.receive_response = failing_receive
        call_count = [0]
        def get_client_once(sid):
            call_count[0] += 1
            return client if call_count[0] <= 1 else None
        pool.get_client = MagicMock(side_effect=get_client_once)
        pool.peek_pending = MagicMock(return_value=pending)
        pool.dequeue_message = MagicMock(return_value=pending)

        run_async(session_reader(session_id, pool))
        mock_send_to_target.assert_not_called()

    @patch("src.handler.send_to_target", side_effect=Exception("send failed"))
    @patch("src.handler.reply_message")
    @patch("src.handler.remove_reaction")
    @patch("src.handler.add_reaction", return_value="r_abc")
    def test_reader_echo_failure_does_not_break_state_machine(
        self, mock_add, mock_remove, mock_reply, mock_send_to_target
    ):
        """send_to_target 失败（log_error）但 set_processing(False) 仍正常翻转"""
        session_id = "p2p_ou_owner_REQ-6"
        store_data = {session_id: {"echo_chat_id": "ou_target"}}
        pending = {"message_id": "internal-uuid6", "content": "hi"}
        pool = self._setup_reader_with_store(
            self._result_messages(), pending, store_data
        )
        run_async(session_reader(session_id, pool, suffix="REQ-6"))
        # 状态机仍正常翻转
        false_calls = [c for c in pool.set_processing.call_args_list if c.args[1] is False]
        assert len(false_calls) == 1
