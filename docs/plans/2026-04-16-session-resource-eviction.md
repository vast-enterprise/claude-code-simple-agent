# Session 资源回收 — 实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 为 ClientPool 增加 LRU 按需回收能力，限制并发 Claude 子进程数，降低内存/进程资源占用。

**Architecture:** `ClientPool.get()` 创建新 client 前，若 `len(self._clients) >= max_active_clients`，按 `last_active` 选出最久未活跃的 session，断开其 client + 取消 reader + 清空 FIFO，保留 store 元数据以支持后续 `--resume` 恢复上下文。Dashboard 新增「活跃进程」卡片观测容量。

**Tech Stack:** Python 3.12, asyncio, claude-agent-sdk, aiohttp, Tailwind CSS (CDN), pytest.

**设计文档:** `docs/plans/2026-04-16-session-resource-eviction-design.md`

**当前状态:**
- ✅ `config.py` 已加 `MAX_ACTIVE_CLIENTS`
- ✅ `config.example.json` 已加 `max_active_clients: 5`
- ✅ `src/__tests__/pool.py::TestPoolEviction` 已写 9 个测试（目前 RED）
- ⏳ 剩余：pool.py 实现、main.py 注入、server.py/dashboard.html 可观测性

---

## Task 1: 让 ClientPool 接受 max_active_clients 和 dispatcher 参数

**Files:**
- Modify: `src/pool.py` (构造函数)
- Test: `src/__tests__/pool.py::TestPoolEviction::test_active_client_count` / `test_max_active_clients_property` / `test_default_max_active_clients`

**Step 1: 跑失败测试确认 RED**

Run: `python3 -m pytest src/__tests__/pool.py::TestPoolEviction::test_default_max_active_clients -v`
Expected: FAIL `AttributeError: 'ClientPool' object has no attribute 'max_active_clients'`

**Step 2: 修改 `ClientPool.__init__`**

替换 `src/pool.py:33-38`：

```python
def __init__(
    self,
    options: ClaudeAgentOptions,
    *,
    store: SessionStore | None = None,
    dispatcher: "SessionDispatcher | None" = None,
    max_active_clients: int = 5,
):
    self._options = options
    self._store = store
    self._dispatcher = dispatcher
    self._max_active_clients = max_active_clients
    self._clients: dict[str, ClaudeSDKClient] = {}
    self._locks: dict[str, asyncio.Lock] = {}
    self._pending: dict[str, collections.deque] = {}
```

**Step 3: 加只读属性 + active_client_count**

在类中合适位置（`shutdown` 前）添加：

```python
@property
def max_active_clients(self) -> int:
    """最大并发 client 数阈值（只读）"""
    return self._max_active_clients

def active_client_count(self) -> int:
    """当前活跃 client 数量"""
    return len(self._clients)
```

**Step 4: 更新 TYPE_CHECKING 导入**

`src/pool.py:16-17` 改为：

```python
if TYPE_CHECKING:
    from src.session import SessionDispatcher
    from src.store import SessionStore
```

**Step 5: 跑测试验证 GREEN**

Run: `python3 -m pytest src/__tests__/pool.py::TestPoolEviction::test_default_max_active_clients src/__tests__/pool.py::TestPoolEviction::test_max_active_clients_property src/__tests__/pool.py::TestPoolEviction::test_active_client_count -v`
Expected: 3 passed

---

## Task 2: 实现 _select_lru_session

**Files:**
- Modify: `src/pool.py`

**Step 1: 在 `ClientPool` 类中添加 `_select_lru_session` 方法**

在 `get_client()` 方法前插入：

```python
def _select_lru_session(self) -> str | None:
    """选择最久未活跃的 session（基于 store 中的 last_active）。

    只在 self._clients 中当前存在的 session 里选择，
    避免选到已经被回收但还在 store 里的 session。
    """
    if not self._clients:
        return None

    store_data: dict = {}
    if self._store:
        store_data = self._store.load_all()

    def sort_key(sid: str) -> str:
        return store_data.get(sid, {}).get("last_active", "")

    return min(self._clients.keys(), key=sort_key)
```

**Step 2: 无独立测试，合并到 Task 3 验证**

跳过独立验证，LRU 逻辑的正确性在 `test_evicts_lru_when_exceeds_limit` 中验证。

---

## Task 3: 实现 _evict_lru

**Files:**
- Modify: `src/pool.py`
- Test: `src/__tests__/pool.py::TestPoolEviction::test_eviction_disconnects_client` + `test_eviction_clears_pending` + `test_preserves_metadata_after_eviction`

**Step 1: 跑测试确认 RED**

Run: `python3 -m pytest src/__tests__/pool.py::TestPoolEviction::test_eviction_disconnects_client -v`
Expected: FAIL

**Step 2: 在 `_select_lru_session` 后添加 `_evict_lru` 方法**

```python
async def _evict_lru(self) -> str | None:
    """回收最久未活跃的 session。

    动作：
    1. 从 self._clients 中移除并 disconnect
    2. 通过 dispatcher 取消 reader task
    3. 清空该 session 的 FIFO 队列
    4. 保留 store 元数据（含 claude_session_id），供后续 resume

    Returns:
        被回收的 session_id，无可回收则 None。
    """
    session_id = self._select_lru_session()
    if not session_id:
        return None

    client = self._clients.pop(session_id, None)
    if client:
        try:
            await client.disconnect()
        except Exception as e:
            log_error(f"[Eviction] disconnect {session_id} 失败: {e}")

    if self._dispatcher:
        try:
            self._dispatcher.cancel_reader(session_id)
        except Exception as e:
            log_error(f"[Eviction] cancel_reader {session_id} 失败: {e}")

    pending = self._pending.pop(session_id, None)
    pending_count = len(pending) if pending else 0
    if pending_count > 0:
        log_error(f"[Eviction] 丢弃 {session_id} 的 {pending_count} 条待处理消息")

    log_debug(f"[Eviction] session={session_id} evicted (pending_dropped={pending_count})")
    return session_id
```

**Step 3: 跑测试（预计仍然 FAIL，因为 get() 还未调用 _evict_lru）**

Run: `python3 -m pytest src/__tests__/pool.py::TestPoolEviction::test_eviction_disconnects_client -v`
Expected: still FAIL（`_evict_lru` 实现完成但未被调用）

继续 Task 4。

---

## Task 4: 在 get() 中接入 LRU 回收

**Files:**
- Modify: `src/pool.py::get`
- Test: 全部 `TestPoolEviction` 用例

**Step 1: 修改 `get()` 方法 — 在 `if session_id not in self._clients` 分支内**

将 `src/pool.py:45-64` 的逻辑修改为：

```python
async with self._locks[session_id]:
    if session_id not in self._clients:
        # 超过阈值先回收最久未活跃的 client（不能回收自己）
        while len(self._clients) >= self._max_active_clients:
            evicted = await self._evict_lru()
            if evicted is None:
                break  # 无可回收的 session，防止死循环

        # 如果 store 中有历史 claude_session_id，用 --resume 恢复
        opts = self._options
        stored_sid = self.get_claude_session_id(session_id)
        if stored_sid:
            opts = dataclasses.replace(self._options, resume=stored_sid)
            log_debug(f"resume session: {session_id} → {stored_sid}")

        client = ClaudeSDKClient(options=opts)
        try:
            await client.connect()
        except Exception:
            with contextlib.suppress(Exception):
                await client.disconnect()
            raise
        self._clients[session_id] = client
        log_debug(f"新建 client: {session_id}")
        if self._store:
            self._store.save(session_id, {})
```

**Step 2: 跑完整回收测试套件**

Run: `python3 -m pytest src/__tests__/pool.py::TestPoolEviction -v`
Expected: 9 passed

**Step 3: 跑全部 pool 测试确认没破坏既有逻辑**

Run: `python3 -m pytest src/__tests__/pool.py -v`
Expected: 36 passed

**Step 4: Commit**

```bash
git add src/pool.py src/__tests__/pool.py
git commit -m "feat(pool): 增加 LRU 按需回收机制

ClientPool 新增 max_active_clients 阈值（默认 5）。get() 前检查
self._clients 数量，超限则按 store 中 last_active 选出最久未活跃的
session 回收：disconnect client + cancel reader task + 清空 FIFO，
保留 store 元数据供后续 --resume。

测试覆盖 9 个场景：LRU 选择、元数据保留、resume、阈值边界、
FIFO 清理、disconnect 调用、属性访问。"
```

---

## Task 5: main.py 注入 dispatcher 到 ClientPool

**Files:**
- Modify: `src/main.py:95-98`

**Step 1: 调整创建顺序 + 传入 dispatcher 和 MAX_ACTIVE_CLIENTS**

找到 `src/main.py:95-98`：

```python
    store = SessionStore(ROOT / "data" / "sessions.json")
    pool = ClientPool(options, store=store)
    metrics = MetricsCollector()
    dispatcher = SessionDispatcher()
```

改为：

```python
    store = SessionStore(ROOT / "data" / "sessions.json")
    dispatcher = SessionDispatcher()
    pool = ClientPool(
        options,
        store=store,
        dispatcher=dispatcher,
        max_active_clients=MAX_ACTIVE_CLIENTS,
    )
    metrics = MetricsCollector()
```

**Step 2: 更新 import**

修改 `src/main.py:13`：

```python
from src.config import ROOT, CONFIG, PERSONA, HEADLESS_RULES, DISALLOWED_TOOLS, MAX_ACTIVE_CLIENTS, log_debug, log_info
```

**Step 3: 语法检查**

Run: `python3 -c "import ast; ast.parse(open('src/main.py').read()); print('OK')"`
Expected: `OK`

**Step 4: 跑所有测试确认没破坏其他模块**

Run: `python3 -m pytest src/__tests__/ -v 2>&1 | tail -20`
Expected: all passed

---

## Task 6: /api/status 增加 active_clients / max_active_clients

**Files:**
- Modify: `src/server.py::_handle_status`

**Step 1: 修改 `src/server.py:111-116`**

原代码：

```python
async def _handle_status(request):
    metrics = request.app["metrics"]
    pool = request.app["pool"]
    s = metrics.status()
    s["active_sessions"] = len(pool.list_sessions())
    return _json(s)
```

改为：

```python
async def _handle_status(request):
    metrics = request.app["metrics"]
    pool = request.app["pool"]
    s = metrics.status()
    s["active_sessions"] = len(pool.list_sessions())
    s["active_clients"] = pool.active_client_count()
    s["max_active_clients"] = pool.max_active_clients
    return _json(s)
```

**Step 2: 手动验证 API 字段结构**

Run: `python3 -c "
from unittest.mock import MagicMock
from src.pool import ClientPool
pool = ClientPool(MagicMock(), max_active_clients=7)
print('active_clients:', pool.active_client_count())
print('max_active_clients:', pool.max_active_clients)
"`
Expected:
```
active_clients: 0
max_active_clients: 7
```

---

## Task 7: Dashboard 新增「活跃进程」卡片

**Files:**
- Modify: `src/dashboard.html` (状态卡片区 + fetchStatus 逻辑)

**Step 1: 在状态卡片区增加第 5 张卡**

找到 `src/dashboard.html` 的状态卡片 grid（`<section id="status-cards" class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">`），改为 5 列：

```html
    <section id="status-cards" class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
```

在「活跃 Session」卡片之后插入「活跃进程」卡：

```html
      <!-- 活跃进程（回收策略容量） -->
      <div class="bg-gray-800 rounded-lg shadow-lg p-5 border-l-4 border-yellow-500">
        <div class="text-sm text-gray-400 mb-1">活跃进程</div>
        <div class="flex items-baseline gap-1">
          <span id="card-active-clients" class="text-2xl font-bold text-yellow-400">--</span>
          <span class="text-sm text-gray-500">/</span>
          <span id="card-max-clients" class="text-sm text-gray-500">--</span>
        </div>
      </div>
```

**Step 2: 在 `fetchStatus()` 中填充新字段**

找到 `document.getElementById('card-sessions').textContent = data.active_sessions ?? '--';` 这一行（约 `src/dashboard.html:177`），在其后追加：

```javascript
    document.getElementById('card-active-clients').textContent = data.active_clients ?? '--';
    document.getElementById('card-max-clients').textContent = data.max_active_clients ?? '--';
```

**Step 3: 验证 HTML 结构未破坏**

Run: `grep -n 'card-active-clients\|card-max-clients\|lg:grid-cols-5' src/dashboard.html`
Expected: 输出 3 个匹配行（DOM id 各一个 + grid 类一个）

---

## Task 8: 启动 + 端到端验证

**Step 1: 停掉旧进程（如果在跑）**

Run: `ps aux | grep 'python3.*src/main.py' | grep -v grep | awk '{print $2}' | xargs -r kill -TERM`
Expected: 无报错

**Step 2: 启动服务（后台）**

Run: `cd /Users/macbookair/Desktop/projects/tripo-work-center && python3 -m src.main > /tmp/avatar.log 2>&1 &`
Expected: 返回 PID，5 秒后 `/tmp/avatar.log` 显示 "飞书事件监听已启动"

**Step 3: curl 验证 /api/status 返回新字段**

Run: `sleep 3 && curl -s http://127.0.0.1:8420/api/status | python3 -m json.tool`
Expected: 输出包含 `active_clients` 和 `max_active_clients` 字段（初始值 0 / 5）

**Step 4: 手动触发回收验证（可选）**

通过飞书发 6 条来自不同 session 的消息（或降低 `max_active_clients=2` 后重启测试），观察日志：

Run: `grep -E 'Eviction|新建 client|resume' /tmp/avatar.log`
Expected: 能看到 `[Eviction] session=xxx evicted` 日志

**Step 5: Commit 可观测性改动**

```bash
git add src/main.py src/server.py src/dashboard.html src/config.py config.example.json
git commit -m "feat: session 回收的可观测性 + 配置接入

- main.py 注入 dispatcher 到 ClientPool，传递 MAX_ACTIVE_CLIENTS
- /api/status 新增 active_clients / max_active_clients 字段
- Dashboard 新增「活跃进程」卡片（黄色），显示 N/M 格式
- config 支持 max_active_clients（默认 5）"
```

---

## Task 9: 更新 llmdoc（交付前）

**Files:**
- Modify: `llmdoc/architecture/event-pipeline.md`（ClientPool 部分）
- Modify: `llmdoc/architecture/observability.md`（HTTP API 部分）
- Modify: `llmdoc/index.md`（如有摘要变更）

**Step 1: 询问用户是否触发 recorder agent 更新**

> **按 CLAUDE.md 规则：禁止自动更新 llmdoc，必须用 AskUserQuestion 让用户决定。**

通过 `AskUserQuestion` 提供「用 recorder agent 更新文档」选项。

**Step 2: 用户同意后，启动 recorder agent**

如用户同意，以 subagent_type=tr:recorder 启动，prompt 说明回收机制新增点。

---

## 完成标准（Definition of Done）

- [ ] `python3 -m pytest src/__tests__/pool.py -v` 全绿（36 通过，含 9 个新增 Eviction 测试）
- [ ] `python3 -m pytest src/__tests__/ -v` 全绿
- [ ] 服务启动后 `/api/status` 返回 `active_clients` 和 `max_active_clients`
- [ ] Dashboard 打开后能看到「活跃进程」卡片显示 `N / 5`
- [ ] 日志中能观测到 `[Eviction]` 相关消息（超阈值时）
- [ ] 所有相关提交已 commit（未 push，按 CLAUDE.md 约束）
- [ ] 用户确认后 llmdoc 已更新

## 关键文件位置速查

| 文件 | 关键位置 |
|------|----------|
| `src/pool.py` | `__init__` (33-) / `get()` (40-70) / 新增 `_select_lru_session()` / `_evict_lru()` |
| `src/main.py` | `store/pool/dispatcher` 初始化 (95-98) |
| `src/config.py` | `MAX_ACTIVE_CLIENTS` (58) ✅ |
| `src/server.py` | `_handle_status` (111-116) |
| `src/dashboard.html` | `status-cards` section + `fetchStatus` 函数 |
| `config.example.json` | `max_active_clients: 5` (21) ✅ |
| `src/__tests__/pool.py` | `TestPoolEviction` 类 (371-) ✅ |
