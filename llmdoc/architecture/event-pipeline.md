# 事件驱动管道与进程管理

## 1. Identity

- **What it is:** Digital Avatar 的运行时架构——基于双子进程模型的事件驱动消息处理管道，支持多 session 并发。
- **Purpose:** 将飞书实时消息事件接入 Claude Code SDK，实现"接收→过滤→session 分发→推理→回复"闭环，不同 session 并行处理，同一 session 内消息串行。

## 2. Core Components

- `src/main.py` (`main`, `start_event_listener`, `cleanup`, `_force_kill_sdk_process`): 程序入口，负责事件循环、双子进程生命周期管理、信号处理、SessionDispatcher 集成。
- `src/handler.py` (`should_respond`, `handle_message`, `compute_session_id`): 消息过滤（bot/p2p/group 三规则）、session ID 计算（P2P 按用户/群聊按群+用户）、单条消息完整处理流程（prompt 组装→SDK 查询→流式收集→回复）。
- `src/session.py` (`SessionDispatcher`): 并发调度器，per-session asyncio.Queue + worker task，不同 session 并行处理，同一 session 内消息串行。
- `src/permissions.py` (`permission_gate`, `set_sender`, `get_sender`, `_current_sender_id`): 工具调用权限门控回调，通过 `contextvars.ContextVar` 传递 sender 身份，支持并发隔离。
- `src/lark.py` (`add_reaction`, `remove_reaction`, `reply_message`): 飞书交互叶节点，全部为同步 `subprocess.run` 调用 `lark-cli`。
- `src/config.py` (`ROOT`, `CONFIG`, `PERSONA`, `OWNER_ID`): 配置加载叶节点，模块导入时立即执行。

## 3. Execution Flow (LLM Retrieval Map)

### 3.1 双子进程模型

系统运行时存在两个长驻子进程，均由 `main.py` 管理：

```
┌─────────────────────────────────────────────────────┐
│  Python 主进程 (main.py)                             │
│                                                     │
│  ┌──────────────────┐    ┌───────────────────────┐  │
│  │ 子进程 A          │    │ 子进程 B               │  │
│  │ lark-cli event   │    │ Claude Code SDK CLI   │  │
│  │ +subscribe       │    │ (claude_agent_sdk)    │  │
│  │                  │    │                       │  │
│  │ WebSocket 长连接  │    │ cwd=ROOT              │  │
│  │ stdout → NDJSON  │    │ 加载 CLAUDE.md+skills │  │
│  │ start_new_session│    │ bypassPermissions     │  │
│  └────────┬─────────┘    └───────────┬───────────┘  │
│           │ readline()               │ query/recv   │
│           └──────────► 事件循环 ◄─────┘              │
└─────────────────────────────────────────────────────┘
```

- **子进程 A (lark-cli):** `src/main.py:18-27` — 以 `start_new_session=True` 启动独立进程组，WebSocket 接收飞书 `im.message.receive_v1` 事件，每条事件输出一行 JSON 到 stdout。
- **子进程 B (Claude SDK):** `src/main.py:37-52` — `ClaudeSDKClient` 内部管理的 CLI 子进程，`permission_mode="bypassPermissions"` + `can_use_tool=permission_gate` 组合实现自定义权限。

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

- **1. Subscribe:** `lark-cli` 子进程 WebSocket 接收事件 → `src/main.py:91` `readline()`。
- **2. Parse:** `src/main.py:94-100` JSON 解析，畸形行静默跳过。
- **3. Filter:** `src/main.py:102` 调用 `should_respond()` → `src/handler.py:23-38`（bot 消息丢弃；p2p 全响应；group 仅 @mention）。
- **4. Session 计算:** `src/main.py:105` 调用 `compute_session_id(event)` → `src/handler.py:13-20`（P2P → `p2p_{sender_id}`；群聊 → `group_{chat_id}_{sender_id}`）。
- **5. 并发分发:** `src/main.py:107-110` 调用 `dispatcher.dispatch(session_id, handle_message(client, event))`，消息进入 per-session 队列，主循环立即回到 readline。
- **6. Prepare:** `src/handler.py:41-58` 清理 mention、调用 `permissions.set_sender(sender_id)` 写入 contextvars、组装带角色标签的 prompt。
- **7. Query:** `src/handler.py:59` `client.query(prompt, session_id=session_id)` 发送至 Claude SDK，携带 session_id 实现会话隔离。
- **8. Stream:** `src/handler.py:64-74` 异步迭代 `receive_response()`，首条 `AssistantMessage` 触发 `add_reaction`，累积文本，`ResultMessage` 终止。
- **9. Reply:** `src/handler.py:77-81` 移除表情，调用 `reply_message` 回复飞书。

### 3.3 进程生命周期管理

**启动顺序：**
1. `start_event_listener()` 启动 lark-cli 子进程 → `src/main.py:50`
2. `ClaudeSDKClient(options)` 构造 → `src/main.py:53`
3. `client.connect()` 启动 SDK CLI 子进程 → `src/main.py:85`
4. `SessionDispatcher()` 构造 → `src/main.py:88`
5. 注册 `SIGTERM`/`SIGINT` → `cleanup` → `src/main.py:81-82`

**退出路径（两条互斥）：**

| 路径 | 触发条件 | 代码位置 | 行为 |
|------|----------|----------|------|
| 信号退出 | SIGTERM/SIGINT | `src/main.py:68-79` | `os.killpg` 杀两个进程组 → `os._exit(0)` 硬退出，不经 finally |
| 正常退出 | listener stdout EOF | `src/main.py:114-121` | `listener.terminate()` → `dispatcher.shutdown()` → `client.disconnect()` → 正常返回 |

**`_force_kill_sdk_process` 实现细节：** `src/main.py:54-65` — 通过 `client._transport._process` 私有属性获取 SDK 子进程 PID，`os.killpg` 杀整个进程组。依赖 `claude_agent_sdk==0.1.x` 内部结构，版本升级时需验证。

### 3.4 并发处理模型

系统采用 `SessionDispatcher` 实现多 session 并发处理：主循环 `readline` 后立即 `dispatch` 到 per-session 队列，不阻塞后续消息接收。

**Session ID 计算规则（`src/handler.py:13-20`）：**

| 场景 | Session ID 格式 | 隔离粒度 |
|------|-----------------|----------|
| P2P 私聊 | `p2p_{sender_id}` | 按用户隔离 |
| 群聊 | `group_{chat_id}_{sender_id}` | 按群+用户隔离 |

**并发语义：**
- 不同 session 的消息由独立 worker task 并行处理（`src/session.py:21-31`）。
- 同一 session 内消息通过 `asyncio.Queue` 串行排队（`src/session.py:12-19`），保证对话上下文一致性。
- Worker 首次 dispatch 时惰性创建（`src/session.py:14-18`），后续复用。
- Worker 内异常被捕获并打印到 stderr，不影响后续消息处理（`src/session.py:28-29`）。
- 退出时 `dispatcher.shutdown()` 取消所有 worker task（`src/session.py:38-42`）。

**已知限制：**
- `lark.py` 中飞书交互仍为同步 `subprocess.run`，并发场景下会短暂阻塞当前 worker 的事件循环线程。实际影响有限（lark-cli 调用耗时极短）。
- lark-cli 或 SDK 子进程崩溃后无自动重连。

## 4. Design Rationale

- **`start_new_session=True`:** lark-cli 以独立进程组启动，使 `os.killpg` 能一次性终止其所有子进程，避免僵尸进程。
- **`os._exit(0)` 硬退出:** 信号处理器中使用硬退出而非 `sys.exit()`，确保不触发 `finally` 块中可能挂起的 `await client.disconnect()`。
- **`bypassPermissions` + `permission_gate`:** SDK 层面跳过默认交互式权限确认（无人值守场景不可用），由应用层 `permission_gate` 回调实现自定义权限逻辑。
- **SessionDispatcher per-session 队列:** 解决了串行模型下长耗时消息阻塞后续消息的问题。选择 per-session Queue + worker 而非全局线程池，是为了保证同一用户的对话上下文严格有序。
- **`contextvars.ContextVar` 替代全局变量:** `_current_sender_id` 从模块级全局变量改为 `ContextVar`，使 `permission_gate` 在并发场景下能正确识别每个请求的 sender，无需参数透传（SDK 回调签名不支持自定义 context）。
- **同步 `subprocess.run` 调用飞书 API:** `lark.py` 中飞书交互仍为同步阻塞。lark-cli 调用耗时极短（毫秒级），改为异步的收益不大，保持实现简单。
