# 飞书交互层架构

## 1. Identity

- **What it is:** 基于 `lark-cli` 子进程封装的飞书 API 交互层，提供消息回复、表情反馈、事件订阅三大能力。
- **Purpose:** 将所有飞书通信统一收敛到 `subprocess.run` + `lark-cli` 的调用模式，避免直接 HTTP 调用，简化认证和错误处理。

## 2. Core Components

- `src/lark.py` (`add_reaction`, `remove_reaction`, `reply_message`): 飞书 API 交互的唯一出口，全部为同步阻塞调用，无内部依赖（叶节点模块）。
- `src/main.py` (`start_event_listener`): 启动 `lark-cli event +subscribe` 长驻子进程，以 NDJSON 格式输出事件流。
- `src/handler.py` (`handle_message`): 消费端，在消息处理流程中调用 `lark.py` 的三个函数完成表情反馈和消息回复。

## 3. Execution Flow (LLM Retrieval Map)

### 3.1 lark-cli 调用模式

所有飞书 API 调用均通过 `subprocess.run` 同步执行 `lark-cli` 命令，铁律：**必须带 `--as bot`**。

两种调用姿势：

- **封装子命令**: `lark-cli im reactions create --params {...} --data {...} --as bot` — 用于表情操作。见 `src/lark.py:12-18`、`src/lark.py:31-37`。
- **原始 API 调用**: `lark-cli api POST /open-apis/im/v1/messages/{id}/reply --data {...} --as bot --format data` — 用于消息回复。见 `src/lark.py:48-53`。

错误处理策略：失败时通过 `log_error()` 记录日志，不抛异常（静默降级）。

### 3.2 消息回复机制

- **入口**: `src/lark.py:42-57` (`reply_message`)
- **API**: `POST /open-apis/im/v1/messages/{message_id}/reply`
- **截断策略**: 文本超 4000 字符时，截断至 3950 字符并追加 `"\n\n...(回复过长，已截断)"`。见 `src/lark.py:44-45`。
- **消息格式**: `msg_type: "text"`，content 为双重 JSON 编码（`json.dumps({"text": text})` 再包入 data）。

### 3.3 表情反馈机制

表情用作"正在处理"的视觉状态指示器，生命周期与单次消息处理绑定：

1. **添加时机**: `handle_message` 异步迭代 SDK 响应流，首条 `AssistantMessage` 到达时调用 `add_reaction(message_id)`，默认 emoji 为 `"OnIt"`。见 `src/handler.py:72-73`。
2. **返回值**: `add_reaction` 返回 `reaction_id: str | None`，供后续删除使用。见 `src/lark.py:9-26`。
3. **移除时机**: 响应流消费完毕（收到 `ResultMessage`）后，立即调用 `remove_reaction(message_id, reaction_id)` 清理。见 `src/handler.py:84-85`。
4. **容错**: `reaction_id` 为 `None` 时跳过移除；移除失败仅打印日志。

### 3.4 事件订阅配置

- **入口**: `src/main.py:22-31` (`start_event_listener`)
- **命令**: `lark-cli event +subscribe --event-types im.message.receive_v1 --compact --quiet --as bot`
- **关键 flag**:
  - `--event-types im.message.receive_v1`: 仅订阅消息接收事件
  - `--compact`: 精简输出格式（NDJSON，每行一个事件）
  - `--quiet`: 抑制 lark-cli 自身日志输出
  - `--as bot`: 以 bot 身份建立 WebSocket 长连接
- **进程隔离**: `start_new_session=True`，独立进程组，便于信号清理时 `os.killpg` 整组终止。
- **stdout**: `asyncio.subprocess.PIPE`，主循环逐行读取。
- **stderr**: `asyncio.subprocess.DEVNULL`，丢弃。

## 4. Design Rationale

- **为什么用 lark-cli 而非直接 HTTP**: 认证、token 刷新、WebSocket 长连接管理全部由 lark-cli 处理，应用层只需关注业务逻辑。
- **为什么同步调用**: lark-cli 调用耗时极短（毫秒级），同步 `subprocess.run` 足够且更简单。在多 session 并发架构下，每个 worker 的短暂阻塞影响有限。
- **为什么静默降级**: 表情和回复失败不应阻断主流程，避免因飞书 API 抖动导致整个消息处理链中断。
- **4000 字符截断**: 飞书文本消息 API 的长度限制约束，硬截断是 MVP 阶段的简单方案，后续可改为分段发送或 Markdown 卡片。
