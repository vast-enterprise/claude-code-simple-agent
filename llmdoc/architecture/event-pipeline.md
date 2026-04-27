# 事件驱动管道与进程管理

## 1. Identity

- **What it is:** Digital Avatar 的运行时架构——基于多进程池模型的事件驱动消息处理管道，采用 query/response 解耦模型，每个 session 持有独立 Claude 子进程。
- **Purpose:** 将飞书实时消息事件接入 Claude Code SDK，实现"接收 → 过滤 → session 分发 → 非阻塞 query → 后台 reader 异步回复"闭环。发送端立即将消息推入 Claude stdin，接收端 per-session reader task 持续读取响应并回复飞书，两者通过 FIFO 队列对齐映射。

## 2. Core Components

- `src/main.py` (`main`, `start_event_listener`, `_read_or_shutdown`, `_crash_hook`): 程序入口，负责事件循环、lark-cli 进程组管理、asyncio-native 信号处理、ClientPool + SessionDispatcher + MetricsCollector + SessionStore + DefaultsStore + HTTP server 集成、崩溃/断连通知。
- `src/router.py` (`route_message`): 统一命令路由层，从 main.py 调用。解析 `/new`、`/switch`、`/sessions`、`/clear`、`/clear-all`、`/interrupt` 命令，以及 `$suffix` 前缀路由。所有命令处理逻辑集中于此，按需调用 handler 的 send_message/session_reader。
- `src/defaults_store.py` (`DefaultsStore`): per-user 默认会话 suffix 持久化，存储在 `data/session_defaults.json`。支持 get/set/remove 操作，原子写入保证数据安全。
- `src/pool.py` (`ClientPool`, `SessionStatus`): per-session 独立 `ClaudeSDKClient` 池 + per-session FIFO 消息队列 + per-session 状态机。惰性创建，per-session `asyncio.Lock` 防并发重复创建，集成 `SessionStore` 持久化。`get()` 创建新 client 时自动检查 store 中的 `claude_session_id`，若存在则通过 `dataclasses.replace(options, resume=stored_sid)` 实现重启后 session 恢复。FIFO 队列 (`_pending`) 用于对齐 query → response → 飞书回复映射。`SessionStatus` 枚举 + `_processing` 字典 + `get_status()` / `set_processing()` 暴露状态机观测与写入入口；`_select_lru_session()` 跳过 PROCESSING 候选，保证正在执行的 session 不被 LRU 回收。详见 3.4 节。
- `src/handler.py` (`should_respond`, `send_message`, `session_reader`, `compute_session_id`, `_ensure_display_names`, `_build_prompt`, `_is_internal_message`, `_format_with_suffix`): 消息过滤、session ID 计算、名字解析、prompt 构建、suffix 回复前缀、控制面虚构消息 ID 识别、`echo_chat_id` 主动回传。瘦身为纯执行层，`send_message` 接收 router 计算好的 session_id + content，不处理命令路由。`_build_prompt` 构造带发送者上下文的 prompt（角色·名字 + open_id + 场景·chat_id），供 Claude 既能识别发送者身份又能拿到 ID 用于后续 API 交互。`send_message` 是发送端（prompt 构建 + 非阻塞 query + `set_processing(True)` + 入队 FIFO），`session_reader` 是接收端（持续读取响应 + 回复飞书 + 管理 reaction 生命周期 + `ResultMessage` / `CancelledError` / 普通异常三路径下的 `set_processing(False)`）。`_is_internal_message` 识别 `internal-*` 前缀的虚构 message_id，使 `session_reader` 对控制面虚拟事件跳过所有 lark 副作用（`add_reaction` / `remove_reaction` / `reply_message`）但保留核心状态机推进。`_format_with_suffix` 抽出 `来自 {suffix} 的回复：\n` 前缀拼装逻辑，`ResultMessage` 处理段一次性生成 `prefixed_texts`，reply 分支与 echo 分支共用同一份带前缀文本。
- `src/session.py` (`SessionDispatcher`): 调度器，直接 await send_coro（非阻塞），首次消息时启动 per-session reader task。Reader task 随 session 生命周期存在。
- `src/permissions.py` (`permission_gate`, `set_sender`, `get_sender`, `_current_sender_id`): 工具调用权限门控回调，通过 `contextvars.ContextVar` 传递 sender 身份，支持并发隔离。
- `src/lark.py` (`add_reaction`, `remove_reaction`, `reply_message`, `_reply_plain_text`, `send_to_target`, `_prepare_markdown_text`, `_resolve_receive_id_type`, `resolve_user_name`, `resolve_chat_name`, `resolve_rich_content`, `download_message_image`, `_get_message_image_key`, `_resolve_inline_images`): 飞书交互叶节点 + 富消息解析 + 图片下载模块。API 交互全部为同步 `subprocess.run` 调用 `lark-cli`。消息回复使用 markdown 格式（`lark-cli im +messages-reply --markdown`），失败自动降级纯文本。`send_to_target` 是 echo 路径的主动发送通道（`lark-cli im messages create`），按目标 ID 前缀（`ou_*` → `open_id`、`oc_*` → `chat_id`，由 `_resolve_receive_id_type` 判定）自动选择 `receive_id_type`，失败仅 `log_error` 不降级，避免干扰核心状态机。`_prepare_markdown_text` 抽出截断（>15000 字符）+ `_convert_md_tables` 表格预处理逻辑，`reply_message` 与 `send_to_target` 共用。富消息解析将 merge_forward/image/file/audio/video/sticker/media 转为可读文本，图片类消息自动下载到 `data/images/` 并返回文件路径引用。详见 `/llmdoc/architecture/lark-interaction.md` 3.2-3.6 节。
- `src/config.py` (`ROOT`, `CONFIG`, `PERSONA`, `OWNER_ID`, `NOTIFY_CONFIG`, `DISALLOWED_TOOLS`, `log_debug`, `log_info`, `log_error`): 配置加载叶节点 + 结构化日志系统。
- 可观测性模块（`notify.py`, `store.py`, `metrics.py`, `server.py`）：详见 `/llmdoc/architecture/observability.md`. `server.py` 还承担 HTTP 调度控制面（非 `/api/*` 命名空间），含 `_parse_echo_chat_id` helper 处理 `echo_chat_id` 字段的"缺省 / 显式 str / 显式空串关闭"三态语义，详见 3.6 节。

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
 │                           set_processing(True)                       receive_response()
 │                           pool.enqueue()                             peek_pending() → msg_id
 │                                 │                                   AssistantMessage → add_reaction*
 │                           [立即返回,                                 每turn收集text→reply_texts
 │                            不等响应]                                 ResultMessage → 逐条reply* + dequeue
 │                                                                                   + set_processing(False)
 │                                                                     (*internal-* msg_id 跳过lark副作用)
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
- **4d. 非阻塞 query + 进入 PROCESSING:** `src/handler.py` — `pool.get()` 获取 client → `client.query(prompt)` 仅写 stdin → `pool.set_processing(session_id, True)` → `pool.enqueue_message()` 入队 FIFO。立即返回，不等响应。`set_processing(True)` 放在 `query` 成功之后、`enqueue` 之前：`query` 抛异常时不会遗留 stuck True 标记。状态机详见 3.4 节。

**接收端 (`session_reader`)：**

- **6. 持续读取:** `src/handler.py` (`session_reader` 主循环) — `while True` 循环，`async for msg in client.receive_response()` 流式读取。
- **6a. FIFO 匹配:** `src/handler.py` (`session_reader`) — `pool.peek_pending()` 从队头获取当前处理的飞书 message_id（`current_msg`）。
- **6b. Claude session 持久化:** `src/handler.py` (`session_reader`) — 首次 `AssistantMessage.session_id` 存入 store。
- **6c. Reaction 生命周期:** `src/handler.py` (`session_reader`) — `AssistantMessage` 时 `add_reaction`，`ResultMessage` 时 `remove_reaction`。**控制面虚构消息跳过:** 所有 lark 侧副作用（`add_reaction` / `remove_reaction` / `reply_message`）均由 `_is_internal_message(current_msg["message_id"])` 守卫，`internal-*` 前缀的消息仅推进核心状态机（`dequeue_message` / `set_processing` / `save_claude_session_id` / `metrics.record_message`），避免对不存在的飞书 message_id 触发 lark-cli subprocess 失败。详见 3.6 节的控制面契约。
- **6d. 分段发送:** `src/handler.py` (`session_reader`) — `reply_texts: list[str]` 收集每个 `AssistantMessage` turn 的文本。每个 `AssistantMessage` 的 TextBlock 拼成 `turn_text`，非空则 append 进数组。`ResultMessage` 时遍历数组逐条 `reply_message` 回复飞书。
- **6e. 回复 + 1:1 出队 + 翻回 READY:** `src/handler.py` (`session_reader`) — `ResultMessage` 后逐条 `reply_message()` 回复飞书 → `pool.dequeue_message()` 弹出队头一条 → `metrics.record_message()` 记录 → `pool.set_processing(session_id, False)` 翻回 READY。即便 `current_msg` 为空（FIFO 空但仍收到 ResultMessage），`set_processing(False)` 也照常翻转，保证状态机不 stuck。每个 ResultMessage 只 dequeue 一条。
- **6f. 状态重置:** `src/handler.py` (`session_reader`) — 重置 `reply_texts`、`reaction_id`、`current_msg`、`success`、`claude_session_saved`，准备处理下一个 turn。
- **6g. 异常处理:** `src/handler.py` (`session_reader`) — 分两个 `except` 分支保证 PROCESSING 不变式：
  - `except asyncio.CancelledError`（`/clear` / LRU eviction / shutdown 触发的取消路径）：`CancelledError` 继承 `BaseException` 不会被下面的 `except Exception` 拦下，必须单独 `set_processing(False)` 后 `raise` 给上游 `_reader_wrapper` 做任务级清理。
  - `except Exception`：清理残留 reaction（受 `_is_internal_message` 守卫），记录失败 metrics，弹出队头，最后 `set_processing(False)`。
  两路径都把状态翻回 READY，让"每个 `True` 都有配对的 `False`"这条不变式完全自洽于 `handler.py` 内部，不依赖 `pool.remove()` / `_evict_lru()` / `shutdown()` 的 `_processing.pop` 兜底。

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

### 3.4 SessionStatus 状态机

`ClientPool` 为每个 session 维护一个四值状态机，供外部观测（dashboard / HTTP 控制面）和内部决策（LRU 回收、404/409 校验）共用。状态枚举定义在 `src/pool.py` (`SessionStatus`)，运行时由 `_clients: dict[str, ClaudeSDKClient]` + `_processing: dict[str, bool]` + `SessionStore` 三方位共同决定。

| 状态 | 判定 | 含义 |
|------|------|------|
| `NONE` | 既不在 `_clients`，也不在 `store.load_all()` | session 完全不存在 |
| `CREATED` | 不在 `_clients`，但在 `store` 中 | 有元数据（可能含 `claude_session_id`）但尚无 SDK client——典型的重启后状态，下次 `pool.get()` 会触发 `--resume` |
| `READY` | 在 `_clients`，`_processing[sid]` 为 False 或缺失 | client 已 connect，空闲可接消息 |
| `PROCESSING` | 在 `_clients`，`_processing[sid]` 为 True | 已发 `client.query()`，等待 `ResultMessage` |

**状态查询与写入：**

| 方法 | 调用方 | 语义 |
|------|--------|------|
| `get_status(session_id)` | 控制面 GET `/sessions/{owner_id}`、409 校验 | 按上表计算并返回字符串状态 |
| `set_processing(session_id, bool)` | `handler.send_message` / `session_reader` | 翻转 `_processing` 标记；对未建 client 的 session 也允许设置（不会直接影响 `get_status`——`CREATED` 仍以 `_clients` 缺失为准） |

**转换时机（见 3.2 节 4d / 6e / 6g）：**

```
[NONE] ──pool.get() 创建 client──► [READY] ──send_message.query 成功──► [PROCESSING]
  ▲                                   ▲                                      │
  │                                   │                                      │
  │                          ResultMessage / Exception / CancelledError ◄────┘
  │                                   │           (set_processing False)
  │                                   │
  │                           [READY 循环等下一条]
  │
  └── pool.remove() / _evict_lru() / shutdown()（任意状态）
      → _clients.pop + _processing.pop + _locks.pop + _pending.pop
      → [NONE]（若 store 也 archive+remove）或 [CREATED]（若 store 保留）
```

**PROCESSING 不变式（`True` / `False` 配对）：**
- `send_message` 在 `client.query()` 成功后、`enqueue_message` 之前 `set_processing(True)`。query 抛异常时不写 True。
- `session_reader` 在三个出口都 `set_processing(False)`：`ResultMessage` 正常完成、`except asyncio.CancelledError`（捕获后 `raise`）、`except Exception`。`CancelledError` 单独分支是必须的——它继承 `BaseException`，不会被 `except Exception` 吞下。
- 兜底：`pool.remove()` / `_evict_lru()` / `shutdown()` 都 `self._processing.pop(sid, None)` 清理，防止 session 生命周期结束时残留状态。

**LRU 与 PROCESSING 的契约：** `_select_lru_session()` (`src/pool.py`) 在挑选 LRU 回收候选时过滤掉所有 `_processing[sid] == True` 的 session。若所有在池 session 都在 PROCESSING，则返回 `None`，`get()` 的回收循环 `break`，**池允许临时超出 `max_active_clients`**。这是有意的权衡：回收一个正在 query 的 session 会 cancel 它的 reader，丢失本轮 `ResultMessage` 和已经发出去的 prompt 的回复——比短暂超限更昂贵。

### 3.5 多会话命令路由（Multi-Session Routing）

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

### 3.6 HTTP 调度控制面（Dispatch Control Plane）

与 3.5 节的飞书侧命令路由互补，`src/server.py` 在同一个 aiohttp server 上（端口 8420，绑 `127.0.0.1`）挂载了一组**非 `/api/*` 命名空间**的调度端点，面向 owner 的主 Claude agent 远程操控 session 生命周期——典型场景是"推进 REQ-12345"这类需要主 agent 自动驱动分身会话的任务调度流。API 的使用方式见 `tripo-dispatch` skill；本节只描述其在架构上的契约与不变式。

**命名空间隔离：** 现有 `/api/*`（Dashboard + 管理端点，见 observability.md）与新控制面 `/sessions/*` 并存，后者不做鉴权（仅绑回环地址）。路由注册见 `src/server.py` (`_create_app`)。

**端点与职责：**

| 方法 + 路径 | 职责 | 主要状态码 |
|---|---|---|
| `GET /sessions/{owner_id}` | 列出 owner 名下所有 session 及 `status`、`task_id`、`task_type`、`last_active`、`pending_count` | 200 |
| `POST /sessions/{owner_id}/create` | 创建 `p2p_{owner_id}_{suffix}` session + 写入 task 元数据 + 可选 `echo_chat_id` 持久化到 `SessionStore` + dispatch 首条消息 | 200 / 400 / 409（已存在）/ 503（dispatcher 缺失） |
| `POST /sessions/{session_id}/message` | 向已存在 session 追加一条消息 + 可选 `echo_chat_id` 更新 `SessionStore` | 200 / 400 / 404（不存在）/ 409（PROCESSING）/ 503 |

**Owner 归属判定：** `_owner_matches(session_id, owner_id)` (`src/server.py`) 用**精确段匹配**而非朴素 `startswith`，避免 `p2p_ou_test` 意外命中 `p2p_ou_testing_*` 导致跨 owner 泄露。规则：
- p2p：`sid == f"p2p_{owner_id}"` 或 `sid.startswith(f"p2p_{owner_id}_")`。
- group：`sid` 以 `group_` 开头，且 `_{owner_id}` 作为完整段出现（后接 `_` 或在末尾）。

**Suffix 白名单：** `_SUFFIX_PATTERN = re.compile(r"[A-Za-z0-9_\-\.]+")` (`src/server.py`)。空格、`$`、`/` 等字符被拒绝，避免与飞书侧 `/new {suffix}` / `$suffix` 命令解析冲突。

**虚拟事件结构（控制面 → `send_message` 的桥）：**

```python
{
    "chat_type": "p2p",
    "sender_id": owner_id,          # create 用 owner_id；message 用 src.config.OWNER_ID
    "sender_type": "user",          # 防御性：避免 should_respond 过滤
    "message_id": f"internal-{uuid.uuid4()}",
    "chat_id": owner_id,
    "content": message,
}
```

派发镜像 `src/router.py::_dispatch_to_session` 的调用模式：`dispatcher.dispatch(session_id, send_message(...), reader_factory=lambda: session_reader(...))`。`_create_app(pool, metrics, *, dispatcher=None)` 和 `start_server(..., *, dispatcher=None, port=8420)` 的 `dispatcher` 参数由 `src/main.py` 在启动时注入；测试场景或未注入时，两个 POST 端点返回 503。

**`echo_chat_id` 字段（子 session ResultMessage 主动回传给 owner）：**

控制面派发的子 session 在产出 `ResultMessage` 时，除了沿原 `internal-*` message_id 路径推进核心状态机，还可以**主动 send** 一份回复到 owner 的真实飞书目标（chat_id 或 open_id）。开关由 `echo_chat_id` 字段控制，三态语义由 `_parse_echo_chat_id` (`src/server.py`) 实现：

| 端点 | 字段缺失 | 显式非空 str | 显式 `""` | 非 str |
|---|---|---|---|---|
| POST `/create` | 默认写入 `OWNER_ID`（来自 `src.config.OWNER_ID`） | 覆盖写入 store | 关闭 echo（写入空串） | 400 |
| POST `/message` | 不覆盖 store 中已有值 | 更新 store | 关闭 echo（写入空串） | 400 |

- **存储位置：** `SessionStore` 的 per-session 元数据（`echo_chat_id` 键），与 `claude_session_id` / `task_id` 等并列，重启后自动 resume。
- **消费位置：** `session_reader` 在 `ResultMessage` 处理段（`reply` 分支之后）从 `pool._store.load_all().get(session_id, {}).get("echo_chat_id", "")` 读出 target；非空才调 `send_to_target`。
- **触发面：** 仅 `ResultMessage` 阶段触发。中间 `AssistantMessage` turn、`except Exception`、`except asyncio.CancelledError` 路径**均不**触发 echo——避免半成品回复或取消事件污染 owner 单聊。
- **suffix 前缀：** echo 路径与 reply 路径共用 `_format_with_suffix` 拼装结果（一次性生成 `prefixed_texts`），所以 echo 也带 `来自 {suffix} 的回复：\n` 前缀（见 3.5 节规则）。
- **失败语义：** `send_to_target` 失败仅 `log_error`，handler 内再用 `try/except` 包一层兜底，echo 失败不会破坏 reply 分支或核心状态机。

**核心不变式：`internal-*` message_id ⇒ 跳过 lark 副作用。**

控制面与 `session_reader` 之间有一条契约：控制面负责写入 `internal-<uuid>` 形式的虚构 message_id，`_is_internal_message` (`src/handler.py`) 在 `session_reader` 内守卫所有挂在该 message_id 上的 lark-cli 子进程调用（`add_reaction`、`remove_reaction`、`reply_message`，包括 `except Exception` 分支里的 `remove_reaction`）。被屏蔽的只是用户侧可见的飞书反馈——核心状态机（`dequeue_message` / `set_processing` / `save_claude_session_id` / `metrics.record_message`）仍照常推进。没有这条契约，每次控制面派发的 Claude 响应都会触发 2-3 次 `lark-cli` subprocess 针对不存在的 message_id 失败，严重污染日志和运维噪音。

**`internal-*` 守卫与 echo 路径的解耦：** 守卫保护的是"对虚构 message_id 调 lark-cli"的路径；`send_to_target` 直接发到真实 chat_id / open_id，不依赖任何 message_id，因此**不被守卫屏蔽**也**不需要**被守卫屏蔽。两条路径并存、各管一面：

| 路径 | 受 `internal-*` 守卫影响？ | 触发条件 |
|---|---|---|
| `reply_message` / `add_reaction` / `remove_reaction` | 是（`internal-*` 时跳过） | `current_msg` 非空（处理飞书 FIFO 队头时） |
| `send_to_target`（echo 分支） | 否 | `pool._store` 里 `echo_chat_id` 非空，且当前正处于 `ResultMessage` 处理段 |

这一拆分让 `internal-*` 控制面派发既能享受"飞书副作用静默"，又能把回复主动回传给 owner——两个目标各自由 `_is_internal_message` 守卫与 `echo_chat_id` 字段独立调控。

**TOCTOU 语义（调用方必须自行串行化）：** 控制面端点的校验和派发是**非原子**的；pool 层的 per-session lock 只防重复建 client，不防并发 FIFO 入队：

- POST `/create` 的 `409 already exists` 检查与后续 `dispatch` 之间存在窗口。同一 suffix 的并发 create 两条都可能通过 409——pool 不会建两次 client，但 FIFO 会入队两条消息。
- POST `/message` 的 `404 not found` / `409 PROCESSING` 检查与后续 `dispatch` 之间存在窗口。另一路径若在这个窗口调 `pool.remove()`，`send_message` 会"隐式复活"一个新 session（等同于 create 但不写 task 元数据）。同理，两次紧挨的 message 可能都通过 409 检查。

**响应语义：** 200 表示"请求已接受、已派发给 dispatcher"，而非"Claude 已受理消息"。`send_message` 内部异常（query 失败、pool 创建失败）只 `log_error` + 尝试 `reply_message`（对 `internal-*` 是 no-op），不回流到 HTTP 层。调用方需轮询 GET `/sessions/{owner_id}` 观测目标 session 的 `status` 字段（PROCESSING → READY + `pending_count` 归零）以确认消息真正被处理。

### 3.7 进程生命周期管理

**启动顺序：**
1. `sys.excepthook = _crash_hook` 注册崩溃通知钩子
2. `start_event_listener()` 启动 lark-cli 子进程
3. `SessionStore(ROOT / "data" / "sessions.json")` 初始化持久化
4. `DefaultsStore(ROOT / "data" / "session_defaults.json")` 初始化默认会话持久化
5. `SessionDispatcher()` 构造
6. `ClientPool(options, store=store, dispatcher=dispatcher)` 构造（不 connect，惰性）
7. `MetricsCollector()` 初始化指标收集
8. `start_server(pool, metrics, dispatcher=dispatcher, port=8420)` 启动 HTTP API + 调度控制面
9. `loop.add_signal_handler()` 注册 `SIGTERM`/`SIGINT`

**退出路径（统一走 finally）：**

| 步骤 | 行为 | 代码位置 |
|------|------|----------|
| 0 | `server_runner.cleanup()` 停止 HTTP server | `src/main.py:137-138` |
| 1 | `os.killpg(os.getpgid(listener.pid), SIGTERM)` 杀掉 lark-cli 整个进程组，5s 超时后 `SIGKILL` | `src/main.py:140-151` |
| 2 | `dispatcher.drain_all(timeout=10)` 等待 reader tasks 完成，超时后强制取消 | `src/main.py:153` |
| 3 | `pool.shutdown()` 断开所有 per-session client，清空 FIFO、`_locks`、`_processing` | `src/main.py:155` |

### 3.8 并发处理模型

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
- ClientPool 无 idle timeout 主动回收；仅在 `get()` 新建时触发 LRU 回收（`_select_lru_session` 跳过 PROCESSING，见 3.4 节），池上限由 `max_active_clients`（默认 5，可配置）控制。

## 4. Design Rationale

- **Query/Response 解耦:** 旧架构中 `handle_message` 阻塞等待 `receive_response` 完成，同一 session 内消息必须排队。新架构将发送和接收拆开——`send_message` 仅写 stdin 后立即返回，用户可连续发送多条消息而不阻塞。Claude Code 内部按序处理，reader task 按 FIFO 顺序匹配响应和飞书回复。
- **Per-session FIFO 而非全局队列:** 每个 session 独立 FIFO，避免不同 session 的消息互相干扰。FIFO 元素包含 `message_id`（用于飞书回复定位）和 `content`（用于 metrics 记录）。
- **1:1 Dequeue 而非 Batch Dequeue:** 经历三次迭代后确定。Batch dequeue 快照机制因 Claude 合并行为不可预测而导致回复丢失，1:1 策略虽然在合并场景下回复定位不完美（合并回复发到第一条消息），但保证每条消息都能收到回复，是更安全的选择。
- **Reader task 长驻而非 per-message:** Reader task 随 session 首条消息启动，持续运行直到 session 被清理或进程退出。避免了每条消息都创建/销毁 task 的开销。
- **`/interrupt` 指令:** 使用 SDK 的 `{"subtype": "interrupt"}` 控制协议（非 POSIX 信号），通过 `pool.get_client()` 获取已有 client 后调用 `client.interrupt()`。
- **进程隔离:** `start_new_session=True` + `os.killpg` 独立进程组清理；`bypassPermissions` + `permission_gate` headless 权限；Session resume 下沉到 Pool 层自动 `--resume`。
- **Router 层抽取:** 原来 main.py 内联 dispatch 逻辑 + handler.py 自行处理 `/clear`、`/interrupt`，命令路由散落两处。引入 `router.py` 后所有命令解析和路由集中在一个模块，handler.py 瘦身为纯执行层（接收 session_id + content），main.py 只做 `route_message()` 一次调用。
- **Multi-Session 设计:** 每个用户可拥有多个独立 Claude 子进程（通过 suffix 区分），每个子进程有独立上下文和 FIFO 队列。`DefaultsStore` 持久化用户的默认 suffix，普通消息自动路由到默认会话。suffix 回复前缀（`来自 {suffix} 的回复：`）帮助用户在飞书中区分不同会话的响应。
- **SessionStatus 状态机单一事实来源:** `_clients` + `_processing` + `store` 三者共同决定状态，而非引入单独的状态字段——这让状态查询与底层资源永远同步，消除"状态说 READY，但 client 已被 evict"这类不一致。`_processing` 由 handler 读写，pool 只做清理兜底；PROCESSING 的 `True` / `False` 配对是 handler 的责任（含 `asyncio.CancelledError` 专门分支），而不是 pool 的。
- **LRU 跳过 PROCESSING 而非强制上限:** `_select_lru_session` 显式跳过 PROCESSING 候选，允许池临时超出 `max_active_clients`。回收正在 query 的 session 会丢失本轮响应，代价高于短暂超限——宁可多留一个 client 也不破坏正在进行的对话。
- **HTTP 调度控制面与飞书侧解耦:** 控制面端点不走飞书事件链（不经 `route_message` / `should_respond`），但复用同一套 `send_message` + `session_reader` + FIFO 路径。契约通过 `internal-*` 前缀 message_id + `_is_internal_message` 守卫建立：控制面负责写虚构 ID，handler 负责跳过 lark 副作用。这样控制面可以驱动状态机推进（dequeue / metrics / claude_session_id 持久化照常），但不对不存在的 message_id 发 lark-cli 子进程。端点放在 `/sessions/*`（非 `/api/*`）命名空间，与 Dashboard 明确隔离。
- **`echo_chat_id` 与 `internal-*` 守卫并存的契约:** 守卫的语义被严格限定为"屏蔽对虚构 message_id 的 lark-cli 调用"，而 `echo_chat_id` 走的是 `send_to_target` 主动 send 路径，发到真实 chat_id / open_id，根本不挂在 message_id 上。两条路径在 handler 里并列存在但互不依赖：reply 分支被 `_is_internal_message` 守卫包住，echo 分支由 `echo_chat_id` 是否非空控制。把 echo 单独抽出来而不是塞进守卫之内，是为了让"消息可达 owner"这件事独立于"是否有真实 message_id"——控制面派发的子 session 即便完全没有飞书消息上下文，也能把 ResultMessage 主动推回 owner；同时反向也成立——飞书侧普通会话即便没设 `echo_chat_id` 也照常 reply。两者各管一面，避免后续误把 echo 也并进守卫导致控制面派发"静默失踪"。
