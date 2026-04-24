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


class TestCreateSession(AioHTTPTestCase):
    """POST /sessions/{owner_id}/create — dispatch 控制面写端点"""

    async def get_application(self):
        self.mock_pool = MagicMock()
        self.mock_pool.list_sessions.return_value = {}  # 默认：无会话
        self.mock_pool.get_status = MagicMock(return_value="PROCESSING")
        self.mock_pool.pending_count = MagicMock(return_value=1)
        self.mock_pool.active_client_count.return_value = 0
        self.mock_pool.max_active_clients = 5
        # store 默认非 None，save 可观测
        self.mock_pool._store = MagicMock()
        self.mock_pool._store.load_all = MagicMock(return_value={})
        self.mock_pool._store.save = MagicMock()

        self.metrics = MetricsCollector()

        # dispatcher：AsyncMock，可断言被 await 一次
        self.mock_dispatcher = MagicMock()
        self.mock_dispatcher.dispatch = AsyncMock()

        return _create_app(self.mock_pool, self.metrics, dispatcher=self.mock_dispatcher)

    @unittest_run_loop
    async def test_happy_path_creates_and_dispatches(self):
        """合法请求 → 200，dispatcher.dispatch 被 await 一次，store.save 带 task 元数据"""
        body = {
            "suffix": "REQ-12345",
            "message": "继续推进需求 REQ-12345",
            "task_id": "REQ-12345",
            "task_type": "requirement",
        }
        resp = await self.client.post("/sessions/ou_test/create", json=body)
        assert resp.status == 200
        data = await resp.json()
        assert data["session_id"] == "p2p_ou_test_REQ-12345"
        assert data["created"] is True
        assert data["status"] == "PROCESSING"

        # dispatcher.dispatch 应被调用一次，session_id 匹配
        assert self.mock_dispatcher.dispatch.await_count == 1
        call_args = self.mock_dispatcher.dispatch.await_args
        # 第一个位置参数是 session_id
        assert call_args.args[0] == "p2p_ou_test_REQ-12345"
        # 第二个位置参数是 send_message 协程
        import inspect
        assert inspect.iscoroutine(call_args.args[1])
        # reader_factory 以 kw 传入，调用后应返回协程
        rf = call_args.kwargs.get("reader_factory")
        assert callable(rf)

        # store.save 被调用，包含 task_id/task_type
        save_calls = self.mock_pool._store.save.call_args_list
        # 找到带 task_id 的那次
        task_saves = [
            c for c in save_calls
            if len(c.args) >= 2 and isinstance(c.args[1], dict) and "task_id" in c.args[1]
        ]
        assert len(task_saves) >= 1
        saved_sid, saved_meta = task_saves[0].args
        assert saved_sid == "p2p_ou_test_REQ-12345"
        assert saved_meta.get("task_id") == "REQ-12345"
        assert saved_meta.get("task_type") == "requirement"

    @unittest_run_loop
    async def test_missing_suffix_400(self):
        body = {"message": "hi"}
        resp = await self.client.post("/sessions/ou_test/create", json=body)
        assert resp.status == 400
        data = await resp.json()
        assert "error" in data

    @unittest_run_loop
    async def test_empty_suffix_400(self):
        body = {"suffix": "", "message": "hi"}
        resp = await self.client.post("/sessions/ou_test/create", json=body)
        assert resp.status == 400

    @unittest_run_loop
    async def test_empty_message_400(self):
        body = {"suffix": "REQ-1", "message": ""}
        resp = await self.client.post("/sessions/ou_test/create", json=body)
        assert resp.status == 400
        data = await resp.json()
        assert "error" in data

    @unittest_run_loop
    async def test_session_already_exists_409(self):
        """session_id 已在 store 中 → 409，不调用 dispatcher"""
        self.mock_pool._store.load_all = MagicMock(return_value={
            "p2p_ou_test_REQ-1": {"task_id": "REQ-1"},
        })
        body = {"suffix": "REQ-1", "message": "hi"}
        resp = await self.client.post("/sessions/ou_test/create", json=body)
        assert resp.status == 409
        data = await resp.json()
        assert data["session_id"] == "p2p_ou_test_REQ-1"
        assert "error" in data
        # dispatcher 不应被调用
        assert self.mock_dispatcher.dispatch.await_count == 0

    @unittest_run_loop
    async def test_task_id_omitted_no_task_save(self):
        """请求不带 task_id/task_type → 200，store.save 不应以 task_id 作为元数据写入"""
        body = {"suffix": "REQ-2", "message": "hi"}
        resp = await self.client.post("/sessions/ou_test/create", json=body)
        assert resp.status == 200
        data = await resp.json()
        assert data["session_id"] == "p2p_ou_test_REQ-2"
        assert data["created"] is True
        # 检查 store.save 没有带 task_id 的调用（pool.get() 内部的 save 也可能被调，
        # 但我们 mock 的是 pool._store.save，pool.get() 也是 mock，所以这里只看
        # handler 主动触发的 save——应该没有包含 task_id 的）
        save_calls = self.mock_pool._store.save.call_args_list
        for c in save_calls:
            if len(c.args) >= 2 and isinstance(c.args[1], dict):
                assert "task_id" not in c.args[1]
                assert "task_type" not in c.args[1]


class TestCreateSessionNoDispatcher(AioHTTPTestCase):
    """dispatcher 未注入时 → 503"""

    async def get_application(self):
        self.mock_pool = MagicMock()
        self.mock_pool.list_sessions.return_value = {}
        self.mock_pool.active_client_count.return_value = 0
        self.mock_pool.max_active_clients = 5
        self.mock_pool._store = MagicMock()
        self.mock_pool._store.load_all = MagicMock(return_value={})

        self.metrics = MetricsCollector()
        # 不传 dispatcher
        return _create_app(self.mock_pool, self.metrics)

    @unittest_run_loop
    async def test_create_without_dispatcher_503(self):
        body = {"suffix": "REQ-1", "message": "hi"}
        resp = await self.client.post("/sessions/ou_test/create", json=body)
        assert resp.status == 503
        data = await resp.json()
        assert "dispatcher" in data.get("error", "").lower()
