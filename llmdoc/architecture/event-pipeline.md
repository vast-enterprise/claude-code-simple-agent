# 事件驱动管道与进程管理

## 1. Identity

- **What it is:** Digital Avatar 的运行时架构——基于多进程池模型的事件驱动消息处理管道，采用 query/response 解耦模型，每个 session 持有独立 Claude 子进程。
- **Purpose:** 将飞书实时消息事件接入 Claude Code SDK，实现"接收 → 过滤 → session 分发 → 非阻塞 query → 后台 reader 异步回复"闭环。发送端立即将消息推入 Claude stdin，接收端 per-session reader task 持续读取响应并回复飞书，两者通过 FIFO 队列对齐映射。

## 2. Core Components

- `src/main.py` (`main`, `start_event_listener`, `_read_or_shutdown`, `_crash_hook`): 程序入口，负责事件循环、lark-cli 进程组管理、asyncio-native 信号处理、ClientPool + SessionDispatcher + MetricsCollector + SessionStore + DefaultsStore + HTTP server 集成、崩溃/断连通知。
- `src/router.py` (`route_message`): 统一命令路由层，从 main.py 调用。解析 `/new`、`/switch`、`/sessions`、`/clear`、`/clear-all`、`/interrupt` 命令，以及 `$suffix` 前缀路由。所有命令处理逻辑集中于此，按需调用 handler 的 send_message/session_reader。
- `src/defaults_store.py` (`DefaultsStore`): per-user 默认会话 suffix 持久化，存储在 `data/session_defaults.json`。支持 get/set/remove 操作，原子写入保证数据安全。
- `src/pool.py` (`ClientPool`): per-session 独立 `ClaudeSDKClient` 池 + per-session FIFO 消息队列。惰性创建，per-session `asyncio.Lock` 防并发重复创建，集成 `SessionStore` 持久化。`get()` 创建新 client 时自动检查 store 中的 `claude_session_id`，若存在则通过 `dataclasses.replace(options, resume=stored_sid)` 实现重启后 session 恢复。FIFO 队列 (`_pending`) 用于对齐 query → response → 飞书回复映射。
- `src/handler.py` (`should_respond`, `send_message`, `session_reader`, `compute_session_id`, `_ensure_display_names`, `_build_prompt`): 消息过滤、session ID 计算、名字解析、prompt 构建、suffix 回复前缀。瘦身为纯执行层，`send_message` 接收 router 计算好的 session_id + content，不处理命令路由。`_build_prompt` 构造带发送者上下文的 prompt（角色·名字 + open_id + 场景·chat_id），供 Claude 既能识别发送者身份又能拿到 ID 用于后续 API 交互。`send_message` 是发送端（prompt 构建 + 非阻塞 query + 入队 FIFO），`session_reader` 是接收端（持续读取响应 + 回复飞书 + 管理 reaction 生命周期）。
- `src/session.py` (`SessionDispatcher`): 调度器，直接 await send_coro（非阻塞），首次消息时启动 per-session reader task。Reader task 随 session 生命周期存在。
- `src/permissions.py` (`permission_gate`, `set_sender`, `get_sender`, `_current_sender_id`): 工具调用权限门控回调，通过 `contextvars.ContextVar` 传递 sender 身份，支持并发隔离。
- `src/lark.py` (`add_reaction`, `remove_reaction`, `reply_message`, `_reply_plain_text`, `resolve_user_name`, `resolve_chat_name`, `resolve_rich_content`, `download_message_image`, `_get_message_image_key`, `_resolve_inline_images`): 飞书交互叶节点 + 富消息解析 + 图片下载模块。API 交互全部为同步 `subprocess.run` 调用 `lark-cli`。消息回复使用 markdown 格式（`lark-cli im +messages-reply --markdown`），失败自动降级纯文本。富消息解析将 merge_forward/image/file/audio/video/sticker/media 转为可读文本，图片类消息自动下载到 `data/images/` 并返回文件路径引用。详见 `/llmdoc/architecture/lark-interaction.md` 3.2-3.6 节。
- `src/config.py` (`ROOT`, `CONFIG`, `PERSONA`, `OWNER_ID`, `NOTIFY_CONFIG`, `DISALLOWED_TOOLS`, `log_debug`, `log_info`, `log_error`): 配置加载叶节点 + 结构化日志系统。
- 可观测性模块（`notify.py`, `store.py`, `metrics.py`, `server.py`）：详见 `/llmdoc/architecture/observability.md`.

## 3. Execution Flow (LLM Retrieval Map)

### 3.1 多进程池模型

主进程管理 1 个 lark-cli 长驻子进程（WebSocket → NDJSON stdout）+ N 个 Claude SDK 子进程（per-session 惰性创建）。

- **lark-cli 子进程:** `src/main.py:38-47` — `start_new_session=True` 独立进程组，订阅 `im.message.receive_v1` 事件。
- **Claude SDK 子进程:** `src/pool.py:40-70` — `ClientPool.get()` 惰性创建，集成 `SessionStore` 持久化。

### 3.2 事件处理管道（解耦模型）

```
lark-cli stdout
     │
     ▼
 ┌─ readline ──► json.loads ──────────────────────────────┐
 │                                                         ▼
 │                                              route_message(pool, event,
 │                                                dispatcher, defaults)
 │                                                         │
 │                                    ┌────────────────────┼────────────────────┐
 │                                    ▼                    ▼                    ▼
 │                             should_respond?      命令路由（router.py）    普通消息
 │                              │ False              /new /switch $suffix    │
 │                           (drop)                  /sessions /clear       resolve_rich_content
 │                                                   /clear-all /interrupt  compute_session_id
 │                                                         │               + defaults suffix
 │                                                         ▼                    │
 │                                                  各命令 handler              ▼
 │                                                  (reply_message             dispatcher.dispatch(
 │                                                   或 dispatch)              session_id, send_coro,
 │                                                                             reader_factory)
 │                                                                                  │
 │                                    ┌─────────────────────┴──────────────────────┐
 │                                    │                                            │
 │                                    ▼ [发送端: 非阻塞]                            ▼ [接收端: 后台 reader]
 │                              send_message()                             session_reader()
 │                                    │                                    (首次消息时启动,
 │                           set_sender()                                   per-session 长驻)
 │                           _ensure_display_names()                               │
 │                           _build_prompt()                                       ▼
 │                           client.query()                                while True:
 │                           pool.enqueue()                              receive_response()
 │                                 │                                   peek_pending() → msg_id
 │                           [立即返回,                                 AssistantMessage → add_reaction
 │                            不等响应]                                 每turn收集text→reply_texts
 │                                                                     ResultMessage → 逐条reply + dequeue
 │                                                                            │
 └──────── 回到 readline 等待下一条 ◄──────────────────────────────────────────┘
```

逐步对应代码：

- **1. Subscribe:** `lark-cli` 子进程 WebSocket 接收事件 → `src/main.py` `_read_or_shutdown(listener.stdout)`。
- **2. Parse:** `src/main.py` JSON 解析，畸形行静默跳过。
- **3. Route:** `src/main.py` 调用 `route_message(pool, event, dispatcher, defaults, metrics=metrics)` → `src/router.py` (`route_message`)。
- **3a. Filter:** `src/router.py` 内部调用 `should_respond()` → `src/handler.py` (`should_respond`)（bot 消息丢弃；p2p 全响应；group 仅 @mention）。
- **3b. 富消息解析:** `src/router.py` 调用 `resolve_rich_content(event)` 检测非纯文本消息类型，返回可读文本替换原始 content。详见 `/llmdoc/architecture/lark-interaction.md` 3.5-3.6 节。
- **3c. 命令路由:** `src/router.py` 按优先级匹配命令（`/new` → `/switch` → `$suffix` → `/sessions` → `/clear` → `/clear-all` → `/interrupt` → 普通消息）。
- **3d. Session 计算:** `src/router.py` (`_compute_base_session_id` + `_compute_full_session_id`) 计算 base session_id 并拼接 suffix。普通消息使用 `defaults.get_default(base)` 获取用户默认 suffix。
- **3e. 分发:** `src/router.py` (`_dispatch_to_session`) 调用 `dispatcher.dispatch(session_id, send_message(...), reader_factory=lambda: session_reader(...))`。

**发送端 (`send_message`)：**

- **4a. Slash command 透传:** `src/handler.py` — `/` 开头的消息直接作为 prompt，不加发送者前缀。
- **4b. 名字解析:** `src/handler.py` — `_ensure_display_names()` 首次遇到新 session 时调用。
- **4c. Prompt 构建:** `src/handler.py` — `_build_prompt()` 构造带发送者上下文的 prompt，格式为 `[角色·名字 (open_id)] 在场景中说：内容`。角色区分所有者/同事，场景区分私聊/群聊（含群名和 chat_id）。名字和群名从 store 读取（由 4b 步骤提前解析）。
- **4d. 非阻塞 query:** `src/handler.py` — `pool.get()` 获取 client → `client.query(prompt)` 仅写 stdin → `pool.enqueue_message()` 入队 FIFO。立即返回，不等响应。

**接收端 (`session_reader`)：**

- **6. 持续读取:** `src/handler.py:196-263` — `while True` 循环，`async for msg in client.receive_response()` 流式读取。
- **6a. FIFO 匹配:** `src/handler.py:211-212` — `pool.peek_pending()` 从队头获取当前处理的飞书 message_id（`current_msg`）。
- **6b. Claude session 持久化:** `src/handler.py:215-218` — 首次 `AssistantMessage.session_id` 存入 store。
- **6c. Reaction 生命周期:** `src/handler.py:219-220` — `AssistantMessage` 时 `add_reaction`，`ResultMessage` 时 `remove_reaction`。
- **6d. 分段发送:** `src/handler.py:202` — `reply_texts: list[str]` 收集每个 `AssistantMessage` turn 的文本。每个 `AssistantMessage` 的 TextBlock 拼成 `turn_text`，非空则 append 进数组。`ResultMessage` 时遍历数组逐条 `reply_message` 回复飞书。见 `src/handler.py:222-227`（收集）、`src/handler.py:242-243`（逐条回复）。
- **6e. 回复 + 1:1 出队:** `src/handler.py:238-247` — `ResultMessage` 后逐条 `reply_message()` 回复飞书 → `pool.dequeue_message()` 弹出队头一条 → `metrics.record_message()` 记录。每个 ResultMessage 只 dequeue 一条。
- **6f. 状态重置:** `src/handler.py:249-254` — 重置 `reply_texts`、`reaction_id`、`current_msg`、`success`、`claude_session_saved`，准备处理下一个 turn。
- **6g. 异常处理:** `src/handler.py:256-262` — 清理残留 reaction，记录失败 metrics，弹出队头。

### 3.3 FIFO 消息队列机制（1:1 Dequeue 策略）

`ClientPool._pending` 是 per-session `collections.deque`，作为发送端和接收端的桥梁：

| 操作 | 调用方 | 代码位置 |
|------|--------|----------|
| `enqueue_message()` — 入队（message_id + content + timestamp） | `send_message` | `src/pool.py:135-143` |
| `peek_pending()` — 查看队头（不弹出） | `session_reader` | `src/pool.py:145-149` |
| `dequeue_message()` — 弹出队头 | `session_reader` | `src/pool.py:152-157` |
| `has_pending()` — 是否有待处理消息 | 调用方按需 | `src/pool.py:159-162` |
| `pending_count()` — 队列长度 | 未使用（保留） | `src/pool.py:164-167` |
| `dequeue_batch()` — 批量弹出 | 未使用（保留） | `src/pool.py:169-177` |

**1:1 Dequeue 策略：** 每个 `ResultMessage` 只 dequeue 一条 FIFO 消息。用户发一条消息 → `send_message` 做一次 `query()` + 一次 `enqueue()` → `session_reader` 收到 Claude 响应后 `peek()` 获取对应的飞书 message_id → `ResultMessage` 时 `dequeue()` + `reply_message()`。多条消息按 FIFO 顺序依次处理。

**Claude 合并行为的 Trade-off：** Claude Code 有时会将 stdin 中积压的多条 query 合并为一个 turn 处理（一次 `AssistantMessage` → `ResultMessage` 周期覆盖多条问题）。此时合并回复发到第一条消息，后续 turn 处理 FIFO 中的剩余消息。这是可接受的 trade-off——保证每条用户消息都能收到回复，代价是合并场景下第一条消息的回复内容涵盖了多个问题。

**设计迭代历史：**
1. **初始设计（1:1 dequeue）**：每个 ResultMessage dequeue 一条。问题：Claude 合并 query 时 FIFO 和 response 错位。
2. **batch dequeue（快照机制）**：首个 AssistantMessage 时快照 FIFO 长度，ResultMessage 时批量 dequeue。问题：Claude 的合并行为不可预测，批量 dequeue 太激进导致后续 turn 的回复丢失（FIFO 被提前清空）。
3. **最终方案（回归 1:1）**：接受 trade-off，保证每条消息都有回复。`dequeue_batch()` 和 `pending_count()` 保留在 `pool.py` 中但 `session_reader` 不再调用。

### 3.4 多会话命令路由（Multi-Session Routing）

`src/router.py` 提供了一套命令来实现 per-user/per-group 的多独立会话管理。

| 命令 | 行为 | 代码处理逻辑 |
|------|------|-------------|
| `/new {suffix} {message}` | 创建新会话并发消息 | 使用 `base_session_id_{suffix}` 作为目标 session。创建前不需要存在。 |
| `$suffix {message}` | 单次路由到指定会话 | 类似 `/new`，但要求目标会话必须已存在，否则提示先用 `/new` 创建。 |
| `/switch {suffix?}` | 切换默认会话 | 将 `suffix` 保存到 `DefaultsStore`。后续普通消息将自动路由到该会话。不传 suffix 则切回原始会话（重置为空）。 |
| `/sessions` | 列出当前用户所有会话 | 遍历 pool 中所有以当前 user `base_session_id` 开头的 session_id，返回列表，并标出当前 default。 |
| `/clear {suffix?}` | 清除指定/默认会话 | 默认清除当前活跃（default）会话。调用 `dispatcher.cancel_reader()` + `pool.remove()` 彻底清理独立子进程，并清空 default 记录。 |
| `/clear-all` | 清除用户所有会话 | 遍历清除该用户的所有会话子进程，并清空 default 记录。 |
| `/interrupt {suffix?}` | 中断指定/默认会话 | 向对应的 SDK client 发送控制指令。 |

所有带有 suffix 会话的回复，在经过 `session_reader` 时会自动附加 `来自 {suffix} 的回复：\n` 前缀，以明确上下文（原始会话不带前缀）。

### 3.5 进程生命周期管理

**启动顺序：**
1. `sys.excepthook = _crash_hook` 注册崩溃通知钩子
2. `start_event_listener()` 启动 lark-cli 子进程
3. `SessionStore(ROOT / "data" / "sessions.json")` 初始化持久化
4. `DefaultsStore(ROOT / "data" / "session_defaults.json")` 初始化默认会话持久化
5. `SessionDispatcher()` 构造
6. `ClientPool(options, store=store, dispatcher=dispatcher)` 构造（不 connect，惰性）
7. `MetricsCollector()` 初始化指标收集
8. `start_server(pool, metrics, port=8420)` 启动 HTTP API
9. `loop.add_signal_handler()` 注册 `SIGTERM`/`SIGINT`

**退出路径（统一走 finally）：**

| 步骤 | 行为 | 代码位置 |
|------|------|----------|
| 0 | `server_runner.cleanup()` 停止 HTTP server | `src/main.py:137-138` |
| 1 | `os.killpg(os.getpgid(listener.pid), SIGTERM)` 杀掉 lark-cli 整个进程组，5s 超时后 `SIGKILL` | `src/main.py:140-151` |
| 2 | `dispatcher.drain_all(timeout=10)` 等待 reader tasks 完成，超时后强制取消 | `src/main.py:153` |
| 3 | `pool.shutdown()` 断开所有 per-session client，清空 FIFO | `src/main.py:155` |

### 3.6 并发处理模型

系统采用 `SessionDispatcher` + `ClientPool` 实现多 session 并发处理。主循环 `readline` 后在 `router.py` 内直接 await `send_message`（非阻塞，仅写 stdin），不阻塞后续消息接收。每个 session 有独立 reader task 在后台持续读取响应。

**Session ID 计算规则：**

基础 session ID 由 `src/handler.py:25-32` 计算：

| 场景 | Base Session ID 格式 | 隔离粒度 |
|------|---------------------|----------|
| P2P 私聊 | `p2p_{sender_id}` | 按用户隔离 |
| 群聊 | `group_{chat_id}_{sender_id}` | 按群+用户隔离 |

带 suffix 的完整 session ID 由 `src/router.py:26-30` 计算（`_compute_full_session_id`）：

| 场景 | 完整 Session ID 格式 |
|------|---------------------|
| 原始会话 | `{base}` |
| 带 suffix 会话 | `{base}_{suffix}` |

示例：
- 用户 ou_xxx 原始私聊会话：`p2p_ou_xxx`
- 同一用户创建名为 "cms" 的会话：`p2p_ou_xxx_cms`
- 用户在群 oc_zzz 发言，创建 "翻译" 会话：`group_oc_zzz_ou_xxx_翻译`

**并发语义：**
- 不同 session 并行（独立 reader task + 独立 client），用户消息直达 Claude Code stdin，由 Claude 内部排队处理。
- Per-session reader task 和 client 均惰性创建。Reader task 首次收到消息时启动，随 session 生命周期存在。
- Reader 异常被 `log_error()` 捕获，自动从 `_readers` 中清理。退出时 `dispatcher.shutdown()` 取消所有 reader + `pool.shutdown()` 断开所有 client + 清空 FIFO。

**已知限制：**
- `lark.py` 中飞书交互仍为同步 `subprocess.run`，并发场景下会短暂阻塞当前 reader 的事件循环线程。实际影响有限（lark-cli 调用耗时极短）。
- lark-cli 断连后有通知但无自动重连；SDK 子进程崩溃后无自动重连。
- ClientPool 中 client 只增不减，无 idle timeout 回收机制（`src/pool.py:29-31` TODO）。

## 4. Design Rationale

- **Query/Response 解耦:** 旧架构中 `handle_message` 阻塞等待 `receive_response` 完成，同一 session 内消息必须排队。新架构将发送和接收拆开——`send_message` 仅写 stdin 后立即返回，用户可连续发送多条消息而不阻塞。Claude Code 内部按序处理，reader task 按 FIFO 顺序匹配响应和飞书回复。
- **Per-session FIFO 而非全局队列:** 每个 session 独立 FIFO，避免不同 session 的消息互相干扰。FIFO 元素包含 `message_id`（用于飞书回复定位）和 `content`（用于 metrics 记录）。
- **1:1 Dequeue 而非 Batch Dequeue:** 经历三次迭代后确定。Batch dequeue 快照机制因 Claude 合并行为不可预测而导致回复丢失，1:1 策略虽然在合并场景下回复定位不完美（合并回复发到第一条消息），但保证每条消息都能收到回复，是更安全的选择。
- **Reader task 长驻而非 per-message:** Reader task 随 session 首条消息启动，持续运行直到 session 被清理或进程退出。避免了每条消息都创建/销毁 task 的开销。
- **`/interrupt` 指令:** 使用 SDK 的 `{"subtype": "interrupt"}` 控制协议（非 POSIX 信号），通过 `pool.get_client()` 获取已有 client 后调用 `client.interrupt()`。
- **进程隔离:** `start_new_session=True` + `os.killpg` 独立进程组清理；`bypassPermissions` + `permission_gate` headless 权限；Session resume 下沉到 Pool 层自动 `--resume`。
- **Router 层抽取:** 原来 main.py 内联 dispatch 逻辑 + handler.py 自行处理 `/clear`、`/interrupt`，命令路由散落两处。引入 `router.py` 后所有命令解析和路由集中在一个模块，handler.py 瘦身为纯执行层（接收 session_id + content），main.py 只做 `route_message()` 一次调用。
- **Multi-Session 设计:** 每个用户可拥有多个独立 Claude 子进程（通过 suffix 区分），每个子进程有独立上下文和 FIFO 队列。`DefaultsStore` 持久化用户的默认 suffix，普通消息自动路由到默认会话。suffix 回复前缀（`来自 {suffix} 的回复：`）帮助用户在飞书中区分不同会话的响应。
