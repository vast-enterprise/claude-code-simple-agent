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
