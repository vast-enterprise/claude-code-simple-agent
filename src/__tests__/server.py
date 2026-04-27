"""HTTP API server 测试"""

import unittest.mock
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
        import src.server as _srv
        # patch OWNER_ID 为测试用 owner，使路径 /sessions/ou_test/create 能通过校验
        self._owner_patcher = unittest.mock.patch.object(_srv, "OWNER_ID", "ou_test")
        self._owner_patcher.start()
        self.addCleanup(self._owner_patcher.stop)

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
        # handler 通过 pool.list_sessions() 查——这是 pool 对 store 的公共封装
        self.mock_pool.list_sessions.return_value = {
            "p2p_ou_test_REQ-1": {"task_id": "REQ-1"},
        }
        body = {"suffix": "REQ-1", "message": "hi"}
        resp = await self.client.post("/sessions/ou_test/create", json=body)
        assert resp.status == 409
        data = await resp.json()
        assert data["session_id"] == "p2p_ou_test_REQ-1"
        assert "error" in data
        # dispatcher 不应被调用
        assert self.mock_dispatcher.dispatch.await_count == 0

    @unittest_run_loop
    async def test_task_id_non_string_400(self):
        """task_id 必须是 str；传 int → 400"""
        body = {"suffix": "REQ-3", "message": "hi", "task_id": 123}
        resp = await self.client.post("/sessions/ou_test/create", json=body)
        assert resp.status == 400
        data = await resp.json()
        assert "task_id" in data.get("error", "")
        # 不应触发 dispatch
        assert self.mock_dispatcher.dispatch.await_count == 0

    @unittest_run_loop
    async def test_task_type_non_string_400(self):
        """task_type 必须是 str；传 dict → 400"""
        body = {"suffix": "REQ-4", "message": "hi", "task_type": {"nested": "bad"}}
        resp = await self.client.post("/sessions/ou_test/create", json=body)
        assert resp.status == 400
        data = await resp.json()
        assert "task_type" in data.get("error", "")
        assert self.mock_dispatcher.dispatch.await_count == 0

    @unittest_run_loop
    async def test_suffix_whitelist_rejects_space(self):
        """suffix 含空格 → 400（与飞书 $suffix / /new ... 解析冲突）"""
        body = {"suffix": "foo bar", "message": "hi"}
        resp = await self.client.post("/sessions/ou_test/create", json=body)
        assert resp.status == 400
        data = await resp.json()
        assert "suffix" in data.get("error", "").lower()
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
        import src.server as _srv
        self._owner_patcher = unittest.mock.patch.object(_srv, "OWNER_ID", "ou_test")
        self._owner_patcher.start()
        self.addCleanup(self._owner_patcher.stop)

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


class TestSendMessage(AioHTTPTestCase):
    """POST /sessions/{session_id}/message — 向已存在的 session 追加消息"""

    async def get_application(self):
        import src.server as _srv
        # patch OWNER_ID 为测试用 owner，使 p2p_ou_test_* 路径能通过 owner 归属校验
        self._owner_patcher = unittest.mock.patch.object(_srv, "OWNER_ID", "ou_test")
        self._owner_patcher.start()
        self.addCleanup(self._owner_patcher.stop)

        self.mock_pool = MagicMock()
        # 默认 session 存在，状态 READY（可接收消息）
        self.mock_pool.list_sessions.return_value = {
            "p2p_ou_test_REQ-12345": {"task_id": "REQ-12345", "task_type": "requirement"},
        }
        self.mock_pool.get_status = MagicMock(return_value="READY")
        self.mock_pool.pending_count = MagicMock(return_value=0)
        self.mock_pool.active_client_count.return_value = 0
        self.mock_pool.max_active_clients = 5
        self.mock_pool._store = MagicMock()
        self.mock_pool._store.load_all = MagicMock(return_value={})

        self.metrics = MetricsCollector()

        self.mock_dispatcher = MagicMock()
        self.mock_dispatcher.dispatch = AsyncMock()

        return _create_app(self.mock_pool, self.metrics, dispatcher=self.mock_dispatcher)

    @unittest_run_loop
    async def test_happy_path_dispatches(self):
        """session 存在 + READY → 200，dispatcher.dispatch 被 await 一次"""
        body = {"message": "继续推进需求 REQ-12345", "suffix": "REQ-12345"}
        resp = await self.client.post(
            "/sessions/p2p_ou_test_REQ-12345/message", json=body
        )
        assert resp.status == 200
        data = await resp.json()
        assert data.get("session_id") == "p2p_ou_test_REQ-12345"
        assert data.get("status") == "PROCESSING"
        assert data.get("queued") is True

        # dispatcher.dispatch 被调用一次，session_id 匹配
        assert self.mock_dispatcher.dispatch.await_count == 1
        call_args = self.mock_dispatcher.dispatch.await_args
        assert call_args.args[0] == "p2p_ou_test_REQ-12345"
        # 第二个位置参数是 send_message 协程
        import inspect
        assert inspect.iscoroutine(call_args.args[1])
        # reader_factory 以 kw 传入
        rf = call_args.kwargs.get("reader_factory")
        assert callable(rf)

    @unittest_run_loop
    async def test_session_not_found_404(self):
        """session 不在 pool.list_sessions() → 404，不调用 dispatcher"""
        self.mock_pool.list_sessions.return_value = {}  # 空
        body = {"message": "hi"}
        resp = await self.client.post(
            "/sessions/p2p_ou_test_REQ-NOEXIST/message", json=body
        )
        assert resp.status == 404
        data = await resp.json()
        assert data.get("session_id") == "p2p_ou_test_REQ-NOEXIST"
        assert "not found" in data.get("error", "").lower()
        # dispatcher 不应被调用
        assert self.mock_dispatcher.dispatch.await_count == 0

    @unittest_run_loop
    async def test_session_processing_409(self):
        """session 当前 PROCESSING → 409，不调用 dispatcher"""
        self.mock_pool.get_status = MagicMock(return_value="PROCESSING")
        body = {"message": "hi"}
        resp = await self.client.post(
            "/sessions/p2p_ou_test_REQ-12345/message", json=body
        )
        assert resp.status == 409
        data = await resp.json()
        assert data.get("session_id") == "p2p_ou_test_REQ-12345"
        assert "processing" in data.get("error", "").lower()
        assert self.mock_dispatcher.dispatch.await_count == 0

    @unittest_run_loop
    async def test_missing_message_400(self):
        """body 缺 message 字段 → 400"""
        body = {"suffix": "REQ-12345"}
        resp = await self.client.post(
            "/sessions/p2p_ou_test_REQ-12345/message", json=body
        )
        assert resp.status == 400
        data = await resp.json()
        assert "error" in data
        assert self.mock_dispatcher.dispatch.await_count == 0

    @unittest_run_loop
    async def test_empty_message_400(self):
        """message 为空字符串 → 400"""
        body = {"message": ""}
        resp = await self.client.post(
            "/sessions/p2p_ou_test_REQ-12345/message", json=body
        )
        assert resp.status == 400
        data = await resp.json()
        assert "error" in data
        assert self.mock_dispatcher.dispatch.await_count == 0

    @unittest_run_loop
    async def test_non_string_message_400(self):
        """message 非字符串（传 int）→ 400"""
        body = {"message": 123}
        resp = await self.client.post(
            "/sessions/p2p_ou_test_REQ-12345/message", json=body
        )
        assert resp.status == 400
        data = await resp.json()
        assert "error" in data
        assert self.mock_dispatcher.dispatch.await_count == 0

    @unittest_run_loop
    async def test_suffix_passed_to_reader_factory(self):
        """suffix 应透传到 session_reader（通过 patch handler.session_reader 断言）"""
        from unittest.mock import patch

        async def _noop(*args, **kwargs):
            pass

        with patch("src.server.session_reader", side_effect=_noop) as mock_reader:
            body = {"message": "hi there", "suffix": "REQ-12345"}
            resp = await self.client.post(
                "/sessions/p2p_ou_test_REQ-12345/message", json=body
            )
            assert resp.status == 200
            data = await resp.json()
            assert data.get("session_id") == "p2p_ou_test_REQ-12345"

            # 调用 reader_factory，触发 session_reader(...)
            call_args = self.mock_dispatcher.dispatch.await_args
            rf = call_args.kwargs.get("reader_factory")
            assert callable(rf)
            coro = rf()
            # side_effect 为 async 函数时返回真 coroutine；必须 close 以避免
            # "coroutine was never awaited" RuntimeWarning
            coro.close()

            # session_reader 被调用，suffix 参数是 "REQ-12345"
            assert mock_reader.called
            _, kwargs = mock_reader.call_args
            assert kwargs.get("suffix") == "REQ-12345"

    @unittest_run_loop
    async def test_suffix_omitted_defaults_to_none(self):
        """body 不带 suffix 且 session_id 无 suffix 部分 → session_reader 的 suffix 为 None。

        注意：session_id=p2p_ou_test_REQ-12345 实际上含 suffix=REQ-12345，
        但本测试 setup 中的 session 是 p2p_ou_test_REQ-12345，若 base=p2p_ou_test，
        则 extract 出 suffix=REQ-12345，不是 None。
        使用不含 suffix 的 session_id（p2p_ou_test）来覆盖无 suffix 场景。
        """
        from unittest.mock import patch

        # 重写 list_sessions 使 p2p_ou_test 存在（无 suffix 的 session）
        self.mock_pool.list_sessions.return_value = {
            "p2p_ou_test": {"task_id": None, "task_type": None},
        }

        async def _noop(*args, **kwargs):
            pass

        with patch("src.server.session_reader", side_effect=_noop) as mock_reader:
            body = {"message": "hi"}
            resp = await self.client.post(
                "/sessions/p2p_ou_test/message", json=body
            )
            assert resp.status == 200
            data = await resp.json()
            assert data.get("session_id") == "p2p_ou_test"

            call_args = self.mock_dispatcher.dispatch.await_args
            rf = call_args.kwargs.get("reader_factory")
            coro = rf()
            coro.close()

            assert mock_reader.called
            _, kwargs = mock_reader.call_args
            assert kwargs.get("suffix") is None

    @unittest_run_loop
    async def test_message_extracts_suffix_from_session_id_when_omitted(self):
        """body 不传 suffix 时，从 session_id 自动反推 suffix 传给 reader_factory。

        session_id=p2p_ou_test_REQ-foo，base=p2p_ou_test → suffix 应为 "REQ-foo"。
        """
        from unittest.mock import patch

        # 注入带 suffix 的 session
        self.mock_pool.list_sessions.return_value = {
            "p2p_ou_test_REQ-foo": {"task_id": "REQ-foo"},
        }

        async def _noop(*args, **kwargs):
            pass

        with patch("src.server.session_reader", side_effect=_noop) as mock_reader:
            body = {"message": "hi there"}  # 故意不传 suffix
            resp = await self.client.post(
                "/sessions/p2p_ou_test_REQ-foo/message", json=body
            )
            assert resp.status == 200

            call_args = self.mock_dispatcher.dispatch.await_args
            rf = call_args.kwargs.get("reader_factory")
            coro = rf()
            coro.close()

            assert mock_reader.called
            _, kwargs = mock_reader.call_args
            assert kwargs.get("suffix") == "REQ-foo"

    @unittest_run_loop
    async def test_message_body_suffix_overrides_extraction(self):
        """body 明确传 suffix=REQ-bar 时，优先用 body 的值而非从 session_id 反推。

        session_id=p2p_ou_test_REQ-foo → 若按 session_id 反推应为 REQ-foo，
        但 body 传了 suffix=REQ-bar，应以 body 为准。
        """
        from unittest.mock import patch

        self.mock_pool.list_sessions.return_value = {
            "p2p_ou_test_REQ-foo": {"task_id": "REQ-foo"},
        }

        async def _noop(*args, **kwargs):
            pass

        with patch("src.server.session_reader", side_effect=_noop) as mock_reader:
            body = {"message": "hi", "suffix": "REQ-bar"}
            resp = await self.client.post(
                "/sessions/p2p_ou_test_REQ-foo/message", json=body
            )
            assert resp.status == 200

            call_args = self.mock_dispatcher.dispatch.await_args
            rf = call_args.kwargs.get("reader_factory")
            coro = rf()
            coro.close()

            assert mock_reader.called
            _, kwargs = mock_reader.call_args
            # body 显式传 suffix=REQ-bar，应优先于 session_id 反推
            assert kwargs.get("suffix") == "REQ-bar"

    @unittest_run_loop
    async def test_message_no_suffix_when_session_is_base_p2p(self):
        """session_id=p2p_ou_test（无 suffix 部分）+ body 不传 → suffix=None，不强加。"""
        from unittest.mock import patch

        self.mock_pool.list_sessions.return_value = {
            "p2p_ou_test": {"task_id": None},
        }

        async def _noop(*args, **kwargs):
            pass

        with patch("src.server.session_reader", side_effect=_noop) as mock_reader:
            body = {"message": "hello"}
            resp = await self.client.post(
                "/sessions/p2p_ou_test/message", json=body
            )
            assert resp.status == 200

            call_args = self.mock_dispatcher.dispatch.await_args
            rf = call_args.kwargs.get("reader_factory")
            coro = rf()
            coro.close()

            assert mock_reader.called
            _, kwargs = mock_reader.call_args
            assert kwargs.get("suffix") is None


class TestCreateSessionOwnerGuard(AioHTTPTestCase):
    """POST /sessions/{owner_id}/create — owner_id path 参数校验"""

    async def get_application(self):
        self.mock_pool = MagicMock()
        self.mock_pool.list_sessions.return_value = {}
        self.mock_pool.get_status = MagicMock(return_value="PROCESSING")
        self.mock_pool.pending_count = MagicMock(return_value=1)
        self.mock_pool.active_client_count.return_value = 0
        self.mock_pool.max_active_clients = 5
        self.mock_pool._store = MagicMock()
        self.mock_pool._store.load_all = MagicMock(return_value={})
        self.mock_pool._store.save = MagicMock()

        from src.config import OWNER_ID
        self.owner_id = OWNER_ID

        self.metrics = MetricsCollector()
        self.mock_dispatcher = MagicMock()
        self.mock_dispatcher.dispatch = AsyncMock()

        return _create_app(self.mock_pool, self.metrics, dispatcher=self.mock_dispatcher)

    @unittest_run_loop
    async def test_create_rejects_non_owner(self):
        """path 上的 owner_id != OWNER_ID → 403，body 含 error"""
        body = {"suffix": "REQ-1", "message": "hi"}
        resp = await self.client.post("/sessions/ou_other_intruder/create", json=body)
        assert resp.status == 403
        data = await resp.json()
        assert "error" in data
        # dispatcher 不应被调用
        assert self.mock_dispatcher.dispatch.await_count == 0

    @unittest_run_loop
    async def test_create_accepts_owner(self):
        """path 上的 owner_id == OWNER_ID → 正常处理（200）"""
        body = {"suffix": "REQ-999", "message": "继续"}
        resp = await self.client.post(
            f"/sessions/{self.owner_id}/create", json=body
        )
        assert resp.status == 200
        data = await resp.json()
        assert data["created"] is True
        assert self.mock_dispatcher.dispatch.await_count == 1


class TestSendMessageOwnerGuard(AioHTTPTestCase):
    """POST /sessions/{session_id}/message — session 归属 owner 校验"""

    async def get_application(self):
        from src.config import OWNER_ID
        self.owner_id = OWNER_ID
        # 准备一个属于 owner 的 session 和一个不属于 owner 的 session
        self.mock_pool = MagicMock()
        self.mock_pool.list_sessions.return_value = {
            f"p2p_{OWNER_ID}_REQ-42": {"task_id": "REQ-42"},
            "p2p_ou_other_REQ-1": {"task_id": "REQ-1"},
        }
        self.mock_pool.get_status = MagicMock(return_value="READY")
        self.mock_pool.pending_count = MagicMock(return_value=0)
        self.mock_pool.active_client_count.return_value = 0
        self.mock_pool.max_active_clients = 5
        self.mock_pool._store = MagicMock()
        self.mock_pool._store.load_all = MagicMock(return_value={})
        self.mock_pool._store.save = MagicMock()

        self.metrics = MetricsCollector()
        self.mock_dispatcher = MagicMock()
        self.mock_dispatcher.dispatch = AsyncMock()

        return _create_app(self.mock_pool, self.metrics, dispatcher=self.mock_dispatcher)

    @unittest_run_loop
    async def test_message_rejects_non_owner_session(self):
        """session_id 不属于 OWNER_ID（如 p2p_ou_other_xxx）→ 403"""
        body = {"message": "hi"}
        resp = await self.client.post(
            "/sessions/p2p_ou_other_REQ-1/message", json=body
        )
        assert resp.status == 403
        data = await resp.json()
        assert "error" in data
        # dispatcher 不应被调用
        assert self.mock_dispatcher.dispatch.await_count == 0

    @unittest_run_loop
    async def test_message_accepts_owner_session(self):
        """session_id 属于 OWNER_ID → 正常处理（200 或 404 正常状态）"""
        from src.config import OWNER_ID
        body = {"message": "继续推进"}
        resp = await self.client.post(
            f"/sessions/p2p_{OWNER_ID}_REQ-42/message", json=body
        )
        # 属于 owner 的 session：通过校验，正常走到业务逻辑 → 200
        assert resp.status == 200
        data = await resp.json()
        assert data.get("queued") is True


class TestSendMessageNoDispatcher(AioHTTPTestCase):
    """dispatcher 未注入时 → 503"""

    async def get_application(self):
        import src.server as _srv
        self._owner_patcher = unittest.mock.patch.object(_srv, "OWNER_ID", "ou_test")
        self._owner_patcher.start()
        self.addCleanup(self._owner_patcher.stop)

        self.mock_pool = MagicMock()
        self.mock_pool.list_sessions.return_value = {
            "p2p_ou_test_REQ-12345": {"task_id": "REQ-12345"},
        }
        self.mock_pool.get_status = MagicMock(return_value="READY")
        self.mock_pool.active_client_count.return_value = 0
        self.mock_pool.max_active_clients = 5
        self.mock_pool._store = MagicMock()

        self.metrics = MetricsCollector()
        # 不传 dispatcher
        return _create_app(self.mock_pool, self.metrics)

    @unittest_run_loop
    async def test_send_without_dispatcher_503(self):
        body = {"message": "hi"}
        resp = await self.client.post(
            "/sessions/p2p_ou_test_REQ-12345/message", json=body
        )
        assert resp.status == 503
        data = await resp.json()
        assert "dispatcher" in data.get("error", "").lower()

