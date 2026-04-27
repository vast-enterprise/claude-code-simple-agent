"""HTTP API server for avatar dashboard"""

import json
import re
import uuid
from pathlib import Path

from aiohttp import web

from src.config import OWNER_ID, ROOT, log_info
from src.handler import send_message, session_reader
from src.pool import SessionStatus
from src.router import extract_suffix_from_session_id

# suffix 白名单：避免与飞书侧 /new {suffix} / $suffix 解析冲突（空格、换行、$、/ 等）
_SUFFIX_PATTERN = re.compile(r"[A-Za-z0-9_\-\.]+")

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


async def _handle_create_session(request):
    """POST /sessions/{owner_id}/create — 新建 p2p session 并 dispatch 首条消息。

    调用方（主 Claude agent）在为某个需求/bug 开分身会话时通过此端点创建。

    Request body 字段：
    - suffix (str, required, non-empty, whitelist `[A-Za-z0-9_\\-\\.]+`)
      — 会话标识，用于拼接 session_id；白名单避免与飞书侧
      `/new {suffix}` / `$suffix` 命令解析冲突。
    - message (str, required, non-empty) — 首条消息内容
    - task_id (str, optional) — 需求/Bug 单号，写入 store 元数据
    - task_type (str, optional) — 任务类型（如 "requirement" / "bug"），写入 store 元数据

    语义：
    - 校验输入 → 400
    - 计算 session_id = f"p2p_{{owner_id}}_{{suffix}}"
    - 若 session_id 已在 store → 409（调用方应改用 /message 复用）
    - 若 dispatcher 未注入 → 503
    - 写 task_id / task_type 元数据（若提供）
    - 通过 dispatcher.dispatch 派发首条消息（send_message + session_reader）
    - 返回 session_id / status / created=true

    注意事项：
    - 409 检查与后续 save 非原子（TOCTOU）。同一 suffix 并发 create 可能导致二次派发——
      pool 层 per-session lock 防止重复建 client，但 FIFO 会入队两条消息。
      调用方应在其侧串行化同一 suffix 的 create 请求。
    - 返回 200 仅表示派发已接受。send_message 内部异常被 dispatcher.dispatch swallow
      （只 log_error），调用方需通过 GET /sessions/{{owner_id}} 观测 status 字段
      来确认消息是否真正被 Claude 受理。
    """
    owner_id = request.match_info["owner_id"]
    pool = request.app["pool"]
    metrics = request.app["metrics"]
    dispatcher = request.app.get("dispatcher")

    # 只允许 owner 本人调用写端点
    if owner_id != OWNER_ID:
        return _json({"error": "dispatch is owner-only"}, status=403)

    # 校验 dispatcher 注入（测试/开发场景下可能未配置）
    if dispatcher is None:
        return _json({"error": "dispatcher unavailable"}, status=503)

    # 解析 body
    try:
        body = await request.json()
    except (json.JSONDecodeError, ValueError):
        return _json({"error": "invalid json body"}, status=400)

    if not isinstance(body, dict):
        return _json({"error": "body must be a json object"}, status=400)

    suffix = body.get("suffix")
    message = body.get("message")
    task_id = body.get("task_id")
    task_type = body.get("task_type")

    # 校验 suffix / message
    if not isinstance(suffix, str) or not suffix.strip():
        return _json({"error": "suffix required (non-empty string)"}, status=400)
    if not _SUFFIX_PATTERN.fullmatch(suffix):
        return _json(
            {"error": "suffix must match [A-Za-z0-9_\\-\\.]+ (no spaces / special chars)"},
            status=400,
        )
    if not isinstance(message, str) or not message.strip():
        return _json({"error": "message required (non-empty string)"}, status=400)

    # 校验可选字段类型
    if task_id is not None and not isinstance(task_id, str):
        return _json({"error": "task_id must be a string"}, status=400)
    if task_type is not None and not isinstance(task_type, str):
        return _json({"error": "task_type must be a string"}, status=400)

    session_id = f"p2p_{owner_id}_{suffix}"

    # 409：session 已存在（调用方应改用 /message 端点复用）
    # 用 pool.list_sessions() 而非 pool._store.load_all()，保持封装
    existing = pool.list_sessions()
    if session_id in existing:
        return _json(
            {"error": "session already exists", "session_id": session_id},
            status=409,
        )

    # 先写元数据（save 是幂等 merge，先写后写都 OK；先写更简单）
    if pool._store is not None:
        meta: dict = {}
        if task_id:
            meta["task_id"] = task_id
        if task_type:
            meta["task_type"] = task_type
        if meta:
            pool._store.save(session_id, meta)

    # 构造虚拟事件，镜像 route_message 从真实 Lark 事件计算出的结构
    event = {
        "chat_type": "p2p",
        "sender_id": owner_id,
        "sender_type": "user",  # 防御性：避免 should_respond 过滤
        "message_id": f"internal-{uuid.uuid4()}",
        "content": message,
        "chat_id": owner_id,
    }

    # 派发首条消息（镜像 src/router.py::_dispatch_to_session）
    await dispatcher.dispatch(
        session_id,
        send_message(pool, event, session_id, message, metrics=metrics),
        reader_factory=lambda sid=session_id, sfx=suffix: session_reader(
            sid, pool, suffix=sfx, metrics=metrics
        ),
    )

    status = pool.get_status(session_id)
    return _json({
        "session_id": session_id,
        "status": status,
        "created": True,
    })


async def _handle_send_message(request):
    """POST /sessions/{session_id}/message — 向已存在的 session 追加一条消息。

    与 `_handle_create_session` 互补：create 新建 session 并发首条消息（写 task 元数据）；
    send_message 复用已存在 session，不写元数据、不触发 409-for-exists 检查。

    Request body 字段：
    - message (str, required, non-empty) — 消息内容
    - suffix (str, optional) — 回复前缀（`来自 {suffix} 的回复：\\n`）。
      不传则无前缀——但对 control-plane 场景（internal-* message_id）而言，
      reader 的 lark 侧副作用被 handler 层 _is_internal_message 屏蔽，所以
      prefix 实际不生效，此参数主要用于保持与 create 端点的对称性。

    响应：
    - 200: {"session_id": "<sid>", "status": "PROCESSING", "queued": true}
    - 400: body 非 dict / 缺 message / message 非 str / message 为空
    - 404: session_id 不在 pool.list_sessions()（调用方应改用 /create）
    - 409: pool.get_status(session_id) == PROCESSING（调用方应等待或使用 /interrupt）
    - 503: dispatcher 未注入

    虚拟事件的 sender_id 使用 src.config.OWNER_ID——因为控制平面只由 owner 的
    主 Claude agent 调用。sender_id 被 handler._build_prompt 用于选择角色（所有者/同事）
    但控制平面 message_id 形如 "internal-<uuid>"，reader 侧 lark 调用被整体跳过，
    所以 sender_id 对 lark 反馈无影响，只影响 Claude 看到的 prompt 前缀。

    注意事项（TOCTOU）：
    - 404 检查（list_sessions 查询）与后续 dispatch 非原子；同一瞬间 pool.remove()
      可能将 session 搬走，dispatch 会在空壳 session 上新建 client（等同于 create）。
    - 409 检查与后续 dispatch 同样非原子；set_processing 由 handler.send_message
      负责写入，两次连续 send_message 之间存在短暂窗口可能都通过 409 检查。
      调用方应在其侧串行化同一 session 的请求。
    """
    session_id = request.match_info["session_id"]
    pool = request.app["pool"]
    metrics = request.app["metrics"]
    dispatcher = request.app.get("dispatcher")

    # 只允许 owner 名下的 session 被调用
    if not _owner_matches(session_id, OWNER_ID):
        return _json({"error": "dispatch is owner-only"}, status=403)

    # 503: dispatcher 未注入
    if dispatcher is None:
        return _json({"error": "dispatcher unavailable"}, status=503)

    # 400: body 解析
    try:
        body = await request.json()
    except (json.JSONDecodeError, ValueError):
        return _json({"error": "invalid json body"}, status=400)

    if not isinstance(body, dict):
        return _json({"error": "body must be a json object"}, status=400)

    message = body.get("message")
    suffix = body.get("suffix")

    # 400: message 必填 str 且非空
    if not isinstance(message, str) or not message.strip():
        return _json({"error": "message required (non-empty string)"}, status=400)

    # 400: suffix 可选但须为 str
    if suffix is not None and not isinstance(suffix, str):
        return _json({"error": "suffix must be a string"}, status=400)

    # fallback：body 不传 suffix 时从 session_id 自动反推。
    # 控制平面仅服务 owner p2p，base 固定为 f"p2p_{OWNER_ID}"。
    # extract_suffix_from_session_id 返回 None 表示无 suffix，行为等同于直接 None。
    if not suffix:
        suffix = extract_suffix_from_session_id(session_id, f"p2p_{OWNER_ID}")

    # 404: session 不存在（经 pool.list_sessions() 公共 API 查）
    existing = pool.list_sessions()
    if session_id not in existing:
        return _json(
            {"error": "session not found", "session_id": session_id},
            status=404,
        )

    # 409: session 正在处理
    if pool.get_status(session_id) == SessionStatus.PROCESSING:
        return _json(
            {"error": "session is processing", "session_id": session_id},
            status=409,
        )

    # 构造虚拟事件，镜像 create 端点
    event = {
        "chat_type": "p2p",
        "sender_id": OWNER_ID,
        "sender_type": "user",  # 防御性：避免 should_respond 过滤
        "message_id": f"internal-{uuid.uuid4()}",
        "content": message,
        "chat_id": OWNER_ID,
    }

    await dispatcher.dispatch(
        session_id,
        send_message(pool, event, session_id, message, metrics=metrics),
        reader_factory=lambda sid=session_id, sfx=suffix: session_reader(
            sid, pool, suffix=sfx, metrics=metrics
        ),
    )

    return _json({
        "session_id": session_id,
        "status": SessionStatus.PROCESSING,
        "queued": True,
    })


async def _handle_history_page(request):
    """返回历史记录页 HTML"""
    if not _HISTORY_PAGE_PATH.exists():
        return web.Response(text="History page not found", status=404)
    return web.FileResponse(_HISTORY_PAGE_PATH)


# ── App 创建与启动 ──


def _create_app(pool, metrics, *, dispatcher=None) -> web.Application:
    app = web.Application()
    app["pool"] = pool
    app["metrics"] = metrics
    app["dispatcher"] = dispatcher

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

    # 调度控制面：/sessions/{owner_id}/* 挂在根路径下，与 /api/* 分开
    app.router.add_get("/sessions/{owner_id}", _handle_sessions_by_owner)
    app.router.add_post("/sessions/{owner_id}/create", _handle_create_session)
    app.router.add_post("/sessions/{session_id}/message", _handle_send_message)

    return app


async def start_server(pool, metrics, *, dispatcher=None, port: int = 8420) -> web.AppRunner:
    """启动 HTTP server，返回 runner（用于 shutdown 时 cleanup）"""
    app = _create_app(pool, metrics, dispatcher=dispatcher)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", port)
    await site.start()
    log_info(f"Dashboard: http://localhost:{port}")
    return runner
