"""HTTP API server for avatar dashboard"""

from pathlib import Path

from aiohttp import web

from src.config import log_info

_DASHBOARD_PATH = Path(__file__).parent / "dashboard.html"


def _json(data, status=200):
    return web.json_response(data, status=status)


async def _handle_status(request):
    metrics = request.app["metrics"]
    pool = request.app["pool"]
    s = metrics.status()
    s["active_sessions"] = len(pool.list_sessions())
    return _json(s)


async def _handle_sessions(request):
    pool = request.app["pool"]
    return _json(pool.list_sessions())


async def _handle_session_messages(request):
    session_id = request.match_info["session_id"]
    metrics = request.app["metrics"]
    messages = [m for m in metrics.message_log if m["session_id"] == session_id]
    return _json(messages)


async def _handle_session_clear(request):
    session_id = request.match_info["session_id"]
    pool = request.app["pool"]
    removed = await pool.remove(session_id)
    return _json({"ok": removed, "session_id": session_id})


async def _handle_session_compact(request):
    session_id = request.match_info["session_id"]
    # TODO: Claude SDK compact 集成
    return _json({"ok": False, "message": "compact 功能开发中", "session_id": session_id})


async def _handle_dashboard(request):
    if not _DASHBOARD_PATH.exists():
        return web.Response(text="Dashboard not found", status=404)
    return web.FileResponse(_DASHBOARD_PATH)


def _create_app(pool, metrics) -> web.Application:
    app = web.Application()
    app["pool"] = pool
    app["metrics"] = metrics

    app.router.add_get("/", _handle_dashboard)
    app.router.add_get("/api/status", _handle_status)
    app.router.add_get("/api/sessions", _handle_sessions)
    app.router.add_get("/api/sessions/{session_id}/messages", _handle_session_messages)
    app.router.add_post("/api/sessions/{session_id}/clear", _handle_session_clear)
    app.router.add_post("/api/sessions/{session_id}/compact", _handle_session_compact)

    return app


async def start_server(pool, metrics, port: int = 8420) -> web.AppRunner:
    """启动 HTTP server，返回 runner（用于 shutdown 时 cleanup）"""
    app = _create_app(pool, metrics)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    log_info(f"Dashboard: http://localhost:{port}")
    return runner
