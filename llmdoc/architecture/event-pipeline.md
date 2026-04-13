# 事件驱动管道与进程管理

## 1. Identity

- **What it is:** Digital Avatar 的运行时架构——基于多进程池模型的事件驱动消息处理管道，支持多 session 并发，每个 session 持有独立 Claude 子进程。
- **Purpose:** 将飞书实时消息事件接入 Claude Code SDK，实现"接收→过滤→session 分发→获取独立 client→推理→回复"闭环，不同 session 并行处理，同一 session 内消息串行。

## 2. Core Components

- `src/main.py` (`main`, `start_event_listener`, `_read_or_shutdown`, `_crash_hook`): 程序入口，负责事件循环、lark-cli 进程组管理、asyncio-native 信号处理、ClientPool + SessionDispatcher + MetricsCollector + SessionStore + HTTP server 集成、崩溃/断连通知。
- `src/pool.py` (`ClientPool`): per-session 独立 `ClaudeSDKClient` 池。惰性创建，per-session `asyncio.Lock` 防并发重复创建，集成 `SessionStore` 持久化，支持 session resume（`get_claude_session_id`/`save_claude_session_id`），`remove()` 带 per-session lock 防并发冲突。
- `src/handler.py` (`should_respond`, `handle_message`, `compute_session_id`, `parse_command`, `handle_command`): 消息过滤、飞书指令解析（`/clear` `/compact` `/sessions` `/status`）、session ID 计算、单条消息处理流程（指令优先、Claude session resume、metrics 集成）。
- `src/session.py` (`SessionDispatcher`): 并发调度器，per-session asyncio.Queue + worker task，不同 session 并行处理，同一 session 内消息串行。
- `src/permissions.py` (`permission_gate`, `set_sender`, `get_sender`, `_current_sender_id`): 工具调用权限门控回调，通过 `contextvars.ContextVar` 传递 sender 身份，支持并发隔离。
- `src/lark.py` (`add_reaction`, `remove_reaction`, `reply_message`): 飞书交互叶节点，全部为同步 `subprocess.run` 调用 `lark-cli`。
- `src/config.py` (`ROOT`, `CONFIG`, `PERSONA`, `OWNER_ID`, `NOTIFY_CONFIG`, `DISALLOWED_TOOLS`, `log_debug`, `log_info`, `log_error`): 配置加载叶节点 + 结构化日志系统（`logging.getLogger("avatar")`）。
- 可观测性模块（`notify.py`, `store.py`, `metrics.py`, `server.py`）：详见 `/llmdoc/architecture/observability.md`.

## 3. Execution Flow (LLM Retrieval Map)

### 3.1 多进程池模型

系统运行时存在 1 个 lark-cli 长驻子进程 + N 个 Claude SDK 子进程（per-session 惰性创建），由 `main.py` 和 `pool.py` 协同管理：

主进程管理 1 个 lark-cli 长驻子进程（WebSocket → NDJSON stdout）+ N 个 Claude SDK 子进程（per-session 惰性创建）。

- **lark-cli 子进程:** `src/main.py:38-47` — `start_new_session=True` 独立进程组，订阅 `im.message.receive_v1` 事件。
- **Claude SDK 子进程:** `src/pool.py:36-59` — `ClientPool.get()` 惰性创建，集成 `SessionStore` 持久化。

### 3.2 事件处理管道

```
lark-cli stdout
     │
     ▼
 ┌─ readline ──► json.loads ──► should_respond ─┐
 │                                    │ False    │ True
 │                                 (drop)        ▼
 │                          compute_session_id(event)
 │                                    │
 │                                    ▼
 │                          dispatcher.dispatch(session_id, coro)
 │                                    │
 │                    ┌───────────────┴───────────────┐
 │                    │ per-session Queue              │
 │                    │ (不同 session 并行,             │
 │                    │  同一 session 串行)             │
 │                    └───────────────┬───────────────┘
 │                                    ▼
 │                              handle_message
 │                                    │
 │                    ┌───────────────┼───────────────┐
 │                    ▼               ▼               ▼
 │              set_sender()    client.query()   add_reaction()
 │              (contextvars)   (SDK 推理,        (OnIt 表情)
 │                              session_id)
 │                                    │
 │                                    ▼
 │                          receive_response() 流式迭代
 │                          累积 TextBlock.text
 │                                    │
 │                                    ▼
 │                          remove_reaction()
 │                          reply_message()
 │                                    │
 └────────────── 回到 readline 等待下一条 ◄──────┘
```

逐步对应代码：

- **1. Subscribe:** `lark-cli` 子进程 WebSocket 接收事件 → `src/main.py:108` `_read_or_shutdown(listener.stdout)`。
- **2. Parse:** `src/main.py:113-119` JSON 解析，畸形行静默跳过。
- **3. Filter:** `src/main.py:121` 调用 `should_respond()` → `src/handler.py:32-47`（bot 消息丢弃；p2p 全响应；group 仅 @mention）。
- **4. Session 计算:** `src/main.py:124` 调用 `compute_session_id(event)` → `src/handler.py:22-29`.
- **5. 并发分发:** `src/main.py:126-129` 调用 `dispatcher.dispatch(session_id, handle_message(pool, event, metrics=metrics))`，消息进入 per-session 队列。
- **5a. 指令检测:** `src/handler.py:123-127` `parse_command()` 检测 `/` 开头指令，匹配则直接处理不经过 Claude。
- **6. 获取 client:** `src/handler.py:139` `client = await pool.get(session_id)` 从 ClientPool 获取 client（`SessionStore` 同步持久化）。
- **6a. Session Resume:** `src/handler.py:142-143` 查询 `pool.get_claude_session_id(session_id)` 获取上次 Claude session_id 传入 query。
- **7. Prepare:** `src/handler.py:129-132` 清理 mention、设置 sender、组装 prompt。
- **8. Query:** `src/handler.py:143` `client.query(prompt, session_id=claude_sid)`.
- **9. Stream:** `src/handler.py:148-166` 异步迭代响应，首次 `AssistantMessage.session_id` 持久化到 store，收集文本。
- **10. Reply:** `src/handler.py:168-172` 移除表情，调用 `reply_message`。
- **11. Metrics:** `src/handler.py:177-179` `finally` 块中 `metrics.record_message()` 确保异常也计入。

### 3.3 进程生命周期管理

**启动顺序：**
1. `sys.excepthook = _crash_hook` 注册崩溃通知钩子 → `src/main.py:35`
2. `start_event_listener()` 启动 lark-cli 子进程 → `src/main.py:92`
3. `SessionStore(ROOT / "data" / "sessions.json")` 初始化持久化 → `src/main.py:95`
4. `ClientPool(options, store=store)` 构造（不 connect，惰性）→ `src/main.py:96`
5. `MetricsCollector()` 初始化指标收集 → `src/main.py:97`
6. `SessionDispatcher()` 构造 → `src/main.py:98`
7. `start_server(pool, metrics, port=8420)` 启动 HTTP API → `src/main.py:100`
8. `loop.add_signal_handler()` 注册 `SIGTERM`/`SIGINT` → `src/main.py:103-104`

**退出路径（统一走 finally）：**

信号退出和正常退出（listener EOF）最终都经过 `finally` 块：

| 步骤 | 行为 | 代码位置 |
|------|------|----------|
| 0 | `server_runner.cleanup()` 停止 HTTP server | `src/main.py:137` |
| 1 | `os.killpg(os.getpgid(listener.pid), SIGTERM)` 杀掉 lark-cli 整个进程组，5s 超时后 `SIGKILL` | `src/main.py:139-150` |
| 2 | `dispatcher.drain_all(timeout=10)` 等待 worker 完成，超时强制取消 | `src/main.py:152` |
| 3 | `pool.shutdown()` 断开所有 per-session client | `src/main.py:154` |

**优雅关闭机制：**
`_shutdown = asyncio.Event()` + `loop.add_signal_handler()` 配合 `_read_or_shutdown()` 多路复用（`src/main.py:24,50-66,103-104`）。lark-cli 用 `os.killpg()` 杀进程组，`dispatcher.drain_all()` 等待 10s 后强制取消 worker。

### 3.4 并发处理模型

系统采用 `SessionDispatcher` + `ClientPool` 实现多 session 并发处理：主循环 `readline` 后立即 `dispatch` 到 per-session 队列，不阻塞后续消息接收。每个 session worker 持有独立 client（独立 Claude 子进程），实现真正的会话隔离。

**Session ID 计算规则（`src/handler.py:13-20`）：**

| 场景 | Session ID 格式 | 隔离粒度 |
|------|-----------------|----------|
| P2P 私聊 | `p2p_{sender_id}` | 按用户隔离 |
| 群聊 | `group_{chat_id}_{sender_id}` | 按群+用户隔离 |

**并发语义：**
- 不同 session 并行（独立 worker task + 独立 client），同一 session 串行（`asyncio.Queue`）。
- Worker 和 client 均惰性创建，per-session `asyncio.Lock` 防并发重复创建。
- Worker 异常被 `log_error()` 捕获，不中断事件循环。退出时 `dispatcher.shutdown()` + `pool.shutdown()` 清理。

**已知限制：**
- `lark.py` 中飞书交互仍为同步 `subprocess.run`，并发场景下会短暂阻塞当前 worker 的事件循环线程。实际影响有限（lark-cli 调用耗时极短）。
- lark-cli 断连后有通知但无自动重连；SDK 子进程崩溃后无自动重连。
- ClientPool 中 client 只增不减，无 idle timeout 回收机制（`src/pool.py:26-28` TODO）。用户量大时需加定时回收不活跃 client。可通过 `/clear` 指令或 HTTP API 手动清理。
- `compact` 端点和指令尚未实现（TODO）。

## 4. Design Rationale

- **`start_new_session=True` + `os.killpg`:** 独立进程组 + 整组清理，避免僵尸进程。
- **Per-session 独立 client:** 每个 session 独立 Claude 子进程，消除上下文串扰。惰性创建避免预分配。
- **`bypassPermissions` + `permission_gate`:** headless 场景跳过交互式确认，应用层自定义权限。
- **Per-session Queue + worker:** 保证同一用户对话上下文严格有序，不同用户并行。
- **`contextvars.ContextVar`:** 替代全局变量，SDK 回调并发安全。
- **同步 `subprocess.run`:** lark-cli 毫秒级调用，同步更简单。
