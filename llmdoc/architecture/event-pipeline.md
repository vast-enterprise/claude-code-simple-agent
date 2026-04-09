# 事件驱动管道与进程管理

## 1. Identity

- **What it is:** Digital Avatar 的运行时架构——基于双子进程模型的事件驱动消息处理管道。
- **Purpose:** 将飞书实时消息事件接入 Claude Code SDK，实现串行的"接收→过滤→推理→回复"闭环。

## 2. Core Components

- `src/main.py` (`main`, `start_event_listener`, `cleanup`, `_force_kill_sdk_process`): 程序入口，负责事件循环、双子进程生命周期管理、信号处理。
- `src/handler.py` (`should_respond`, `handle_message`): 消息过滤（bot/p2p/group 三规则）与单条消息完整处理流程（prompt 组装→SDK 查询→流式收集→回复）。
- `src/permissions.py` (`permission_gate`, `_current_sender_id`): 工具调用权限门控回调，通过全局变量传递 sender 身份（串行限定）。
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
 │                              handle_message
 │                                    │
 │                    ┌───────────────┼───────────────┐
 │                    ▼               ▼               ▼
 │              set sender_id   client.query()   add_reaction()
 │              (全局写入)       (SDK 推理)       (OnIt 表情)
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

- **1. Subscribe:** `lark-cli` 子进程 WebSocket 接收事件 → `src/main.py:88` `readline()`。
- **2. Parse:** `src/main.py:91-97` JSON 解析，畸形行静默跳过。
- **3. Filter:** `src/main.py:99` 调用 `should_respond()` → `src/handler.py:11-26`（bot 消息丢弃；p2p 全响应；group 仅 @mention）。
- **4. Prepare:** `src/handler.py:31-45` 清理 mention、写入 `_current_sender_id`、组装带角色标签的 prompt。
- **5. Query:** `src/handler.py:47` `client.query(prompt)` 发送至 Claude SDK。
- **6. Stream:** `src/handler.py:52-62` 异步迭代 `receive_response()`，首条 `AssistantMessage` 触发 `add_reaction`，累积文本，`ResultMessage` 终止。
- **7. Reply:** `src/handler.py:65-69` 移除表情，调用 `reply_message` 回复飞书（4000 字符截断）。

### 3.3 进程生命周期管理

**启动顺序：**
1. `start_event_listener()` 启动 lark-cli 子进程 → `src/main.py:49`
2. `ClaudeSDKClient(options)` 构造 → `src/main.py:52`
3. `client.connect()` 启动 SDK CLI 子进程 → `src/main.py:84`
4. 注册 `SIGTERM`/`SIGINT` → `cleanup` → `src/main.py:80-81`

**退出路径（两条互斥）：**

| 路径 | 触发条件 | 代码位置 | 行为 |
|------|----------|----------|------|
| 信号退出 | SIGTERM/SIGINT | `src/main.py:67-78` | `os.killpg` 杀两个进程组 → `os._exit(0)` 硬退出，不经 finally |
| 正常退出 | listener stdout EOF | `src/main.py:112-117` | `listener.terminate()` → `client.disconnect()` → 正常返回 |

**`_force_kill_sdk_process` 实现细节：** `src/main.py:54-65` — 通过 `client._transport._process` 私有属性获取 SDK 子进程 PID，`os.killpg` 杀整个进程组。依赖 `claude_agent_sdk==0.1.x` 内部结构，版本升级时需验证。

### 3.4 串行处理模型及其限制

系统采用单事件循环串行处理：`readline → handle_message → readline`，同一时刻只处理一条消息。

**已知限制：**
- `permissions._current_sender_id` 是全局可变状态（`src/permissions.py:12`），代码注释明确标注仅适用于串行，并发需改为 per-request context。
- 长耗时消息（SDK 推理可能数十秒）会阻塞后续消息处理，无排队机制。
- 所有消息共用 default session，无 session 隔离。
- lark-cli 或 SDK 子进程崩溃后无自动重连。

## 4. Design Rationale

- **`start_new_session=True`:** lark-cli 以独立进程组启动，使 `os.killpg` 能一次性终止其所有子进程，避免僵尸进程。
- **`os._exit(0)` 硬退出:** 信号处理器中使用硬退出而非 `sys.exit()`，确保不触发 `finally` 块中可能挂起的 `await client.disconnect()`。
- **`bypassPermissions` + `permission_gate`:** SDK 层面跳过默认交互式权限确认（无人值守场景不可用），由应用层 `permission_gate` 回调实现自定义权限逻辑。
- **同步 `subprocess.run` 调用飞书 API:** `lark.py` 中飞书交互为同步阻塞，因为串行模型下无并发需求，简化了实现。
