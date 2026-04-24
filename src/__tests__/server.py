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
        self.mock_pool.active_client_count.return_value = 0
        self.mock_pool.max_active_clients = 5

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


class TestSessionsByOwner(AioHTTPTestCase):
    """GET /sessions/{owner_id} — dispatch 控制面读端点"""

    async def get_application(self):
        # 默认：空 store。具体测试里通过修改 list_sessions.return_value 注入数据。
        self.mock_pool = MagicMock()
        self.mock_pool.list_sessions.return_value = {}
        self.mock_pool.get_status = MagicMock(return_value="READY")
        self.mock_pool.pending_count = MagicMock(return_value=0)
        # 仅用于 /api/status 等老端点——这里不相关但要存在
        self.mock_pool.active_client_count.return_value = 0
        self.mock_pool.max_active_clients = 5
        # 大多数测试下 store 非 None（默认）——near-match / cross-owner 都需要 store 返回数据
        self.mock_pool._store = MagicMock()

        self.metrics = MetricsCollector()
        return _create_app(self.mock_pool, self.metrics)

    @unittest_run_loop
    async def test_happy_path_two_sessions(self):
        """owner 有两个 session，一个带 task_id 一个不带"""
        self.mock_pool.list_sessions.return_value = {
            "p2p_ou_test_REQ-1": {
                "task_id": "REQ-1",
                "task_type": "requirement",
                "last_active": "2026-04-24T10:00:00Z",
            },
            "p2p_ou_test": {
                "last_active": "2026-04-24T09:00:00Z",
            },
        }
        resp = await self.client.get("/sessions/ou_test")
        assert resp.status == 200
        data = await resp.json()
        assert "sessions" in data
        assert len(data["sessions"]) == 2

        by_sid = {s["session_id"]: s for s in data["sessions"]}
        assert by_sid["p2p_ou_test_REQ-1"]["task_id"] == "REQ-1"
        assert by_sid["p2p_ou_test_REQ-1"]["task_type"] == "requirement"
        assert by_sid["p2p_ou_test_REQ-1"]["last_active"] == "2026-04-24T10:00:00Z"
        assert by_sid["p2p_ou_test_REQ-1"]["status"] == "READY"
        assert by_sid["p2p_ou_test_REQ-1"]["pending_count"] == 0

        # 无 task_id / task_type 的 session 应显式返回 None（不是省略、不是空串）
        assert by_sid["p2p_ou_test"]["task_id"] is None
        assert by_sid["p2p_ou_test"]["task_type"] is None
        assert by_sid["p2p_ou_test"]["last_active"] == "2026-04-24T09:00:00Z"

    @unittest_run_loop
    async def test_empty_when_owner_has_no_sessions(self):
        """owner 在 store 中无任何 session → {"sessions": []}"""
        self.mock_pool.list_sessions.return_value = {
            "p2p_ou_other": {"task_id": "REQ-9", "last_active": "2026-04-24T08:00:00Z"},
        }
        resp = await self.client.get("/sessions/ou_test")
        assert resp.status == 200
        data = await resp.json()
        assert data == {"sessions": []}

    @unittest_run_loop
    async def test_cross_owner_isolation(self):
        """同一 pool 下多 owner，只返回目标 owner"""
        self.mock_pool.list_sessions.return_value = {
            "p2p_ou_test_REQ-1": {"task_id": "REQ-1", "last_active": "T1"},
            "p2p_ou_test": {"last_active": "T2"},
            "p2p_ou_other": {"task_id": "REQ-9", "last_active": "T3"},
            "p2p_ou_other_REQ-2": {"task_id": "REQ-2", "last_active": "T4"},
        }
        resp = await self.client.get("/sessions/ou_test")
        assert resp.status == 200
        data = await resp.json()
        sids = sorted(s["session_id"] for s in data["sessions"])
        assert sids == ["p2p_ou_test", "p2p_ou_test_REQ-1"]

    @unittest_run_loop
    async def test_near_match_prefix_isolation(self):
        """p2p_ou_test 不能命中 p2p_ou_testing_*（exact prefix guard）"""
        self.mock_pool.list_sessions.return_value = {
            "p2p_ou_test_REQ-1": {"task_id": "REQ-1", "last_active": "T1"},
            "p2p_ou_testing_REQ-2": {"task_id": "REQ-2", "last_active": "T2"},
        }
        resp = await self.client.get("/sessions/ou_test")
        assert resp.status == 200
        data = await resp.json()
        sids = [s["session_id"] for s in data["sessions"]]
        assert sids == ["p2p_ou_test_REQ-1"]
        assert "p2p_ou_testing_REQ-2" not in sids

    @unittest_run_loop
    async def test_status_reflects_pool(self):
        """status 字段反映 pool.get_status 的实时结果"""
        self.mock_pool.list_sessions.return_value = {
            "p2p_ou_test": {"last_active": "T1"},
            "p2p_ou_test_REQ-1": {"task_id": "REQ-1", "last_active": "T2"},
        }

        def _status_for(sid):
            return "PROCESSING" if sid == "p2p_ou_test" else "READY"
        self.mock_pool.get_status.side_effect = _status_for

        def _pending_for(sid):
            return 3 if sid == "p2p_ou_test" else 0
        self.mock_pool.pending_count.side_effect = _pending_for

        resp = await self.client.get("/sessions/ou_test")
        assert resp.status == 200
        data = await resp.json()
        by_sid = {s["session_id"]: s for s in data["sessions"]}
        assert by_sid["p2p_ou_test"]["status"] == "PROCESSING"
        assert by_sid["p2p_ou_test"]["pending_count"] == 3
        assert by_sid["p2p_ou_test_REQ-1"]["status"] == "READY"
        assert by_sid["p2p_ou_test_REQ-1"]["pending_count"] == 0

    @unittest_run_loop
    async def test_store_none_defensive(self):
        """pool._store is None 时（防御性）应返回空 list"""
        self.mock_pool._store = None
        # list_sessions 也会是 {}（pool 契约），但这里显式设一下更像真实
        self.mock_pool.list_sessions.return_value = {}
        resp = await self.client.get("/sessions/ou_test")
        assert resp.status == 200
        data = await resp.json()
        assert data == {"sessions": []}
