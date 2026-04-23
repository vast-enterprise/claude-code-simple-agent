# 多会话（Multi-Session）设计方案

> 日期：2026-04-23
> 状态：已确认

## 1. 背景

当前每个用户在单聊/群聊中只有一个 session（`p2p_{user_id}` / `group_{chat_id}_{sender_id}`），对应一个独立的 Claude SDK Client。用户需要同时维护多个独立对话上下文（如"cms翻译需求"和"bug修复"并行推进），当前架构不支持。

## 2. 方案选择

**方案 B：新增 router.py 中间层 + 迁移已有命令**

- 新增 `src/router.py` 统一管理所有命令路由
- 从 `handler.py` 迁出 `/clear`、`/interrupt` 等命令处理
- `handler.py` 瘦身为纯执行层（query + reader）
- `pool.py`、`session.py` 不改，session_id 带 suffix 后自然映射到独立 client

## 3. session_id 格式

| 场景 | 原始会话 | 带 suffix 会话 |
|------|---------|---------------|
| P2P | `p2p_{user_id}` | `p2p_{user_id}_{suffix}` |
| 群聊 | `group_{chat_id}_{sender_id}` | `group_{chat_id}_{sender_id}_{suffix}` |

## 4. 用户命令

| 命令 | 行为 |
|------|------|
| `/new {suffix} {message}` | 创建新会话并发送第一条消息。suffix 和 message 都必填，缺参数回复用法提示。若会话已存在则复用 |
| `$suffix {message}` | 路由到指定 suffix 的会话。会话不存在时报错提示 |
| `/switch {suffix?}` | 切换默认会话。无参数切回原始会话。目标不存在时报错。切换成功明确提示 |
| `/sessions` | 列出当前用户所有活跃会话（suffix、创建时间、是否默认） |
| `/clear {suffix?}` | 清除指定/默认会话。无参数清除当前默认 |
| `/clear-all` | 清除该用户的所有会话 |
| `/interrupt {suffix?}` | 中断指定/默认会话的当前任务 |
| 普通消息（无前缀） | 发送到当前默认会话 |
| `/xxx`（其他 slash cmd） | 透传给当前默认会话的 Claude |

命令解析优先级：`/new` > `/switch` > `/sessions` > `/clear-all` > `/clear` > `/interrupt` > `$suffix` > 其他 slash cmd > 普通消息。

## 5. 数据流

```
lark-cli stdout → main.py (parse + filter)
    │
    ▼
router.route_message(pool, event, dispatcher, defaults, metrics)
    │
    ├─ /new {suffix} {msg}  → 计算 {base}_{suffix} → dispatch send_message
    ├─ $suffix {msg}        → 查找 {base}_{suffix} → dispatch send_message
    ├─ /switch {suffix?}    → 更新 defaults → reply 提示
    ├─ /sessions            → 查询 store → reply 列表
    ├─ /clear-all           → 逐个 pool.remove → reply
    ├─ /clear {suffix?}     → pool.remove(target) → reply
    ├─ /interrupt {suffix?} → client.interrupt() → reply
    ├─ /xxx (其他 slash cmd) → 透传给默认 session 的 Claude
    └─ 普通消息              → 默认 session_id → dispatch send_message
```

## 6. 新增模块

### 6.1 DefaultsStore（`src/defaults_store.py`）

per-user 默认会话 suffix 持久化，存储在 `data/session_defaults.json`：

```json
{
  "p2p_{user_id}": null,
  "group_{chat_id}_{sender_id}": "cms翻译需求"
}
```

`null` 表示默认到原始会话。

接口：
- `get_default(base_session_id) -> str | None`
- `set_default(base_session_id, suffix: str | None)`
- `remove_user(base_session_id)`

### 6.2 router.py

核心函数 `route_message(pool, event, dispatcher, defaults, *, metrics)` 统一处理所有命令路由。

辅助函数：
- `_compute_base_session_id(event)` — 原始 session_id（不带 suffix）
- `_compute_full_session_id(base, suffix)` — 拼接
- `_extract_suffix(session_id, base)` — 从完整 session_id 提取 suffix
- `_list_user_sessions(pool, base)` — 查询用户所有会话
- `_dispatch_to_session(pool, event, dispatcher, session_id, content, suffix, *, metrics)` — 内部 dispatch 封装

## 7. handler.py 改造

### 7.1 send_message 瘦身

新签名：

```python
async def send_message(
    pool: ClientPool, event: dict, session_id: str, content: str,
    *, metrics: MetricsCollector | None = None,
):
```

移除：`/clear` 处理、`/interrupt` 处理、`compute_session_id` 调用、slash cmd 透传判断。
保留：富消息解析、`_ensure_display_names`、`_build_prompt`、`client.query()` + `enqueue`。

slash cmd（`/` 开头）的判断仍在 send_message 中：决定是否加 `_build_prompt` 前缀。

### 7.2 session_reader 回复前缀

新增 `suffix: str | None = None` 参数。回复时：

```python
for text in reply_texts:
    if suffix:
        text = f"来自 {suffix} 的回复：\n{text}"
    reply_message(mid, text)
```

原始会话（suffix=None）不加前缀，完全向后兼容。

## 8. main.py 改造

```python
# 原来
session_id = compute_session_id(event)
await dispatcher.dispatch(session_id, send_message(...), reader_factory=...)

# 改为
await route_message(pool, event, dispatcher, defaults, metrics=metrics)
```

初始化时新增 `DefaultsStore`：

```python
defaults = DefaultsStore(ROOT / "data" / "session_defaults.json")
```

## 9. 边界情况

| 场景 | 行为 |
|------|------|
| `/new` 无参数 | 回复用法提示 |
| `/new suffix` 无 message | 回复用法提示 |
| `/new 已存在suffix msg` | 复用已有会话，发送消息 |
| `$不存在suffix msg` | 回复"会话不存在，请先 /new" |
| `/switch 不存在suffix` | 回复"会话不存在" |
| `/clear 不存在suffix` | 回复"会话不存在" |
| `/interrupt` 目标无活跃 client | 回复"当前没有活跃任务" |
| LRU 回收后再发消息 | pool.get 自动 resume |
| suffix 含 `_`、emoji | 允许，取到第一个空格为止 |

## 10. 回复格式

### /sessions

```
当前会话列表：
● 原始会话 [默认]
● cms翻译需求 (创建于 04-23 14:30)
● bug修复 (创建于 04-23 15:00)

共 3 个会话。使用 $suffix 消息 切换，/switch suffix 设为默认。
```

### /switch

```
已切换默认会话到「cms翻译需求」。后续消息将发送到此会话。
```

```
已切换回原始会话。
```

### /new 校验失败

```
用法：/new {会话名称} {消息内容}
示例：/new cms翻译 查查这个需求的状态
```

## 11. 向后兼容

- `sessions.json` 格式不变，新 session key 多了 `_{suffix}` 后缀
- 不带命令前缀的普通消息行为不变（走原始会话）
- Dashboard / Session 详情页 / 历史记录页自动兼容

## 12. 不做的事

- 不限制 suffix 数量（靠全局 LRU 回收）
- 不做会话重命名
- 不做跨用户会话共享
- 不做 per-user client 上限（统一配额）

## 13. 测试

| 测试文件 | 覆盖范围 |
|---------|---------|
| `test_router.py` | 命令解析优先级、参数校验、路由逻辑、边界情况 |
| `test_defaults_store.py` | 持久化读写、切回原始、文件初始化 |
| `test_handler.py`（更新） | 瘦身后的 send_message、session_reader 回复前缀 |
