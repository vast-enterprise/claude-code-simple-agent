# Multi-Session Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 让飞书单聊/群聊用户拥有多个独立 Claude 会话，通过 `/new`、`$suffix`、`/switch` 等命令管理。

**Architecture:** 新增 `router.py` 命令路由层 + `defaults_store.py` 默认会话持久化。从 `handler.py` 迁出所有命令处理，handler 瘦身为纯执行层。`pool.py`、`session.py` 不改。

**Tech Stack:** Python 3.12, claude-agent-sdk, pytest

**Design doc:** `docs/plans/2026-04-23-multi-session-design.md`

---

## Task 1: DefaultsStore 模块（TDD）

**Files:**
- Create: `src/defaults_store.py`
- Create: `src/__tests__/defaults_store.py`

**Step 1: Write failing test for get_default**

```python
# src/__tests__/defaults_store.py
import tempfile
from pathlib import Path
from src.defaults_store import DefaultsStore


def test_get_default_returns_none_when_empty():
    with tempfile.TemporaryDirectory() as d:
        store = DefaultsStore(Path(d) / "session_defaults.json")
        assert store.get_default("p2p_ou_123") is None


def test_get_default_returns_stored_suffix():
    with tempfile.TemporaryDirectory() as d:
        store = DefaultsStore(Path(d) / "session_defaults.json")
        store.set_default("p2p_ou_123", "cms翻译")
        assert store.get_default("p2p_ou_123") == "cms翻译"


def test_get_default_returns_none_for_original_session():
    with tempfile.TemporaryDirectory() as d:
        store = DefaultsStore(Path(d) / "session_defaults.json")
        store.set_default("p2p_ou_123", None)
        assert store.get_default("p2p_ou_123") is None
```

**Step 2: Run test to verify it fails**

Run: `pytest src/__tests__/defaults_store.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'src.defaults_store'"

**Step 3: Write minimal DefaultsStore implementation**

```python
# src/defaults_store.py
"""per-user 默认会话 suffix 持久化"""

import json
import os
import tempfile
from pathlib import Path

from src.config import log_error


class DefaultsStore:
    def __init__(self, path: Path):
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def get_default(self, base_session_id: str) -> str | None:
        """获取用户的默认 suffix，None 表示原始会话"""
        data = self._load()
        return data.get(base_session_id)

    def set_default(self, base_session_id: str, suffix: str | None) -> None:
        """设置默认 suffix，None 切回原始会话"""
        data = self._load()
        data[base_session_id] = suffix
        self._write(data)

    def remove_user(self, base_session_id: str) -> None:
        """清除用户的默认设置"""
        data = self._load()
        if base_session_id in data:
            del data[base_session_id]
            self._write(data)

    def _load(self) -> dict:
        if not self._path.exists():
            return 
        try:
            return json.loads(self._path.read_text())
        except (json.JSONDecodeError, OSError):
            log_error("session_defaults.json 损坏，重置")
            return {}

    def _write(self, data: dict) -> None:
        """原子写入"""
        content = json.dumps(data, indent=2, ensure_ascii=False)
        fd, tmp_path = tempfile.mkstemp(dir=self._path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, self._path)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
```

**Step 4: Run test to verify it passes**

Run: `pytest src/__tests__/defaults_store.py -v`
Expected: PASS (3 tests)

**Step 5: Add edge case tests**

```python
# src/__tests__/defaults_store.py (append)

def test_set_default_overwrites_existing():
    with tempfile.TemporaryDirectory() as d:
        store = DefaultsStore(Path(d) / "session_defaults.json")
        store.set_default("p2p_ou_123", "old")
        store.set_default("p2p_ou_123", "new")
        assert store.get_default("p2p_ou_123") == "new"


def test_remove_user_deletes_entry():
    with tempfile.TemporaryDirectory() as d:
        store = DefaultsStore(Path(d) / "session_defaults.json")
        store.set_default("p2p_ou_123", "cms")
        store.remove_user("p2p_ou_123")
        assert store.get_default("p2p_ou_123") is None


def test_remove_user_nonexistent_is_noop():
    with tempfile.TemporaryDirectory() as d:
        store = DefaultsStore(Path(d) / "session_defaults.json")
        store.remove_user("nonexistent")  # 不报错


def test_persistence_across_instances():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "session_defaults.json"
        store1 = DefaultsStore(path)
        store1.set_default("p2p_ou_123", "cms")
        store2 = DefaultsStore(path)
        assert store2.get_default("p2p_ou_123") == "cms"


def test_corrupted_file_resets():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "session_defaults.json"
        path.write_text("not json")
        store = DefaultsStore(path)
        assert store.get_default("p2p_ou_123") is None
```

**Step 6: Run all tests**

Run: `pytest src/__tests__/defaults_store.py -v`
Expected: PASS (8 tests)

**Step 7: Commit**

```bash
git add src/defaults_store.py src/__tests__/defaults_store.py
git commit -m "feat(multi-session): add DefaultsStore for per-user default suffix persistence

- Atomic write with fsync
- Handles corrupted file gracefully
- 8 tests covering get/set/remove/persistence"
```

---

## Task 2: handler.py 瘦身（TDD）

**Files:**
- Modify: `src/handler.py`
- Modify: `src/__tests__/handler.py`

**目标：** `send_message` 接受外部传入的 `session_id` 和 `content`，移除 `/clear`、`/interrupt` 处理、`compute_session_id` 调用。`session_reader` 新增 `suffix` 参数控制回复前缀。`compute_session_id`、`should_respond`、`_build_prompt`、`_ensure_display_names` 保留不动（router 会调用它们）。

**Step 1: 更新 test_handler.py 中 send_message 测试**

修改 `TestSendMessage` 中所有测试，适配新签名 `send_message(pool, event, session_id, content, *, metrics)`。

关键变更：
- 所有 `send_message(pool, _event())` → `send_message(pool, _event(), "p2p_ou_xxx", "hello")`
- 删除 `test_clear_removes_session`、`test_interrupt_calls_client_interrupt`、`test_interrupt_no_client` 三个测试（迁移到 test_router.py）
- 删除 `test_routes_to_correct_session`（session_id 不再由 handler 计算）
- `test_query_called_and_enqueued`：传入 session_id + content
- `test_slash_command_sent_raw`：传入 content="/status"
- `test_normal_message_has_prefix`：传入 content="hello"
- `test_cleans_at_mention`：content 已由 router 去掉 @mention，handler 不再处理（删除此测试）
- `test_skips_empty_content`：传入 content=""
- `test_group_routes_correctly`：删除（session_id 由 router 传入）

```python
# 更新后的 TestSendMessage
class TestSendMessage:
    """send_message 接受 session_id + content，立即 query + 入队 FIFO"""

    @patch("src.handler.reply_message")
    def test_query_called_and_enqueued(self, mock_reply):
        pool, client = _make_mock_pool()
        run_async(send_message(pool, _event(), "p2p_test", "hello"))
        client.query.assert_called_once()
        pool.enqueue_message.assert_called_once()
        mock_reply.assert_not_called()

    @patch("src.handler.reply_message")
    def test_resumes_with_stored_session_id(self, mock_reply):
        pool, client = _make_mock_pool(claude_session_id="stored_123")
        run_async(send_message(pool, _event(), "p2p_test", "hello"))
        _, kwargs = client.query.call_args
        assert kwargs["session_id"] == "stored_123"

    @patch("src.handler.reply_message")
    def test_slash_command_sent_raw(self, mock_reply):
        pool, client = _make_mock_pool()
        run_async(send_message(pool, _event(), "p2p_test", "/status"))
        prompt = client.query.call_args[0][0]
        assert prompt == "/status"

    @patch("src.handler.reply_message")
    def test_normal_message_has_prefix(self, mock_reply):
        pool, client = _make_mock_pool()
        run_async(send_message(pool, _event(), "p2p_test", "hello"))
        prompt = client.query.call_args[0][0]
        assert "所有者" in prompt
        assert "hello" in prompt

    @patch("src.handler.reply_message")
    def test_skips_empty_content(self, mock_reply):
        pool, _ = _make_mock_pool()
        run_async(send_message(pool, _event(), "p2p_test", ""))
        pool.get.assert_not_called()
```

**Step 2: 新增 session_reader 回复前缀测试**

```python
# 追加到 TestSessionReader
@patch("src.handler.reply_message")
@patch("src.handler.remove_reaction")
@patch("src.handler.add_reaction", return_value="r_abc")
def test_reply_with_suffix_prefix(self, mock_add, mock_remove, mock_reply):
    messages = [
        AssistantMessage(content=[TextBlock(text="回复内容")], model="sonnet"),
        ResultMessage(subtype="result", duration_ms=100, duration_api_ms=80,
                      is_error=False, num_turns=1, session_id="x"),
    ]
    pending = {"message_id": "om_test", "content": "hello"}
    pool = self._setup_reader(messages, pending)
    run_async(session_reader("p2p_test_cms", pool, suffix="cms"))
    mock_reply.assert_called_once()
    reply_text = mock_reply.call_args[0][1]
    assert reply_text.startswith("来自 cms 的回复：")
    assert "回复内容" in reply_text

@patch("src.handler.reply_message")
@patch("src.handler.remove_reaction")
@patch("src.handler.add_reaction", return_value="r_abc")
def test_reply_without_suffix_no_prefix(self, mock_add, mock_remove, mock_reply):
    messages = [
        AssistantMessage(content=[TextBlock(text="回复内容")], model="sonnet"),
        ResultMessage(subtype="result", duration_ms=100, duration_api_ms=80,
                      is_error=False, num_turns=1, session_id="x"),
    ]
    pending = {"message_id": "om_test", "content": "hello"}
    pool = self._setup_reader(messages, pending)
    run_async(session_reader("p2p_test", pool, suffix=None))
    mock_reply.assert_called_once_with("om_test", "回复内容")
```

**Step 3: Run tests to verify they fail**

Run: `pytest src/__tests__/handler.py -v`
Expected: FAIL（send_message 签名不匹配，suffix 参数不存在）

**Step 4: 修改 handler.py**

`send_message` 新签名：

```python
async def send_message(
    pool: ClientPool, event: dict, session_id: str, content: str,
    *, metrics: MetricsCollector | None = None,
):
    """发送端：接受 router 传入的 session_id 和 content，立即 query 推送给 Claude。"""
    message_id = event.get("message_id", "")
    sender_id = event.get("sender_id", "")

    if not content or not message_id:
        return

    permissions.set_sender(sender_id)
    _ensure_display_names(pool, event, session_id)

    if content.startswith("/"):
        prompt = content
    else:
        prompt = _build_prompt(pool, event, session_id, content)

    try:
        client = await pool.get(session_id)
        claude_sid = pool.get_claude_session_id(session_id)
        await client.query(prompt, session_id=claude_sid)
        pool.enqueue_message(session_id, message_id, content)
        log_debug(f"[{session_id}] query 已发送: {content[:50]}")
    except Exception as e:
        log_error(f"[{session_id}] send_message 失败: {e}")
        reply_message(message_id, "抱歉，发送消息时出了点问题。")
        if metrics:
            metrics.record_message(session_id, content, False, "")
```

`session_reader` 新增 suffix 参数：

```python
async def session_reader(
    session_id: str, pool: ClientPool, *,
    suffix: str | None = None,
    metrics: MetricsCollector | None = None,
):
```

回复处（原 `handler.py:242-243`）改为：

```python
for text in reply_texts:
    if suffix:
        text = f"来自 {suffix} 的回复：\n{text}"
    reply_message(mid, text)
```

**Step 5: Run tests to verify they pass**

Run: `pytest src/__tests__/handler.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add src/handler.py src/__tests__/handler.py
git commit -m "refactor(handler): slim send_message to accept session_id+content, add suffix reply prefix

- send_message no longer handles /clear, /interrupt, session_id computation
- session_reader adds 'suffix' param for reply prefix
- Tests updated: removed command tests (moving to router), added prefix tests"
```

---

## Task 3: router.py 核心路由逻辑（TDD）

**Files:**
- Create: `src/router.py`
- Create: `src/__tests__/router.py`

**Step 1: Write failing tests for helper functions**

```python
# src/__tests__/router.py
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.router import (
    _compute_base_session_id,
    _compute_full_session_id,
    _extract_suffix_from_session_id,
)


def test_compute_base_session_id_p2p():
    event = {"chat_type": "p2p", "sender_id": "ou_123"}
    assert _compute_base_session_id(event) == "p2p_ou_123"


def test_compute_base_session_id_group():
    event = {"chat_type": "group", "chat_id": "oc_abc", "sender_id": "ou_123"}
    assert _compute_base_session_id(event) == "group_oc_abc_ou_123"


def test_compute_full_session_id_with_suffix():
    assert _compute_full_session_id("p2p_ou_123", "cms") == "p2p_ou_123_cms"


def test_compute_full_session_id_without_suffix():
    assert _compute_full_session_id("p2p_ou_123", None) == "p2p_ou_123"


def test_extract_suffix_from_session_id():
    assert _extract_suffix_from_session_id("p2p_ou_123_cms", "p2p_ou_123") == "cms"


def test_extract_suffix_returns_none_for_base():
    assert _extract_suffix_from_session_id("p2p_ou_123", "p2p_ou_123") is None
```

**Step 2: Run test to verify it fails**

Run: `pytest src/__tests__/router.py::test_compute_base_session_id_p2p -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Write minimal router.py with helper functions**

```python
# src/router.py
"""命令路由层：统一处理所有飞书命令，决定消息发往哪个 session"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.config import BOT_NAME, log_debug
from src.handler import compute_session_id
from src.lark import reply_message

if TYPE_CHECKING:
    from src.defaults_store import DefaultsStore
    from src.metrics import MetricsCollector
    from src.pool import ClientPool
    from src.session import SessionDispatcher

BOT_MENTION = f"@{BOT_NAME}"


def _compute_base_session_id(event: dict) -> str:
    """计算原始 session_id（不带 suffix），复用 handler.compute_session_id"""
    return compute_session_id(event)


def _compute_full_session_id(base: str, suffix: str | None) -> str:
    """base + suffix 拼接，suffix 为 None 时返回 base"""
    if suffix is None:
        return base
    return f"{base}_{suffix}"


def _extract_suffix_from_session_id(session_id: str, base: str) -> str | None:
    """从完整 session_id 中提取 suffix，无 suffix 返回 None"""
    if session_id == base:
        return None
    if session_id.startswith(base + "_"):
        return session_id[len(base) + 1:]
    return None


async def route_message(
    pool: ClientPool,
    event: dict,
    dispatcher: SessionDispatcher,
    defaults: DefaultsStore,
    *,
    metrics: MetricsCollector | None = None,
) -> None:
    """路由消息到对应 session 或处理命令"""
    # TODO: 实现命令路由
    pass
```

**Step 4: Run tests to verify they pass**

Run: `pytest src/__tests__/router.py -v`
Expected: PASS (6 tests)

**Step 5: Commit**

```bash
git add src/router.py src/__tests__/router.py
git commit -m "feat(router): add helper functions for session_id computation

- _compute_base_session_id: reuse handler.compute_session_id
- _compute_full_session_id: append suffix
- _extract_suffix_from_session_id: parse suffix from full id
- 6 tests covering p2p/group/suffix extraction"
```

---

## Task 4: router.py 命令解析（/new, $suffix, /switch）

**Files:**
- Modify: `src/router.py`
- Modify: `src/__tests__/router.py`

**Step 1: Write failing tests for /new command**

```python
# src/__tests__/router.py (append)

def run_async(coro):
    return asyncio.run(coro)


def _make_event(content="hello", sender_id="ou_123", chat_type="p2p"):
    return {
        "content": content,
        "message_id": "om_test",
        "sender_id": sender_id,
        "chat_type": chat_type,
    }


def _make_mocks():
    pool = MagicMock()
    pool.get = AsyncMock()
    pool.list_sessions = MagicMock(return_value={})
    pool.remove = AsyncMock(return_value=True)
    pool.get_client = MagicMock(return_value=None)
    
    dispatcher = MagicMock()
    dispatcher.dispatch = AsyncMock()
    dispatcher.cancel_reader = MagicMock()
    
    defaults = MagicMock()
    defaults.get_default = MagicMock(return_value=None)
    defaults.set_default = MagicMock()
    defaults.remove_user = MagicMock()
    
    return pool, dispatcher, defaults


@patch("src.router.reply_message")
@patch("src.router.send_message")
def test_new_command_creates_session(mock_send, mock_reply):
    pool, dispatcher, defaults = _make_mocks()
    event = _make_event(content="/new cms翻译 查查这个需求")
    
    run_async(route_message(pool, event, dispatcher, defaults))
    
    # 应该 dispatch 到 p2p_ou_123_cms翻译
    dispatcher.dispatch.assert_called_once()
    call_args = dispatcher.dispatch.call_args
    # 检查传给 send_message 的参数
    mock_send.assert_called_once()


@patch("src.router.reply_message")
def test_new_command_missing_suffix(mock_reply):
    pool, dispatcher, defaults = _make_mocks()
    event = _make_event(content="/new")
    
    run_async(route_message(pool, event, dispatcher, defaults))
    
    mock_reply.assert_called_once()
    reply_text = mock_reply.call_args[0][1]
    assert "用法" in reply_text
    dispatcher.dispatch.assert_not_called()


@patch("src.router.reply_message")
def test_new_command_missing_message(mock_reply):
    pool, dispatcher, defaults = _make_mocks()
    event = _make_event(content="/new cms翻译")
    
    run_async(route_message(pool, event, dispatcher, defaults))
    
    mock_reply.assert_called_once()
    reply_text = mock_reply.call_args[0][1]
    assert "用法" in reply_text
```

**Step 2: Write failing tests for $suffix routing**

```python
# src/__tests__/router.py (append)

@patch("src.router.reply_message")
@patch("src.router.send_message")
def test_dollar_prefix_routes_to_suffix(mock_send, mock_reply):
    pool, dispatcher, defaults = _make_mocks()
    pool.list_sessions = MagicMock(return_value={
        "p2p_ou_123_cms": {"created_at": "2026-04-23T10:00:00"}
    })
    event = _make_event(content="$cms 帮我查一下")
    
    run_async(route_message(pool, event, dispatcher, defaults))
    
    dispatcher.dispatch.assert_called_once()
    mock_reply.assert_not_called()


@patch("src.router.reply_message")
def test_dollar_prefix_nonexistent_session(mock_reply):
    pool, dispatcher, defaults = _make_mocks()
    event = _make_event(content="$不存在 消息")
    
    run_async(route_message(pool, event, dispatcher, defaults))
    
    mock_reply.assert_called_once()
    reply_text = mock_reply.call_args[0][1]
    assert "不存在" in reply_text
    dispatcher.dispatch.assert_not_called()
```

**Step 3: Write failing tests for /switch**

```python
# src/__tests__/router.py (append)

@patch("src.router.reply_message")
def test_switch_to_existing_suffix(mock_reply):
    pool, dispatcher, defaults = _make_mocks()
    pool.list_sessions = MagicMock(return_value={
        "p2p_ou_123_cms": {"created_at": "2026-04-23T10:00:00"}
    })
    event = _make_event(content="/switch cms")
    
    run_async(route_message(pool, event, dispatcher, defaults))
    
    defaults.set_default.assert_called_once_with("p2p_ou_123", "cms")
    mock_reply.assert_called_once()
    reply_text = mock_reply.call_args[0][1]
    assert "已切换" in reply_text
    assert "cms" in reply_text


@patch("src.router.reply_message")
def test_switch_to_original_session(mock_reply):
    pool, dispatcher, defaults = _make_mocks()
    event = _make_event(content="/switch")
    
    run_async(route_message(pool, event, dispatcher, defaults))
    
    defaults.set_default.assert_called_once_with("p2p_ou_123", None)
    mock_reply.assert_called_once()
    reply_text = mock_reply.call_args[0][1]
    assert "原始会话" in reply_text


@patch("src.router.reply_message")
def test_switch_to_nonexistent_suffix(mock_reply):
    pool, dispatcher, defaults = _make_mocks()
    event = _make_event(content="/switch 不存在")
    
    run_async(route_message(pool, event, dispatcher, defaults))
    
    defaults.set_default.assert_not_called()
    mock_reply.assert_called_once()
    reply_text = mock_reply.call_args[0][1]
    assert "不存在" in reply_text
```

**Step 4: Run tests to verify they fail**

Run: `pytest src/__tests__/router.py::test_new_command_creates_session -v`
Expected: FAIL (route_message 未实现)

**Step 5: Implement command routing in router.py**

```python
# src/router.py (replace route_message)

from src.handler import send_message, session_reader, should_respond


async def route_message(
    pool: ClientPool,
    event: dict,
    dispatcher: SessionDispatcher,
    defaults: DefaultsStore,
    *,
    metrics: MetricsCollector | None = None,
) -> None:
    """路由消息到对应 session 或处理命令"""
    if not should_respond(event):
        return

    content = event.get("content", "").strip()
    content = content.replace(BOT_MENTION, "").strip()
    message_id = event.get("message_id", "")
    
    if not content or not message_id:
        return

    base_session_id = _compute_base_session_id(event)

    # 1. /new {suffix} {message}
    if content.startswith("/new "):
        await _handle_new_command(pool, event, dispatcher, base_session_id, content, metrics)
        return

    # 2. /switch {suffix?}
    if content.startswith("/switch"):
        await _handle_switch_command(pool, event, defaults, base_session_id, content)
        return

    # 3. $suffix {message}
    if content.startswith("$"):
        await _handle_dollar_prefix(pool, event, dispatcher, base_session_id, content, metrics)
        return

    # 4. 普通消息 → 默认 session
    default_suffix = defaults.get_default(base_session_id)
    target_session_id = _compute_full_session_id(base_session_id, default_suffix)
    await _dispatch_to_session(
        pool, event, dispatcher, target_session_id, content, default_suffix, metrics=metrics
    )


async def _handle_new_command(pool, event, dispatcher, base, content, metrics):
    """处理 /new {suffix} {message}"""
    parts = content.split(None, 2)  # ["/new", "suffix", "message"]
    if len(parts) < 3:
        reply_message(event["message_id"], 
            "用法：/new {会话名称} {消息内容}\n"
            "示例：/new cms翻译 查查这个需求的状态")
        return

    suffix = parts[1]
    message = parts[2]
    target_session_id = _compute_full_session_id(base, suffix)
    
    await _dispatch_to_session(
        pool, event, dispatcher, target_session_id, message, suffix, metrics=metrics
    )


async def _handle_switch_command(pool, event, defaults, base, content):
    """处理 /switch {suffix?}"""
    parts = content.split(None, 1)
    suffix = parts[1] if len(parts) > 1 else None

    if suffix is None:
        # 切回原始会话
        defaults.set_default(base, None)
        reply_message(event["message_id"], "已切换回原始会话。")
        return

    # 检查目标会话是否存在
    target_session_id = _compute_full_session_id(base, suffix)
    all_sessions = pool.list_sessions()
    if target_session_id not in all_sessions:
        reply_message(event["message_id"], f"会话「{suffix}」不存在，请先 /new 创建。")
        return

    defaults.set_default(base, suffix)
    reply_message(event["message_id"], f"已切换默认会话到「{suffix}」。后续消息将发送到此会话。")


async def _handle_dollar_prefix(pool, event, dispatcher, base, content, metrics):
    """处理 $suffix {message}"""
    # 提取 suffix（到第一个空格）
    if " " not in content[1:]:
        reply_message(event["message_id"], "用法：$会话名称 消息内容")
        return

    suffix, message = content[1:].split(None, 1)
    target_session_id = _compute_full_session_id(base, suffix)

    # 检查会话是否存在
    all_sessions = pool.list_sessions()
    if target_session_id not in all_sessions:
        reply_message(event["message_id"], 
            f"会话「{suffix}」不存在，请先 /new {suffix} {{消息}} 创建。")
        return

    await _dispatch_to_session(
        pool, event, dispatcher, target_session_id, message, suffix, metrics=metrics
    )


async def _dispatch_to_session(pool, event, dispatcher, session_id, content, suffix, *, metrics):
    """内部 dispatch 封装"""
    await dispatcher.dispatch(
        session_id,
        send_message(pool, event, session_id, content, metrics=metrics),
        reader_factory=lambda sid=session_id, sfx=suffix: session_reader(
            sid, pool, suffix=sfx, metrics=metrics
        ),
    )
```

**Step 6: Run tests to verify they pass**

Run: `pytest src/__tests__/router.py -v`
Expected: PASS (15 tests)

**Step 7: Commit**

```bash
git add src/router.py src/__tests__/router.py
git commit -m "feat(router): implement /new, $suffix, /switch command routing

- /new {suffix} {msg}: create/reuse session and dispatch
- $suffix {msg}: route to existing session, error if not found
- /switch {suffix?}: change default session, validate existence
- 9 new tests covering command parsing and edge cases"
```

---

## Task 5: router.py 管理命令（/sessions, /clear, /clear-all, /interrupt）

**Files:**
- Modify: `src/router.py`
- Modify: `src/__tests__/router.py`

**Step 1: Write failing tests for /sessions**

```python
# src/__tests__/router.py (append)
from datetime import datetime, timezone

@patch("src.router.reply_message")
def test_sessions_lists_all(mock_reply):
    pool, dispatcher, defaults = _make_mocks()
    pool.list_sessions = MagicMock(return_value={
        "p2p_ou_123": {"created_at": "2026-04-23T10:00:00+00:00"},
        "p2p_ou_123_cms": {"created_at": "2026-04-23T14:30:00+00:00"},
        "p2p_ou_123_bug修复": {"created_at": "2026-04-23T15:00:00+00:00"},
        "p2p_ou_456": {"created_at": "2026-04-23T09:00:00+00:00"},  # 别人的
    })
    defaults.get_default = MagicMock(return_value=None)
    event = _make_event(content="/sessions")
    
    run_async(route_message(pool, event, dispatcher, defaults))
    
    mock_reply.assert_called_once()
    reply_text = mock_reply.call_args[0][1]
    assert "原始会话" in reply_text
    assert "cms" in reply_text
    assert "bug修复" in reply_text
    assert "ou_456" not in reply_text  # 不显示别人的会话
```

**Step 2: Write failing tests for /clear and /clear-all**

```python
# src/__tests__/router.py (append)

@patch("src.router.reply_message")
def test_clear_removes_default_session(mock_reply):
    pool, dispatcher, defaults = _make_mocks()
    event = _make_event(content="/clear")
    
    run_async(route_message(pool, event, dispatcher, defaults))
    
    pool.remove.assert_called_once_with("p2p_ou_123")
    mock_reply.assert_called_once()
    assert "已清除" in mock_reply.call_args[0][1]


@patch("src.router.reply_message")
def test_clear_with_suffix(mock_reply):
    pool, dispatcher, defaults = _make_mocks()
    pool.list_sessions = MagicMock(return_value={
        "p2p_ou_123_cms": {"created_at": "2026-04-23T14:30:00+00:00"},
    })
    event = _make_event(content="/clear cms")
    
    run_async(route_message(pool, event, dispatcher, defaults))
    
    pool.remove.assert_called_once_with("p2p_ou_123_cms")
    dispatcher.cancel_reader.assert_called_once_with("p2p_ou_123_cms")


@patch("src.router.reply_message")
def test_clear_nonexistent_suffix(mock_reply):
    pool, dispatcher, defaults = _make_mocks()
    pool.remove = AsyncMock(return_value=False)
    event = _make_event(content="/clear 不存在")
    
    run_async(route_message(pool, event, dispatcher, defaults))
    
    mock_reply.assert_called_once()
    assert "不存在" in mock_reply.call_args[0][1]


@patch("src.router.reply_message")
def test_clear_all(mock_reply):
    pool, dispatcher, defaults = _make_mocks()
    pool.list_sessions = MagicMock(return_value={
        "p2p_ou_123": {"created_at": "2026-04-23T10:00:00+00:00"},
        "p2p_ou_123_cms": {"created_at": "2026-04-23T14:30:00+00:00"},
        "p2p_ou_456": {"created_at": "2026-04-23T09:00:00+00:00"},
    })
    event = _make_event(content="/clear-all")
    
    run_async(route_message(pool, event, dispatcher, defaults))
    
    # 只清除 ou_123 的 2 个会话，不清 ou_456 的
    assert pool.remove.call_count == 2
    defaults.remove_user.assert_called_once_with("p2p_ou_123")
```

**Step 3: Write failing tests for /interrupt**

```python
# src/__tests__/router.py (append)

@patch("src.router.reply_message")
def test_interrupt_default_session(mock_reply):
    pool, dispatcher, defaults = _make_mocks()
    client = MagicMock()
    client.interrupt = AsyncMock()
    pool.get_client = MagicMock(return_value=client)
    event = _make_event(content="/interrupt")
    
    run_async(route_message(pool, event, dispatcher, defaults))
    
    client.interrupt.assert_called_once()
    mock_reply.assert_called_once()
    assert "已中断" in mock_reply.call_args[0][1]


@patch("src.router.reply_message")
def test_interrupt_with_suffix(mock_reply):
    pool, dispatcher, defaults = _make_mocks()
    client = MagicMock()
    client.interrupt = AsyncMock()
    pool.get_client = MagicMock(return_value=client)
    event = _make_event(content="/interrupt cms")
    
    run_async(route_message(pool, event, dispatcher, defaults))
    
    pool.get_client.assert_called_with("p2p_ou_123_cms")
    client.interrupt.assert_called_once()


@patch("src.router.reply_message")
def test_interrupt_no_active_client(mock_reply):
    pool, dispatcher, defaults = _make_mocks()
    event = _make_event(content="/interrupt")
    
    run_async(route_message(pool, event, dispatcher, defaults))
    
    mock_reply.assert_called_once()
    assert "没有活跃任务" in mock_reply.call_args[0][1]
```

**Step 4: Run tests to verify they fail**

Run: `pytest src/__tests__/router.py -k "sessions or clear or interrupt" -v`
Expected: FAIL

**Step 5: Implement management commands in router.py**

在 `route_message` 的命令优先级链中，在 `/switch` 之后、`$suffix` 之前插入：

```python
# 在 route_message 函数中添加

    # 3. /sessions
    if content.strip().lower() == "/sessions":
        _handle_sessions(pool, event, defaults, base_session_id)
        return

    # 4. /clear-all
    if content.strip().lower() == "/clear-all":
        await _handle_clear_all(pool, event, dispatcher, defaults, base_session_id)
        return

    # 5. /clear {suffix?}
    if content.strip().lower().startswith("/clear"):
        await _handle_clear(pool, event, dispatcher, defaults, base_session_id, content)
        return

    # 6. /interrupt {suffix?}
    if content.strip().lower().startswith("/interrupt"):
        await _handle_interrupt(pool, event, base_session_id, content)
        return
```

```python
def _list_user_sessions(pool: ClientPool, base: str) -> dict[str, dict]:
    """查询 store 中所有属于该 base 的 session"""
    all_sessions = pool.list_sessions()
    result = {}
    for sid, meta in all_sessions.items():
        if sid == base or sid.startswith(base + "_"):
            result[sid] = meta
    return result


def _handle_sessions(pool, event, defaults, base):
    """处理 /sessions"""
    user_sessions = _list_user_sessions(pool, base)
    default_suffix = defaults.get_default(base)

    if not user_sessions:
        reply_message(event["message_id"], "当前没有活跃会话。")
        return

    lines = ["当前会话列表："]
    for sid, meta in sorted(user_sessions.items(), key=lambda x: x[1].get("created_at", "")):
        suffix = _extract_suffix_from_session_id(sid, base)
        is_default = (suffix == default_suffix) if default_suffix else (suffix is None)
        name = suffix if suffix else "原始会话"
        created = meta.get("created_at", "")[:16].replace("T", " ") if meta.get("created_at") else ""
        marker = " [默认]" if is_default else ""
        time_part = f" (创建于 {created})" if created and suffix else ""
        lines.append(f"● {name}{marker}{time_part}")

    lines.append(f"\n共 {len(user_sessions)} 个会话。使用 $suffix 消息 切换，/switch suffix 设为默认。")
    reply_message(event["message_id"], "\n".join(lines))


async def _handle_clear(pool, event, dispatcher, defaults, base, content):
    """处理 /clear {suffix?}"""
    parts = content.split(None, 1)
    suffix = parts[1] if len(parts) > 1 else None

    if suffix is None:
        # 清除当前默认
        current_default = defaults.get_default(base)
        target = _compute_full_session_id(base, current_default)
    else:
        target = _compute_full_session_id(base, suffix)

    removed = await pool.remove(target)
    if removed:
        dispatcher.cancel_reader(target)
        name = suffix or "当前默认"
        reply_message(event["message_id"], f"已清除会话「{name}」。")
    else:
        reply_message(event["message_id"], f"会话「{suffix or '默认'}」不存在。")


async def _handle_clear_all(pool, event, dispatcher, defaults, base):
    """处理 /clear-all"""
    user_sessions = _list_user_sessions(pool, base)
    count = 0
    for sid in list(user_sessions.keys()):
        removed = await pool.remove(sid)
        if removed:
            dispatcher.cancel_reader(sid)
            count += 1
    defaults.remove_user(base)
    reply_message(event["message_id"], f"已清除所有 {count} 个会话。")


async def _handle_interrupt(pool, event, base, content):
    """处理 /interrupt {suffix?}"""
    parts = content.split(None, 1)
    suffix = parts[1] if len(parts) > 1 else None
    target = _compute_full_session_id(base, suffix)

    client = pool.get_client(target)
    if client:
        try:
            await client.interrupt()
            name = suffix or "当前"
            reply_message(event["message_id"], f"已中断「{name}」会话的当前任务。")
        except Exception as e:
            reply_message(event["message_id"], f"中断失败：{e}")
    else:
        reply_message(event["message_id"], "当前没有活跃任务。")
```

**Step 6: Run tests to verify they pass**

Run: `pytest src/__tests__/router.py -v`
Expected: PASS (all tests)

**Step 7: Commit**

```bash
git add src/router.py src/__tests__/router.py
git commit -m "feat(router): implement /sessions, /clear, /clear-all, /interrupt commands

- /sessions: list user's sessions with default marker and timestamps
- /clear {suffix?}: clear specific or default session
- /clear-all: clear all user sessions
- /interrupt {suffix?}: interrupt specific or default session
- 7 new tests for management commands"
```

---

## Task 6: main.py 集成 + 富消息解析迁移 + 全量测试

**Files:**
- Modify: `src/main.py:14,92-135`
- Modify: `src/router.py`（富消息解析从 handler 迁入 router）

**Step 1: 修改 main.py 导入和初始化**

```python
# src/main.py 新增导入
from src.defaults_store import DefaultsStore
from src.router import route_message

# 删除不再直接使用的导入
# 移除: from src.handler import send_message, session_reader, compute_session_id
# 保留: from src.handler import should_respond (router 内部调用，但 main 不直接用了)
```

初始化部分（`main()` 函数内，store 之后）：

```python
defaults = DefaultsStore(ROOT / "data" / "session_defaults.json")
```

**Step 2: 替换事件循环中的 dispatch 为 route_message**

```python
# 原来 main.py:129-135
session_id = compute_session_id(event)
log_info(f"收到消息 [{session_id}]: {event.get('content', '')[:50]}...")
await dispatcher.dispatch(
    session_id,
    send_message(pool, event, metrics=metrics),
    reader_factory=lambda sid=session_id: session_reader(sid, pool, metrics=metrics),
)

# 改为
log_info(f"收到消息: {event.get('content', '')[:50]}...")
await route_message(pool, event, dispatcher, defaults, metrics=metrics)
```

注意：`should_respond` 检查从 main.py 移除——router.route_message 内部会做这个检查。

**Step 3: 将富消息解析移入 router**

在 `route_message` 中，在解析 content 之前加入富消息解析：

```python
# router.py route_message() 开头
from src.lark import reply_message, resolve_rich_content

# 在取到 content 后、命令解析前
rich = resolve_rich_content(event)
if rich is not None:
    content = rich
```

同时从 handler.py 的 `send_message` 中移除富消息解析（原 `handler.py:126-128`），因为 router 已经处理了。

**Step 4: Run full test suite**

Run: `pytest src/__tests__/ -v`
Expected: PASS (所有模块的测试都通过)

**Step 5: Commit**

```bash
git add src/main.py src/router.py src/handler.py
git commit -m "feat(multi-session): integrate router into main event loop

- main.py delegates all messages to route_message()
- Rich content resolution moved from handler to router
- should_respond check moved from main to router
- handler.py fully slimmed to pure execution layer"
```

---

## Task 7: 最终验证 + 文档更新

**Step 1: Run full test suite with coverage**

Run: `pytest src/__tests__/ -v --tb=short`
Expected: ALL PASS

**Step 2: Verify no regressions**

确保以下场景在测试中覆盖：
- 普通消息（无前缀）走默认会话 ✓ (test_router.py)
- `/new` 创建并发送 ✓
- `$suffix` 路由到已有会话 ✓
- `/switch` 切换默认 ✓
- `/clear` 清除指定/默认 ✓
- `/clear-all` 清除全部 ✓
- `/interrupt` 中断指定/默认 ✓
- `/sessions` 列出会话 ✓
- session_reader 回复前缀 ✓ (test_handler.py)
- DefaultsStore 持久化 ✓ (test_defaults_store.py)

**Step 3: Commit all docs**

```bash
git add docs/plans/2026-04-23-multi-session-design.md docs/plans/2026-04-23-multi-session-plan.md
git commit -m "docs: add multi-session design doc and implementation plan"
```
