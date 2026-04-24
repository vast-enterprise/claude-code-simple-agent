"""HTTP API server for avatar dashboard"""

import json
from pathlib import Path

from aiohttp import web

from src.config import ROOT, log_info

_DASHBOARD_PATH = Path(__file__).parent / "dashboard.html"
_SESSION_PAGE_PATH = Path(__file__).parent / "session.html"
_HISTORY_PAGE_PATH = Path(__file__).parent / "history.html"


def _json(data, status=200):
    return web.json_response(data, status=status)


def _get_claude_log_dir() -> Path:
    """从项目 ROOT 推导 Claude 日志目录。

    Claude 的项目日志存储在 ~/.claude/projects/ 下，
    目录名是项目绝对路径中 "/" 替换为 "-" 的结果。
    """
    encoded = str(ROOT).replace("/", "-")
    return Path.home() / ".claude" / "projects" / encoded


def _parse_session_log(log_path: Path) -> list[dict]:
    """解析 Claude JSONL 日志，提取用户消息、助手回复、工具调用。

    过滤规则：
    - 保留 user 文本消息、assistant blocks（text + tool_use）、tool_result
    - 跳过 thinking block、queue-operation、attachment 等非对话类型
    - tool_result content 截断到 5000 字符
    """
    messages: list[dict] = []
    if not log_path.exists():
        return messages

    with open(log_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            entry_type = entry.get("type")
            timestamp = entry.get("timestamp", "")
            msg = entry.get("message", {})
            content = msg.get("content")

            if entry_type == "user" and isinstance(content, str):
                # 用户文本消息
                messages.append({
                    "role": "user",
                    "content": content,
                    "timestamp": timestamp,
                })

            elif entry_type == "user" and isinstance(content, list):
                # 可能包含 tool_result
                for block in content:
                    if block.get("type") == "tool_result":
                        tool_content = block.get("content", "")
                        if isinstance(tool_content, list):
                            tool_content = "\n".join(
                                b.get("text", "")
                                for b in tool_content
                                if isinstance(b, dict)
                            )
                        messages.append({
                            "role": "tool_result",
                            "tool_use_id": block.get("tool_use_id", ""),
                            "content": str(tool_content)[:5000],
                            "timestamp": timestamp,
                        })

            elif entry_type == "assistant" and isinstance(content, list):
                blocks: list[dict] = []
                for block in content:
                    bt = block.get("type")
                    if bt == "text":
                        blocks.append({"type": "text", "text": block.get("text", "")})
                    elif bt == "tool_use":
                        blocks.append({
                            "type": "tool_use",
                            "name": block.get("name", ""),
                            "input": block.get("input", {}),
                            "id": block.get("id", ""),
                        })
                    # 跳过 thinking 和其他类型

                if blocks:
                    messages.append({
                        "role": "assistant",
                        "blocks": blocks,
                        "timestamp": timestamp,
                        "model": msg.get("model", ""),
                    })

    return messages


# ── 原有端点 ──


async def _handle_status(request):
    metrics = request.app["metrics"]
    pool = request.app["pool"]
    s = metrics.status()
    s["active_sessions"] = len(pool.list_sessions())
    s["active_clients"] = pool.active_client_count()
    s["max_active_clients"] = pool.max_active_clients
    return _json(s)


def _sanitize_sessions(raw: dict) -> dict:
    """过滤掉内部字段（如 claude_session_id），只返回安全的元数据"""
    safe = {}
    for sid, meta in raw.items():
        safe[sid] = {k: v for k, v in meta.items() if k != "claude_session_id"}
    return safe


async def _handle_sessions(request):
    pool = request.app["pool"]
    return _json(_sanitize_sessions(pool.list_sessions()))


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
    pool = request.app["pool"]
    claude_sid = pool.get_claude_session_id(session_id)
    if not claude_sid:
        return _json({"ok": False, "message": "当前没有活跃会话", "session_id": session_id})
    try:
        client = await pool.get(session_id)
        from claude_agent_sdk.types import ResultMessage
        await client.query("/compact", session_id=claude_sid)
        async for msg in client.receive_response():
            if isinstance(msg, ResultMessage):
                if msg.is_error:
                    return _json({"ok": False, "message": "压缩失败", "session_id": session_id})
                break
        return _json({"ok": True, "message": "会话已压缩", "session_id": session_id})
    except Exception as e:
        return _json({"ok": False, "message": str(e), "session_id": session_id})


async def _handle_session_interrupt(request):
    session_id = request.match_info["session_id"]
    pool = request.app["pool"]
    client = pool.get_client(session_id)
    if not client:
        return _json({"ok": False, "message": "当前没有活跃会话", "session_id": session_id})
    try:
        await client.interrupt()
        return _json({"ok": True, "message": "已中断当前任务", "session_id": session_id})
    except Exception as e:
        return _json({"ok": False, "message": str(e), "session_id": session_id})


async def _handle_dashboard(request):
    if not _DASHBOARD_PATH.exists():
        return web.Response(text="Dashboard not found", status=404)
    return web.FileResponse(_DASHBOARD_PATH)


# ── 新增端点 ──


async def _handle_session_conversation(request):
    """返回指定 session 的完整会话内容（从 Claude JSONL 日志解析）"""
    session_id = request.match_info["session_id"]
    pool = request.app["pool"]

    claude_sid = pool.get_claude_session_id(session_id)
    if not claude_sid:
        return _json({
            "session_id": session_id,
            "error": "No Claude session ID found",
            "messages": [],
        })

    log_dir = _get_claude_log_dir()
    log_path = log_dir / f"{claude_sid}.jsonl"
    messages = _parse_session_log(log_path)

    return _json({
        "session_id": session_id,
        "claude_session_id": claude_sid,
        "messages": messages,
    })


async def _handle_history(request):
    """返回归档的历史 session 列表"""
    pool = request.app["pool"]
    if not pool._store:
        return _json([])
    history = pool._store.load_history()
    safe = [
        {k: v for k, v in record.items() if k != "claude_session_id"}
        for record in history
    ]
    return _json(safe)


async def _handle_history_conversation(request):
    """返回指定历史 session 的完整会话内容"""
    pool = request.app["pool"]
    if not pool._store:
        return _json({"error": "No store configured", "messages": []}, status=400)

    try:
        index = int(request.match_info["index"])
    except ValueError:
        return _json({"error": "Invalid index", "messages": []}, status=400)

    history = pool._store.load_history()
    if index < 0 or index >= len(history):
        return _json({"error": "Index out of range", "messages": []}, status=404)

    record = history[index]
    claude_sid = record.get("claude_session_id")
    if not claude_sid:
        return _json({
            "session_id": record.get("session_id", ""),
            "error": "No Claude session ID in archive",
            "messages": [],
        })

    log_dir = _get_claude_log_dir()
    log_path = log_dir / f"{claude_sid}.jsonl"
    messages = _parse_session_log(log_path)

    return _json({
        "session_id": record.get("session_id", ""),
        "sender_name": record.get("sender_name", ""),
        "chat_name": record.get("chat_name", ""),
        "archived_at": record.get("archived_at", ""),
        "messages": messages,
    })


async def _handle_session_page(request):
    """返回 session 详情页 HTML"""
    if not _SESSION_PAGE_PATH.exists():
        return web.Response(text="Session page not found", status=404)
    return web.FileResponse(_SESSION_PAGE_PATH)


# ── 调度控制面（/sessions/*，不在 /api/ 命名空间下） ──


def _owner_matches(session_id: str, owner_id: str) -> bool:
    """判断 session_id 是否属于指定 owner。

    精确前缀匹配，避免 `ou_test` 命中 `ou_testing_*` 这样的跨 owner 泄露。
    模仿 src/router.py::_is_user_session 的模式。

    规则：
    - p2p: sid == f"p2p_{owner_id}" 或 sid.startswith(f"p2p_{owner_id}_")
    - group: sid 以 "group_" 开头，且 owner_id 作为完整段出现
             （即 f"_{owner_id}" 后紧跟 "_" 或行尾）
    """
    p2p_base = f"p2p_{owner_id}"
    if session_id == p2p_base or session_id.startswith(p2p_base + "_"):
        return True
    if session_id.startswith("group_"):
        seg = f"_{owner_id}"
        if session_id.endswith(seg) or (seg + "_") in session_id:
            return True
    return False


async def _handle_sessions_by_owner(request):
    """GET /sessions/{owner_id} — 列出 owner 名下所有 session 及其实时状态。

    dispatch 控制面读端点：调用方（主 Claude agent）通过此端点发现
    owner 当前有哪些 session / 各自的 task_id / 状态，以决定发给谁或新建。
    """
    owner_id = request.match_info["owner_id"]
    pool = request.app["pool"]

    # 防御性：pool._store 为 None 时（测试场景/未注入 store）返回空
    if getattr(pool, "_store", None) is None:
        return _json({"sessions": []})

    raw = pool.list_sessions()
    sessions_out = []
    for sid, meta in raw.items():
        if not _owner_matches(sid, owner_id):
            continue
        sessions_out.append({
            "session_id": sid,
            "status": pool.get_status(sid),
            "task_id": meta.get("task_id"),
            "task_type": meta.get("task_type"),
            "last_active": meta.get("last_active", ""),
            "pending_count": pool.pending_count(sid),
        })
    return _json({"sessions": sessions_out})


async def _handle_history_page(request):
    """返回历史记录页 HTML"""
    if not _HISTORY_PAGE_PATH.exists():
        return web.Response(text="History page not found", status=404)
    return web.FileResponse(_HISTORY_PAGE_PATH)


# ── App 创建与启动 ──


def _create_app(pool, metrics) -> web.Application:
    app = web.Application()
    app["pool"] = pool
    app["metrics"] = metrics

    app.router.add_get("/", _handle_dashboard)
    app.router.add_get("/session.html", _handle_session_page)
    app.router.add_get("/history.html", _handle_history_page)
    app.router.add_get("/api/status", _handle_status)
    app.router.add_get("/api/sessions", _handle_sessions)
    app.router.add_get("/api/sessions/history", _handle_history)
    app.router.add_get("/api/sessions/history/{index}/conversation", _handle_history_conversation)
    app.router.add_get("/api/sessions/{session_id}/messages", _handle_session_messages)
    app.router.add_get("/api/sessions/{session_id}/conversation", _handle_session_conversation)
    app.router.add_post("/api/sessions/{session_id}/clear", _handle_session_clear)
    app.router.add_post("/api/sessions/{session_id}/compact", _handle_session_compact)
    app.router.add_post("/api/sessions/{session_id}/interrupt", _handle_session_interrupt)

    # 调度控制面：/sessions/{owner_id} 挂在根路径下，与 /api/* 分开
    app.router.add_get("/sessions/{owner_id}", _handle_sessions_by_owner)

    return app


async def start_server(pool, metrics, port: int = 8420) -> web.AppRunner:
    """启动 HTTP server，返回 runner（用于 shutdown 时 cleanup）"""
    app = _create_app(pool, metrics)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", port)
    await site.start()
    log_info(f"Dashboard: http://localhost:{port}")
    return runner
