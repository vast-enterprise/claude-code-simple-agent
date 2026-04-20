"""pool 模块测试"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.pool import ClientPool


def run_async(coro):
    return asyncio.run(coro)


class TestClientPool:
    def _make_pool(self):
        options = MagicMock()
        pool = ClientPool(options)
        return pool

    @patch("src.pool.ClaudeSDKClient")
    def test_get_creates_and_connects_client(self, MockClient):
        mock_instance = MagicMock()
        mock_instance.connect = AsyncMock()
        MockClient.return_value = mock_instance

        pool = self._make_pool()

        async def run():
            client = await pool.get("session_a")
            assert client is mock_instance
            mock_instance.connect.assert_called_once()

        run_async(run())

    @patch("src.pool.ClaudeSDKClient")
    def test_get_reuses_existing_client(self, MockClient):
        mock_instance = MagicMock()
        mock_instance.connect = AsyncMock()
        MockClient.return_value = mock_instance

        pool = self._make_pool()

        async def run():
            c1 = await pool.get("session_a")
            c2 = await pool.get("session_a")
            assert c1 is c2
            # connect 只调一次
            assert mock_instance.connect.call_count == 1

        run_async(run())

    @patch("src.pool.ClaudeSDKClient")
    def test_different_sessions_get_different_clients(self, MockClient):
        instances = []
        def make_client(**kwargs):
            m = MagicMock()
            m.connect = AsyncMock()
            instances.append(m)
            return m
        MockClient.side_effect = make_client

        pool = self._make_pool()

        async def run():
            c1 = await pool.get("session_a")
            c2 = await pool.get("session_b")
            assert c1 is not c2
            assert len(instances) == 2

        run_async(run())

    @patch("src.pool.ClaudeSDKClient")
    def test_shutdown_disconnects_all(self, MockClient):
        instances = []
        def make_client(**kwargs):
            m = MagicMock()
            m.connect = AsyncMock()
            m.disconnect = AsyncMock()
            instances.append(m)
            return m
        MockClient.side_effect = make_client

        pool = self._make_pool()

        async def run():
            await pool.get("a")
            await pool.get("b")
            await pool.shutdown()
            for inst in instances:
                inst.disconnect.assert_called_once()

        run_async(run())

    @patch("src.pool.ClaudeSDKClient")
    def test_concurrent_get_same_session_only_creates_once(self, MockClient):
        """并发 get 同一 session 不会重复创建"""
        call_count = 0
        async def slow_connect():
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.01)

        mock_instance = MagicMock()
        mock_instance.connect = AsyncMock(side_effect=slow_connect)
        MockClient.return_value = mock_instance

        pool = self._make_pool()

        async def run():
            results = await asyncio.gather(
                pool.get("same"),
                pool.get("same"),
                pool.get("same"),
            )
            assert all(r is mock_instance for r in results)
            assert call_count == 1

        run_async(run())


class TestClientPoolFIFO:
    """per-session 消息 FIFO 测试"""

    def _make_pool(self):
        return ClientPool(MagicMock())

    def test_enqueue_and_peek(self):
        pool = self._make_pool()
        pool.enqueue_message("s1", "om_1", "hello")

        entry = pool.peek_pending("s1")
        assert entry is not None
        assert entry["message_id"] == "om_1"
        assert entry["content"] == "hello"
        assert "timestamp" in entry

    def test_dequeue_returns_and_removes(self):
        pool = self._make_pool()
        pool.enqueue_message("s1", "om_1", "hello")

        entry = pool.dequeue_message("s1")
        assert entry["message_id"] == "om_1"
        assert pool.peek_pending("s1") is None

    def test_fifo_order(self):
        pool = self._make_pool()
        pool.enqueue_message("s1", "om_1", "first")
        pool.enqueue_message("s1", "om_2", "second")

        assert pool.dequeue_message("s1")["message_id"] == "om_1"
        assert pool.dequeue_message("s1")["message_id"] == "om_2"

    def test_different_sessions_independent(self):
        pool = self._make_pool()
        pool.enqueue_message("s1", "om_1", "hello")
        pool.enqueue_message("s2", "om_2", "world")

        assert pool.peek_pending("s1")["message_id"] == "om_1"
        assert pool.peek_pending("s2")["message_id"] == "om_2"

    def test_has_pending(self):
        pool = self._make_pool()
        assert pool.has_pending("s1") is False
        pool.enqueue_message("s1", "om_1", "hello")
        assert pool.has_pending("s1") is True
        pool.dequeue_message("s1")
        assert pool.has_pending("s1") is False

    def test_peek_empty_returns_none(self):
        pool = self._make_pool()
        assert pool.peek_pending("s1") is None

    def test_dequeue_empty_returns_none(self):
        pool = self._make_pool()
        assert pool.dequeue_message("s1") is None

    def test_pending_count(self):
        pool = self._make_pool()
        assert pool.pending_count("s1") == 0
        pool.enqueue_message("s1", "om_1", "a")
        pool.enqueue_message("s1", "om_2", "b")
        assert pool.pending_count("s1") == 2

    def test_dequeue_batch(self):
        pool = self._make_pool()
        pool.enqueue_message("s1", "om_1", "a")
        pool.enqueue_message("s1", "om_2", "b")
        pool.enqueue_message("s1", "om_3", "c")

        batch = pool.dequeue_batch("s1", 2)
        assert len(batch) == 2
        assert batch[0]["message_id"] == "om_1"
        assert batch[1]["message_id"] == "om_2"
        assert pool.pending_count("s1") == 1

    def test_dequeue_batch_more_than_available(self):
        pool = self._make_pool()
        pool.enqueue_message("s1", "om_1", "a")
        batch = pool.dequeue_batch("s1", 5)
        assert len(batch) == 1
        assert pool.pending_count("s1") == 0

    def test_dequeue_batch_empty(self):
        pool = self._make_pool()
        batch = pool.dequeue_batch("s1", 3)
        assert batch == []

    def test_get_client_returns_none_when_no_client(self):
        pool = self._make_pool()
        assert pool.get_client("s1") is None

    @patch("src.pool.ClaudeSDKClient")
    def test_get_client_returns_existing(self, MockClient):
        mock_instance = MagicMock()
        mock_instance.connect = AsyncMock()
        MockClient.return_value = mock_instance

        pool = self._make_pool()

        async def run():
            await pool.get("s1")
            assert pool.get_client("s1") is mock_instance

        run_async(run())

    @patch("src.pool.ClaudeSDKClient")
    def test_remove_clears_pending(self, MockClient):
        mock_instance = MagicMock()
        mock_instance.connect = AsyncMock()
        mock_instance.disconnect = AsyncMock()
        MockClient.return_value = mock_instance

        pool = self._make_pool()

        async def run():
            await pool.get("s1")
            pool.enqueue_message("s1", "om_1", "hello")
            await pool.remove("s1")
            assert pool.has_pending("s1") is False

        run_async(run())

    def test_shutdown_clears_pending(self):
        pool = self._make_pool()
        pool.enqueue_message("s1", "om_1", "hello")

        async def run():
            await pool.shutdown()

        run_async(run())
        assert pool.has_pending("s1") is False


class TestClientPoolWithStore:
    """ClientPool + SessionStore 集成测试"""

    def _make_store(self):
        """创建一个 mock SessionStore"""
        store = MagicMock()
        store.save = MagicMock()
        store.update_active = MagicMock()
        store.remove = MagicMock(side_effect=lambda sid: sid in ("s1", "s2"))
        store.load_all = MagicMock(return_value={"s1": {"message_count": 3}, "s2": {"message_count": 1}})
        return store

    @patch("src.pool.ClaudeSDKClient")
    def test_get_saves_to_store(self, MockClient):
        """get() 新建 client 时 store.save 被调用"""
        mock_instance = MagicMock()
        mock_instance.connect = AsyncMock()
        MockClient.return_value = mock_instance

        store = self._make_store()
        pool = ClientPool(MagicMock(), store=store)

        async def run():
            await pool.get("session_x")
            store.save.assert_called_once_with("session_x", {})

        run_async(run())

    @patch("src.pool.ClaudeSDKClient")
    def test_get_updates_active(self, MockClient):
        """get() 时 store.update_active 被调用"""
        mock_instance = MagicMock()
        mock_instance.connect = AsyncMock()
        MockClient.return_value = mock_instance

        store = self._make_store()
        pool = ClientPool(MagicMock(), store=store)

        async def run():
            await pool.get("session_x")
            store.update_active.assert_called_once_with("session_x")
            # 再次 get 同一 session，update_active 应被调用第二次
            await pool.get("session_x")
            assert store.update_active.call_count == 2

        run_async(run())

    @patch("src.pool.ClaudeSDKClient")
    def test_remove_disconnects_and_removes(self, MockClient):
        """remove() 断开 client + 从 store 删除"""
        mock_instance = MagicMock()
        mock_instance.connect = AsyncMock()
        mock_instance.disconnect = AsyncMock()
        MockClient.return_value = mock_instance

        store = self._make_store()
        pool = ClientPool(MagicMock(), store=store)

        async def run():
            await pool.get("session_x")
            result = await pool.remove("session_x")
            assert result is True
            mock_instance.disconnect.assert_called_once()
            store.remove.assert_called_once_with("session_x")

        run_async(run())

    @patch("src.pool.ClaudeSDKClient")
    def test_remove_nonexistent_session(self, MockClient):
        """remove 不存在的 session 返回 False"""
        store = self._make_store()
        pool = ClientPool(MagicMock(), store=store)

        async def run():
            result = await pool.remove("nonexistent")
            assert result is False

        run_async(run())

    @patch("src.pool.ClaudeSDKClient")
    def test_list_sessions(self, MockClient):
        """list_sessions 返回 store 数据"""
        store = self._make_store()
        pool = ClientPool(MagicMock(), store=store)
        result = pool.list_sessions()
        store.load_all.assert_called_once()
        assert result == {"s1": {"message_count": 3}, "s2": {"message_count": 1}}

    @patch("src.pool.ClaudeSDKClient")
    def test_session_ids(self, MockClient):
        """session_ids 返回 store 中所有 session_id"""
        store = self._make_store()
        pool = ClientPool(MagicMock(), store=store)
        result = pool.session_ids()
        assert result == {"s1", "s2"}

    @patch("src.pool.ClaudeSDKClient")
    def test_pool_without_store(self, MockClient):
        """store=None 时不报错（向后兼容）"""
        mock_instance = MagicMock()
        mock_instance.connect = AsyncMock()
        mock_instance.disconnect = AsyncMock()
        MockClient.return_value = mock_instance

        pool = ClientPool(MagicMock())  # 不传 store

        async def run():
            client = await pool.get("session_a")
            assert client is mock_instance
            # list_sessions / session_ids 在无 store 时返回空
            assert pool.list_sessions() == {}
            assert pool.session_ids() == set()

        run_async(run())


class TestPoolEviction:
    """LRU 回收策略测试"""

    def _make_store(self, sessions: dict):
        store = MagicMock()
        store.load_all = MagicMock(return_value=sessions)
        store.save = MagicMock()
        store.update_active = MagicMock()
        store.remove = MagicMock(return_value=True)
        store.archive = MagicMock(return_value=True)
        return store

    def _make_dispatcher(self):
        dispatcher = MagicMock()
        dispatcher.cancel_reader = MagicMock()
        return dispatcher

    @patch("src.pool.ClaudeSDKClient")
    def test_evicts_lru_when_exceeds_limit(self, MockClient):
        """超过阈值时回收 last_active 最早的 session"""
        instances = []
        def make_client(**kwargs):
            m = MagicMock()
            m.connect = AsyncMock()
            m.disconnect = AsyncMock()
            instances.append(m)
            return m
        MockClient.side_effect = make_client

        store = self._make_store({
            "s1": {"last_active": "2026-04-16T01:00:00+00:00"},
            "s2": {"last_active": "2026-04-16T03:00:00+00:00"},
            "s3": {"last_active": "2026-04-16T02:00:00+00:00"},
        })
        dispatcher = self._make_dispatcher()
        pool = ClientPool(MagicMock(), store=store, max_active_clients=3, dispatcher=dispatcher)

        async def run():
            await pool.get("s1")
            await pool.get("s2")
            await pool.get("s3")
            assert len(pool._clients) == 3

            # 第 4 个 session 触发回收
            await pool.get("s4")
            # s1 是 last_active 最早的，应被回收
            assert "s1" not in pool._clients
            assert "s4" in pool._clients
            dispatcher.cancel_reader.assert_called_with("s1")

        run_async(run())

    @patch("src.pool.ClaudeSDKClient")
    def test_preserves_metadata_after_eviction(self, MockClient):
        """回收后 store 元数据仍保留（不调用 store.remove）"""
        mock_instance = MagicMock()
        mock_instance.connect = AsyncMock()
        mock_instance.disconnect = AsyncMock()
        MockClient.return_value = mock_instance

        store = self._make_store({
            "s1": {"last_active": "2026-04-16T01:00:00+00:00", "claude_session_id": "cid_1"},
            "s2": {"last_active": "2026-04-16T03:00:00+00:00"},
        })
        pool = ClientPool(MagicMock(), store=store, max_active_clients=2, dispatcher=self._make_dispatcher())

        async def run():
            await pool.get("s1")
            await pool.get("s2")
            # 触发回收 s1
            await pool.get("s3")
            # store.remove 不应被调用（元数据保留）
            store.remove.assert_not_called()

        run_async(run())

    @patch("src.pool.ClaudeSDKClient")
    def test_resume_after_eviction(self, MockClient):
        """回收后再次 get 同一 session 时使用 --resume"""
        created_opts = []
        def make_client(**kwargs):
            m = MagicMock()
            m.connect = AsyncMock()
            m.disconnect = AsyncMock()
            created_opts.append(kwargs.get("options"))
            return m
        MockClient.side_effect = make_client

        store = self._make_store({
            "s1": {"last_active": "2026-04-16T01:00:00+00:00", "claude_session_id": "cid_1"},
            "s2": {"last_active": "2026-04-16T03:00:00+00:00"},
        })
        dispatcher = self._make_dispatcher()
        base_opts = MagicMock()
        pool = ClientPool(base_opts, store=store, max_active_clients=2, dispatcher=dispatcher)

        async def run():
            await pool.get("s1")
            await pool.get("s2")
            # 触发回收 s1
            await pool.get("s3")
            assert "s1" not in pool._clients

            # 再次 get s1，应触发 resume
            await pool.get("s1")
            assert "s1" in pool._clients

        run_async(run())

    @patch("src.pool.ClaudeSDKClient")
    def test_no_eviction_below_limit(self, MockClient):
        """未超阈值时不回收"""
        mock_instance = MagicMock()
        mock_instance.connect = AsyncMock()
        mock_instance.disconnect = AsyncMock()
        MockClient.return_value = mock_instance

        store = self._make_store({
            "s1": {"last_active": "2026-04-16T01:00:00+00:00"},
        })
        dispatcher = self._make_dispatcher()
        pool = ClientPool(MagicMock(), store=store, max_active_clients=5, dispatcher=dispatcher)

        async def run():
            await pool.get("s1")
            await pool.get("s2")
            # 只有 2 个，阈值 5，不应回收
            assert len(pool._clients) == 2
            mock_instance.disconnect.assert_not_called()
            dispatcher.cancel_reader.assert_not_called()

        run_async(run())

    @patch("src.pool.ClaudeSDKClient")
    def test_eviction_clears_pending(self, MockClient):
        """回收时清空 FIFO 队列"""
        mock_instance = MagicMock()
        mock_instance.connect = AsyncMock()
        mock_instance.disconnect = AsyncMock()
        MockClient.return_value = mock_instance

        store = self._make_store({
            "s1": {"last_active": "2026-04-16T01:00:00+00:00"},
            "s2": {"last_active": "2026-04-16T03:00:00+00:00"},
        })
        pool = ClientPool(MagicMock(), store=store, max_active_clients=2, dispatcher=self._make_dispatcher())

        async def run():
            await pool.get("s1")
            await pool.get("s2")
            pool.enqueue_message("s1", "om_1", "hello")
            assert pool.has_pending("s1") is True

            # 触发回收 s1
            await pool.get("s3")
            assert pool.has_pending("s1") is False

        run_async(run())

    @patch("src.pool.ClaudeSDKClient")
    def test_eviction_disconnects_client(self, MockClient):
        """回收时调用 client.disconnect()"""
        def make_client(**kwargs):
            m = MagicMock()
            m.connect = AsyncMock()
            m.disconnect = AsyncMock()
            return m
        MockClient.side_effect = make_client

        store = self._make_store({
            "s1": {"last_active": "2026-04-16T01:00:00+00:00"},
            "s2": {"last_active": "2026-04-16T03:00:00+00:00"},
        })
        pool = ClientPool(MagicMock(), store=store, max_active_clients=2, dispatcher=self._make_dispatcher())

        async def run():
            await pool.get("s1")
            s1_client = pool._clients["s1"]
            await pool.get("s2")
            # 触发回收 s1
            await pool.get("s3")
            s1_client.disconnect.assert_called_once()

        run_async(run())

    def test_active_client_count(self):
        """active_client_count 返回当前 client 数量"""
        pool = ClientPool(MagicMock(), max_active_clients=5)
        assert pool.active_client_count() == 0

    def test_max_active_clients_property(self):
        """max_active_clients 属性可读"""
        pool = ClientPool(MagicMock(), max_active_clients=3)
        assert pool.max_active_clients == 3

    def test_default_max_active_clients(self):
        """不传 max_active_clients 时默认 5"""
        pool = ClientPool(MagicMock())
        assert pool.max_active_clients == 5
