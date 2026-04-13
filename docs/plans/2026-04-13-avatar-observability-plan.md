# Avatar 可观测性 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 为 Digital Avatar 添加异常通知、session 持久化、飞书指令和管理后台。

**Architecture:** 在现有 avatar 进程内新增 4 个模块（notify/store/metrics/server），不引入外部依赖。HTTP server 使用 Python 标准库 `aiohttp` 或原生 asyncio。Session 持久化写 JSON 文件，重启时 Claude SDK resume 恢复上下文。

**Tech Stack:** Python asyncio, Claude Agent SDK, lark-cli, aiohttp, vanilla HTML+JS+Tailwind CDN

**Design Doc:** `docs/plans/2026-04-13-avatar-observability-design.md`

---

### Task 1: notify.py — 异常通知

**Files:**
- Create: `src/notify.py`
- Create: `src/__tests__/notify.py`
- Modify: `src/config.py` — 新增 NOTIFY_CONFIG 解析

**Step 1: Write the failing test**

```python
# src/__tests__/notify.py
import time
from unittest.mock import patch, MagicMock
from src.notify import notify_error, _throttle_cache


def test_notify_error_calls_lark_cli():
    """notify_error 调用 lark-cli 发送消息"""
    _throttle_cache.clear()
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        notify_error("测试标题", "测试详情")
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert "lark-cli" in args
        assert "--as" in args and "bot" in args[args.index("--as") + 1:]


def test_notify_error_throttle():
    """60 秒内同类通知只发一次"""
    _throttle_cache.clear()
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        notify_error("同类错误", "详情1")
        notify_error("同类错误", "详情2")
        assert mock_run.call_count == 1


def test_notify_error_disabled():
    """notify.enabled=False 时不发送"""
    _throttle_cache.clear()
    with patch("src.notify._notify_config", {"enabled": False}):
        with patch("subprocess.run") as mock_run:
            notify_error("标题", "详情")
            mock_run.assert_not_called()
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest src/__tests__/notify.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.notify'`

**Step 3: Write implementation**

`src/config.py` — 在文件末尾添加 NOTIFY_CONFIG：

```python
NOTIFY_CONFIG: dict = CONFIG.get("notify", {"enabled": False})
```

`src/notify.py`:

```python
"""飞书异常通知，60 秒同类防风暴"""

import json
import subprocess
import time

from src.config import NOTIFY_CONFIG, log_error

_throttle_cache: dict[str, float] = {}
_THROTTLE_SECONDS = 60
_notify_config = NOTIFY_CONFIG


def notify_error(title: str, detail: str) -> None:
    if not _notify_config.get("enabled", False):
        return

    now = time.time()
    if title in _throttle_cache and now - _throttle_cache[title] < _THROTTLE_SECONDS:
        return
    _throttle_cache[title] = now

    receive_id = _notify_config.get("receive_id", "")
    receive_id_type = _notify_config.get("receive_id_type", "open_id")
    if not receive_id:
        return

    text = f"⚠️ {title}\n{detail}"
    content = json.dumps({"text": text})
    data = json.dumps({"receive_id": receive_id, "msg_type": "text", "content": content})

    try:
        subprocess.run(
            [
                "lark-cli", "api", "POST",
                "/open-apis/im/v1/messages",
                f"--params", json.dumps({"receive_id_type": receive_id_type}),
                "--data", data, "--as", "bot", "--format", "data",
            ],
            capture_output=True, text=True, timeout=10,
        )
    except Exception as e:
        log_error(f"发送通知失败: {e}")
```

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest src/__tests__/notify.py -v`
Expected: 3 passed

**Step 5: Commit**

```bash
git add src/notify.py src/__tests__/notify.py src/config.py
git commit -m "feat: add notify module for Lark error notifications"
```

---

### Task 2: store.py — Session 持久化

**Files:**
- Create: `src/store.py`
- Create: `src/__tests__/store.py`

**Step 1: Write the failing test**

```python
# src/__tests__/store.py
import json
import tempfile
from pathlib import Path
from src.store import SessionStore


def test_save_and_load():
    with tempfile.TemporaryDirectory() as d:
        store = SessionStore(Path(d) / "sessions.json")
        store.save("s1", {"message_count": 0})
        loaded = store.load_all()
        assert "s1" in loaded
        assert loaded["s1"]["message_count"] == 0
        assert "created_at" in loaded["s1"]


def test_remove():
    with tempfile.TemporaryDirectory() as d:
        store = SessionStore(Path(d) / "sessions.json")
        store.save("s1", {})
        store.remove("s1")
        assert "s1" not in store.load_all()


def test_update_active():
    with tempfile.TemporaryDirectory() as d:
        store = SessionStore(Path(d) / "sessions.json")
        store.save("s1", {"message_count": 0})
        store.update_active("s1")
        data = store.load_all()
        assert data["s1"]["message_count"] == 1


def test_load_nonexistent():
    with tempfile.TemporaryDirectory() as d:
        store = SessionStore(Path(d) / "sessions.json")
        assert store.load_all() == {}


def test_persistence_across_instances():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "sessions.json"
        store1 = SessionStore(path)
        store1.save("s1", {"message_count": 5})
        store2 = SessionStore(path)
        assert store2.load_all()["s1"]["message_count"] == 5
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest src/__tests__/store.py -v`
Expected: FAIL

**Step 3: Write implementation**

```python
# src/store.py
"""Session 映射持久化"""

import json
from datetime import datetime, timezone
from pathlib import Path

from src.config import log_error


class SessionStore:
    def __init__(self, path: Path):
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def load_all(self) -> dict:
        if not self._path.exists():
            return {}
        try:
            return json.loads(self._path.read_text())
        except (json.JSONDecodeError, OSError):
            log_error(f"sessions.json 损坏，重置")
            return {}

    def save(self, session_id: str, metadata: dict) -> None:
        data = self.load_all()
        now = datetime.now(timezone.utc).isoformat()
        entry = data.get(session_id, {})
        entry.update(metadata)
        entry.setdefault("created_at", now)
        entry.setdefault("last_active", now)
        entry.setdefault("message_count", 0)
        data[session_id] = entry
        self._write(data)

    def remove(self, session_id: str) -> bool:
        data = self.load_all()
        if session_id not in data:
            return False
        del data[session_id]
        self._write(data)
        return True

    def update_active(self, session_id: str) -> None:
        data = self.load_all()
        if session_id in data:
            data[session_id]["last_active"] = datetime.now(timezone.utc).isoformat()
            data[session_id]["message_count"] = data[session_id].get("message_count", 0) + 1
            self._write(data)

    def _write(self, data: dict) -> None:
        self._path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
```

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest src/__tests__/store.py -v`
Expected: 5 passed

**Step 5: Commit**

```bash
git add src/store.py src/__tests__/store.py
git commit -m "feat: add SessionStore for session persistence"
```

---

### Task 3: pool.py 改造 — 集成 SessionStore + resume

**Files:**
- Modify: `src/pool.py`
- Modify: `src/__tests__/pool.py`
- Modify: `src/main.py` — 传入 store 和 data 目录

**Step 1: Write the failing test**

在 `src/__tests__/pool.py` 中添加 store 集成测试（mock ClaudeSDKClient）。

**Step 2: Modify pool.py**

关键变更：
- `ClientPool.__init__` 接受 `store: SessionStore` 参数
- `get()` 创建新 client 时调用 `store.save(session_id, {})`
- `get()` 每次调用后 `store.update_active(session_id)`
- 新增 `remove(session_id)` 方法 — disconnect client + store.remove
- 新增 `list_sessions()` 方法 — 返回 store.load_all()
- 启动时从 store 加载已有 session_id，但不预创建 client（惰性 resume）

**Step 3: Modify main.py**

```python
from src.store import SessionStore
store = SessionStore(ROOT / "data" / "sessions.json")
pool = ClientPool(options, store)
```

**Step 4: Run all tests**

Run: `python3 -m pytest src/__tests__/ -v`
Expected: all pass

**Step 5: Commit**

```bash
git add src/pool.py src/__tests__/pool.py src/main.py
git commit -m "feat: integrate SessionStore into ClientPool for persistence"
```

---

### Task 4: metrics.py — 指标收集

**Files:**
- Create: `src/metrics.py`
- Create: `src/__tests__/metrics.py`

**Step 1: Write the failing test**

```python
# src/__tests__/metrics.py
from src.metrics import MetricsCollector


def test_record_message():
    m = MetricsCollector()
    m.record_message("s1", "你好", True, "你好！")
    assert m.total_messages == 1
    assert m.total_errors == 0
    assert len(m.message_log) == 1


def test_record_error():
    m = MetricsCollector()
    m.record_message("s1", "测试", False, "")
    assert m.total_errors == 1


def test_ring_buffer_limit():
    m = MetricsCollector(max_log=5)
    for i in range(10):
        m.record_message("s1", f"msg{i}", True, "ok")
    assert len(m.message_log) == 5
    assert m.total_messages == 10


def test_status():
    m = MetricsCollector()
    m.record_message("s1", "hi", True, "hey")
    s = m.status()
    assert "uptime" in s
    assert s["total_messages"] == 1
```

**Step 2: Run to fail, then implement**

```python
# src/metrics.py
"""运行指标收集器"""

from collections import deque
from datetime import datetime, timezone


class MetricsCollector:
    def __init__(self, max_log: int = 200):
        self.start_time = datetime.now(timezone.utc)
        self.total_messages = 0
        self.total_errors = 0
        self.message_log: deque[dict] = deque(maxlen=max_log)

    def record_message(
        self, session_id: str, content: str, success: bool, reply: str
    ) -> None:
        self.total_messages += 1
        if not success:
            self.total_errors += 1
        self.message_log.append({
            "session_id": session_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "content_preview": content[:50],
            "success": success,
            "reply_preview": reply[:50],
        })

    def status(self) -> dict:
        now = datetime.now(timezone.utc)
        uptime = now - self.start_time
        hours, remainder = divmod(int(uptime.total_seconds()), 3600)
        minutes = remainder // 60
        return {
            "uptime": f"{hours}h{minutes}m",
            "start_time": self.start_time.isoformat(),
            "total_messages": self.total_messages,
            "total_errors": self.total_errors,
            "error_rate": f"{self.total_errors / max(self.total_messages, 1) * 100:.1f}%",
        }
```

**Step 3: Run tests, commit**

Run: `python3 -m pytest src/__tests__/metrics.py -v`

```bash
git add src/metrics.py src/__tests__/metrics.py
git commit -m "feat: add MetricsCollector for runtime stats"
```

---

### Task 5: handler.py — 飞书指令解析 + metrics 集成

**Files:**
- Modify: `src/handler.py`
- Modify: `src/__tests__/handler.py`

**Step 1: Write failing tests for command parsing**

测试 `/clear`、`/sessions`、`/status` 指令解析和权限控制。

**Step 2: Implement command layer**

在 `handle_message` 前新增 `parse_command(content)` 函数：
- 返回 command 名或 `None`
- `/clear` → `"clear"`（清除当前用户自己的 session）
- `/compact` → `"compact"`（压缩当前用户自己的 session）
- `/sessions` → `"sessions"`（owner only）
- `/status` → `"status"`（owner only）
- 非 `/` 开头 → `None`（走正常 Claude 处理）

飞书指令只操作当前用户自己的 session。跨 session 操作（清除别人、清除全部）仅通过 dashboard HTTP API。

新增 `handle_command(pool, metrics, event, command)` 函数：
- 权限检查：`/sessions` 和 `/status` 仅 owner
- `/clear` 和 `/compact` 所有人可用，但只操作自己的 session
- 通过 `reply_message` 返回结果

在 `handle_message` 中集成 `metrics.record_message()` 调用。

**Step 3: Run tests, commit**

```bash
git add src/handler.py src/__tests__/handler.py
git commit -m "feat: add Lark slash commands and metrics integration"
```

---

### Task 6: server.py — HTTP API

**Files:**
- Create: `src/server.py`
- Create: `src/__tests__/server.py`

**Step 1: Implement HTTP server**

使用 `aiohttp` 创建异步 HTTP server，嵌入 avatar 主事件循环。

API 端点：
- `GET /api/status` — 调用 `metrics.status()` + 活跃 session 数
- `GET /api/sessions` — 调用 `pool.list_sessions()`
- `GET /api/sessions/{id}/messages` — 从 `metrics.message_log` 过滤
- `POST /api/sessions/{id}/clear` — 调用 `pool.remove(session_id)`
- `POST /api/sessions/{id}/compact` — 调用 Claude SDK compact
- `GET /` — 返回 `dashboard.html`

**Step 2: Write tests**

使用 `aiohttp.test_utils.AioHTTPTestCase` 测试 API 端点。

**Step 3: Run tests, commit**

```bash
git add src/server.py src/__tests__/server.py
git commit -m "feat: add HTTP API server for dashboard"
```

---

### Task 7: dashboard.html — 管理后台前端

**Files:**
- Create: `src/dashboard.html`

**Step 1: Create single-file dashboard**

纯 HTML + vanilla JS + Tailwind CDN。

布局：
- 顶部 4 个状态卡片：Uptime、总消息数、错误数、活跃 Session
- 中间 Session 表格：ID | 创建时间 | 最后活跃 | 消息数 | 操作（Clear / Compact）
- 点击 session 行展开消息时间线面板
- 30 秒自动轮询 `/api/status` 和 `/api/sessions`

**Step 2: Manual test**

启动 avatar，浏览器打开 `http://localhost:8420`，验证页面渲染和 API 交互。

**Step 3: Commit**

```bash
git add src/dashboard.html
git commit -m "feat: add dashboard frontend for avatar monitoring"
```

---

### Task 8: main.py 集成 — 通知 + HTTP server 启动

**Files:**
- Modify: `src/main.py`

**Step 1: Integrate all modules**

```python
from src.notify import notify_error
from src.metrics import MetricsCollector
from src.server import start_server

# sys.excepthook 注册
import sys
_original_excepthook = sys.excepthook
def _crash_hook(exc_type, exc_value, exc_tb):
    notify_error("数字分身崩溃", f"{exc_type.__name__}: {exc_value}")
    _original_excepthook(exc_type, exc_value, exc_tb)
sys.excepthook = _crash_hook

# main() 中：
metrics = MetricsCollector()
await start_server(pool, metrics, port=8420)

# lark-cli 断连检测：
if listener.returncode is not None:
    notify_error("飞书事件监听断连", f"exit code: {listener.returncode}")
```

**Step 2: Run full integration test**

```bash
python3 -m pytest src/__tests__/ -v
```

**Step 3: Commit**

```bash
git add src/main.py
git commit -m "feat: integrate observability modules into main loop"
```

---

### Task 9: gitignore + config 更新

**Files:**
- Modify: `.gitignore` — 添加 `data/`
- Modify: `config.example.json` — 添加 notify 配置示例

**Step 1: Update files**

`.gitignore` 添加 `data/`

`config.example.json` 添加：
```json
{
  "notify": {
    "enabled": true,
    "receive_id": "ou_xxx",
    "receive_id_type": "open_id"
  }
}
```

**Step 2: Commit**

```bash
git add .gitignore config.example.json
git commit -m "chore: add data/ to gitignore and notify config example"
```

---

### Task 10: 端到端验证

**Step 1:** 启动 avatar: `python3 -c "from src.main import main; import asyncio; asyncio.run(main())"`
**Step 2:** 浏览器打开 `http://localhost:8420`，确认 dashboard 加载
**Step 3:** 发送飞书消息，确认 dashboard 实时更新
**Step 4:** 发送 `/status`，确认飞书回复系统状态
**Step 5:** 发送 `/sessions`，确认飞书回复 session 列表
**Step 6:** Kill 进程，确认飞书收到崩溃通知
