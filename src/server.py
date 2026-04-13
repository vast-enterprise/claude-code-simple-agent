"""HTTP API server for avatar dashboard"""

import json
from pathlib import Path

from aiohttp import web

from src.config import ROOT, log_info

_DASHBOARD_PATH = Path(__file__).parent / "dashboard.html"
_SESSION_PAGE_PATH = Path(__file__).parent / "session.html"


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
                    })

    return messages


# ── 原有端点 ──


async def _handle_status(request):
    metrics = request.app["metrics"]
    pool = request.app["pool"]
    s = metrics.status()
    s["active_sessions"] = len(pool.list_sessions())
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
    from src.handler import _do_compact
    result = await _do_compact(pool, session_id)
    ok = "已压缩" in result
    return _json({"ok": ok, "message": result, "session_id": session_id})


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


async def _handle_session_page(request):
    """返回 session 详情页 HTML"""
    if not _SESSION_PAGE_PATH.exists():
        return web.Response(text="Session page not found", status=404)
    return web.FileResponse(_SESSION_PAGE_PATH)


# ── App 创建与启动 ──


def _create_app(pool, metrics) -> web.Application:
    app = web.Application()
    app["pool"] = pool
    app["metrics"] = metrics

    app.router.add_get("/", _handle_dashboard)
    app.router.add_get("/session.html", _handle_session_page)
    app.router.add_get("/api/status", _handle_status)
    app.router.add_get("/api/sessions", _handle_sessions)
    app.router.add_get("/api/sessions/{session_id}/messages", _handle_session_messages)
    app.router.add_get("/api/sessions/{session_id}/conversation", _handle_session_conversation)
    app.router.add_post("/api/sessions/{session_id}/clear", _handle_session_clear)
    app.router.add_post("/api/sessions/{session_id}/compact", _handle_session_compact)

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
