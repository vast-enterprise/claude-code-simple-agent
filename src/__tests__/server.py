"""HTTP API server 测试"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop
from aiohttp import web

from src.server import _create_app
from src.metrics import MetricsCollector


class TestServerAPI(AioHTTPTestCase):
    async def get_application(self):
        # mock pool
        self.mock_pool = MagicMock()
        self.mock_pool.list_sessions.return_value = {
            "p2p_ou_test": {"message_count": 5, "last_active": "2026-04-13T10:00:00Z", "created_at": "2026-04-13T09:00:00Z"}
        }
        self.mock_pool.remove = AsyncMock(return_value=True)

        self.metrics = MetricsCollector()
        self.metrics.record_message("p2p_ou_test", "hello", True, "hi there")

        return _create_app(self.mock_pool, self.metrics)

    @unittest_run_loop
    async def test_status(self):
        resp = await self.client.get("/api/status")
        assert resp.status == 200
        data = await resp.json()
        assert "uptime" in data
        assert "total_messages" in data
        assert "active_sessions" in data

    @unittest_run_loop
    async def test_sessions(self):
        resp = await self.client.get("/api/sessions")
        assert resp.status == 200
        data = await resp.json()
        assert "p2p_ou_test" in data

    @unittest_run_loop
    async def test_session_messages(self):
        resp = await self.client.get("/api/sessions/p2p_ou_test/messages")
        assert resp.status == 200
        data = await resp.json()
        assert len(data) == 1
        assert data[0]["session_id"] == "p2p_ou_test"

    @unittest_run_loop
    async def test_session_clear(self):
        resp = await self.client.post("/api/sessions/p2p_ou_test/clear")
        assert resp.status == 200
        data = await resp.json()
        assert data["ok"] is True

    @unittest_run_loop
    async def test_session_compact(self):
        resp = await self.client.post("/api/sessions/p2p_ou_test/compact")
        assert resp.status == 200
        data = await resp.json()
        assert data["ok"] is False  # TODO: compact 未实现
