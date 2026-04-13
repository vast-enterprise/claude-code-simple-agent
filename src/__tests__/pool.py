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


class TestClientPoolWithStore:
    """ClientPool + SessionStore 集成测试"""

    def _make_store(self):
        """创建一个 mock SessionStore"""
        store = MagicMock()
        store.save = MagicMock()
        store.update_active = MagicMock()
        store.remove = MagicMock(return_value=True)
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
