# 事件驱动管道与进程管理

## 1. Identity

- **What it is:** Digital Avatar 的运行时架构——基于多进程池模型的事件驱动消息处理管道，支持多 session 并发，每个 session 持有独立 Claude 子进程。
- **Purpose:** 将飞书实时消息事件接入 Claude Code SDK，实现"接收→过滤→session 分发→获取独立 client→推理→回复"闭环，不同 session 并行处理，同一 session 内消息串行。

## 2. Core Components

- `src/main.py` (`main`, `start_event_listener`, `_read_or_shutdown`): 程序入口，负责事件循环、lark-cli 进程组管理、asyncio-native 信号处理、ClientPool + SessionDispatcher 集成。
- `src/pool.py` (`ClientPool`): per-session 独立 `ClaudeSDKClient` 池。惰性创建，per-session `asyncio.Lock` 防并发重复创建，`shutdown()` 断开所有 client。
- `src/handler.py` (`should_respond`, `handle_message`, `compute_session_id`): 消息过滤（bot/p2p/group 三规则）、session ID 计算（P2P 按用户/群聊按群+用户）、单条消息完整处理流程（从 pool 获取 client→prompt 组装→SDK 查询→流式收集→回复）。
- `src/session.py` (`SessionDispatcher`): 并发调度器，per-session asyncio.Queue + worker task，不同 session 并行处理，同一 session 内消息串行。
- `src/permissions.py` (`permission_gate`, `set_sender`, `get_sender`, `_current_sender_id`): 工具调用权限门控回调，通过 `contextvars.ContextVar` 传递 sender 身份，支持并发隔离。
- `src/lark.py` (`add_reaction`, `remove_reaction`, `reply_message`): 飞书交互叶节点，全部为同步 `subprocess.run` 调用 `lark-cli`。
- `src/config.py` (`ROOT`, `CONFIG`, `PERSONA`, `OWNER_ID`, `log_debug`, `log_info`, `log_error`): 配置加载叶节点 + 结构化日志系统（`logging.getLogger("avatar")`）。

## 3. Execution Flow (LLM Retrieval Map)

### 3.1 多进程池模型

系统运行时存在 1 个 lark-cli 长驻子进程 + N 个 Claude SDK 子进程（per-session 惰性创建），由 `main.py` 和 `pool.py` 协同管理：

```
┌───────────────────────────────────────────────────────────┐
│  Python 主进程 (main.py)                                   │
│                                                           │
│  ┌──────────────────┐    ┌─────────────────────────────┐  │
│  │ 子进程 A          │    │ ClientPool (pool.py)         │  │
│  │ lark-cli event   │    │                             │  │
│  │ +subscribe       │    │  session_1 → Claude CLI #1  │  │
│  │                  │    │  session_2 → Claude CLI #2  │  │
│  │ WebSocket 长连接  │    │  session_N → Claude CLI #N  │  │
│  │ stdout → NDJSON  │    │                             │  │
│  │ start_new_session│    │  惰性创建，首次消息时 connect │  │
│  └────────┬─────────┘    └───────────┬─────────────────┘  │
│           │ readline()               │ pool.get(sid)      │
│           └──────────► 事件循环 ◄─────┘                    │
└───────────────────────────────────────────────────────────┘
```

- **子进程 A (lark-cli):** `src/main.py:22-31` — 以 `start_new_session=True` 启动独立进程组，WebSocket 接收飞书 `im.message.receive_v1` 事件，每条事件输出一行 JSON 到 stdout。
- **子进程 B1..BN (Claude SDK):** `src/pool.py:26-42` — `ClientPool.get(session_id)` 惰性创建 `ClaudeSDKClient`，每个 session 持有独立 Claude 子进程，实现真正的会话上下文隔离。`permission_mode="bypassPermissions"` + `can_use_tool=permission_gate` 组合实现自定义权限。

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

- **1. Subscribe:** `lark-cli` 子进程 WebSocket 接收事件 → `src/main.py:88` `_read_or_shutdown(listener.stdout)`。
- **2. Parse:** `src/main.py:94-97` JSON 解析，畸形行静默跳过。
- **3. Filter:** `src/main.py:99` 调用 `should_respond()` → `src/handler.py:23-38`（bot 消息丢弃；p2p 全响应；group 仅 @mention）。
- **4. Session 计算:** `src/main.py:102` 调用 `compute_session_id(event)` → `src/handler.py:13-20`（P2P → `p2p_{sender_id}`；群聊 → `group_{chat_id}_{sender_id}`）。
- **5. 并发分发:** `src/main.py:104-107` 调用 `dispatcher.dispatch(session_id, handle_message(pool, event))`，消息进入 per-session 队列，主循环立即回到 readline。
- **6. 获取 client:** `src/handler.py:59` `client = await pool.get(session_id)` 从 ClientPool 获取（或惰性创建）该 session 的独立 ClaudeSDKClient。
- **7. Prepare:** `src/handler.py:41-56` 清理 mention、调用 `permissions.set_sender(sender_id)` 写入 contextvars、组装带角色标签的 prompt。
- **8. Query:** `src/handler.py:61` `client.query(prompt, session_id=session_id)` 发送至该 session 的独立 Claude SDK 子进程。
- **9. Stream:** `src/handler.py:67-82` 异步迭代 `receive_response()`，首条 `AssistantMessage` 触发 `add_reaction`，累积文本，记录 Claude session ID（debug 日志），`ResultMessage` 终止。
- **10. Reply:** `src/handler.py:84-88` 移除表情，调用 `reply_message` 回复飞书。

### 3.3 进程生命周期管理

**启动顺序：**
1. `start_event_listener()` 启动 lark-cli 子进程 → `src/main.py:76`
2. `ClientPool(options)` 构造（不 connect，惰性）→ `src/main.py:79`
3. `SessionDispatcher()` 构造 → `src/main.py:80`
4. `loop.add_signal_handler()` 注册 `SIGTERM`/`SIGINT`（asyncio-native，设 `_shutdown` Event）→ `src/main.py:82-84`

**退出路径（统一走 finally）：**

信号退出和正常退出（listener EOF）最终都经过 `finally` 块：

| 步骤 | 行为 | 代码位置 |
|------|------|----------|
| 1 | `os.killpg(os.getpgid(listener.pid), SIGTERM)` 杀掉 lark-cli 整个进程组，5s 超时后 `SIGKILL` | `src/main.py:114-125` |
| 2 | `dispatcher.drain_all(timeout=10)` 等待 worker 完成，超时强制取消 | `src/main.py:127` |
| 3 | `pool.shutdown()` 断开所有 per-session client（内部逐个 `client.disconnect()`） | `src/main.py:129` |

**优雅关闭机制：**

- `_shutdown = asyncio.Event()` 作为信号标志 → `src/main.py:19`
- `loop.add_signal_handler()` 替代 `signal.signal()`，asyncio-native 信号处理 → `src/main.py:82-84`
- `_read_or_shutdown()` 用 `asyncio.wait()` 多路复用 `readline` + `_shutdown.wait()`，信号触发时立即打断主循环 → `src/main.py:34-50`
- lark-cli 清理使用 `os.killpg()` 杀整个进程组（因 `start_new_session=True`），替代 `listener.terminate()` 避免遗留子进程
- `dispatcher.drain_all()` 先等待所有队列清空（最多 10s），超时后强制 `shutdown()` 取消 worker
- 此架构为未来**断线重连**铺路：finally 块后可接重连循环

### 3.4 并发处理模型

系统采用 `SessionDispatcher` + `ClientPool` 实现多 session 并发处理：主循环 `readline` 后立即 `dispatch` 到 per-session 队列，不阻塞后续消息接收。每个 session worker 持有独立 client（独立 Claude 子进程），实现真正的会话隔离。

**Session ID 计算规则（`src/handler.py:13-20`）：**

| 场景 | Session ID 格式 | 隔离粒度 |
|------|-----------------|----------|
| P2P 私聊 | `p2p_{sender_id}` | 按用户隔离 |
| 群聊 | `group_{chat_id}_{sender_id}` | 按群+用户隔离 |

**并发语义：**
- 不同 session 的消息由独立 worker task 并行处理（`src/session.py:22-32`），每个 worker 通过 `pool.get(session_id)` 获取独立的 `ClaudeSDKClient`。
- 同一 session 内消息通过 `asyncio.Queue` 串行排队（`src/session.py:13-20`），保证对话上下文一致性。
- Worker 首次 dispatch 时惰性创建（`src/session.py:15-19`），后续复用；client 首次 `pool.get()` 时惰性创建并 `connect()`（`src/pool.py:26-42`），后续复用。
- `ClientPool` 使用 per-session `asyncio.Lock` 防止并发 `get()` 同一 session 时重复创建 client（`src/pool.py:28-31`）。
- Worker 内异常被捕获并通过 `log_error()` 记录，不影响后续消息处理（`src/session.py:29-30`）。
- 退出时 `dispatcher.shutdown()` 取消所有 worker task，`pool.shutdown()` 断开所有 client。

**已知限制：**
- `lark.py` 中飞书交互仍为同步 `subprocess.run`，并发场景下会短暂阻塞当前 worker 的事件循环线程。实际影响有限（lark-cli 调用耗时极短）。
- lark-cli 或 SDK 子进程崩溃后无自动重连。
- ClientPool 中 client 只增不减，无 idle timeout 回收机制（`src/pool.py:17-18` TODO）。用户量大时需加定时回收不活跃 client。

## 4. Design Rationale

- **`start_new_session=True` + `os.killpg`:** lark-cli 以独立进程组启动，清理时使用 `os.killpg()` 一次性终止整个进程组，避免僵尸进程。替代了旧的 `listener.terminate()` 方式，后者可能遗留 lark-cli 的子进程。
- **`loop.add_signal_handler` 替代 `signal.signal`:** asyncio-native 信号处理，避免在非主线程注册信号的限制，与 `_shutdown = asyncio.Event()` 配合实现优雅关闭。
- **ClientPool per-session 独立 client:** 旧架构中所有 session 共享一个 `ClaudeSDKClient`，session 间可能存在上下文串扰。新架构中每个 session 持有独立 Claude 子进程，实现真正的会话隔离。惰性创建避免启动时预分配资源。
- **`bypassPermissions` + `permission_gate`:** SDK 层面跳过默认交互式权限确认（无人值守场景不可用），由应用层 `permission_gate` 回调实现自定义权限逻辑。
- **SessionDispatcher per-session 队列:** 解决了串行模型下长耗时消息阻塞后续消息的问题。选择 per-session Queue + worker 而非全局线程池，是为了保证同一用户的对话上下文严格有序。
- **`contextvars.ContextVar` 替代全局变量:** `_current_sender_id` 从模块级全局变量改为 `ContextVar`，使 `permission_gate` 在并发场景下能正确识别每个请求的 sender，无需参数透传（SDK 回调签名不支持自定义 context）。
- **同步 `subprocess.run` 调用飞书 API:** `lark.py` 中飞书交互仍为同步阻塞。lark-cli 调用耗时极短（毫秒级），改为异步的收益不大，保持实现简单。
