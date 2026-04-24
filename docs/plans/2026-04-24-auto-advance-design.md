# 需求自动推进机制设计文档

> 创建日期：2026-04-24

## 1. Context

### 1.1 问题背景

Tripo 调度中枢目前是被动响应用户请求的系统。用户需要主动在飞书群里触发消息，调度中枢才会推进需求或 Bug 的流程。当需求/Bug 在某个流程步骤停滞时（如待评审、待技评、待上线），系统不会主动提醒用户，导致流程推进依赖用户主动跟进。

### 1.2 目标

实现「定时审计 + 主动推进」机制：
- 每小时轮询审计所有者的需求/Bug
- 发现停滞时，主动拉起调度会话，汇报停滞情况
- 用户确认后，自动创建/激活需求 session 推进流程

### 1.3 边界约束

| 维度 | 选择 |
|------|------|
| 推进边界 | 审计 → 发通知（停在通知）——只提醒不行动，等用户回复再走流程 |
| 停滞定义 | 流程断点（任意停滞）——检查流程图的下一步该做了但没做 |
| 触发频率 | 每小时 1 次 |
| 覆盖范围 | 产品需求池 + 缺陷表 + 技术需求池 |

---

## 2. 核心概念

### 2.1 调度会话（Dispatch Session）

- **用途**：审计 + 汇报 + 等用户确认
- **命名**：suffix = `_dispatch`（保留名称，禁止用户创建）
- **session_id**：`p2p_{OWNER_ID}_dispatch`
- **触发**：每小时轮询触发，检查所有者的需求/Bug 停滞情况
- **不推进流程**：只做"发现 + 计划 + 等确认"，实际推进由需求 session 完成

### 2.2 需求 Session

- **用途**：实际推进流程（派 planner/architect/developer 等）
- **命名**：由调度会话 agent 决定 suffix
- **session_id**：`p2p_{OWNER_ID}_{suffix}`
- **创建**：由调度会话 agent 通过 HTTP API 创建/激活

### 2.3 Session 状态定义

| 状态 | 含义 | 判断条件 |
|------|------|---------|
| CREATED | session 在 store 存在，但无 SDK client | `session_id in store` but `not in _clients` |
| READY | 有 SDK client，空闲 | `in _clients` and `not _processing` |
| PROCESSING | 正在执行（SDK 处理 message） | `in _clients` and `_processing=True` |

---

## 3. HTTP API 设计

### 3.1 GET /sessions/{owner_id}

返回用户所有 session 的状态列表，供调度会话 agent 查询。

**响应格式**：
```json
{
  "sessions": [
    {
      "session_id": "p2p_ou_xxx_REQ-12345",
      "status": "READY",
      "task_id": "REQ-12345",
      "task_type": "requirement",
      "last_active": "2026-04-24T10:00:00Z",
      "pending_count": 0
    },
    {
      "session_id": "p2p_ou_xxx_dispatch",
      "status": "PROCESSING",
      "task_id": null,
      "task_type": null,
      "last_active": "2026-04-24T10:30:00Z",
      "pending_count": 1
    }
  ]
}
```

### 3.2 POST /sessions/{owner_id}/create

内部接口：创建或激活 session 并发送消息，供调度会话 agent 创建需求 session。

**请求格式**：
```json
{
  "suffix": "REQ-12345",
  "message": "继续推进需求 REQ-12345",
  "task_id": "REQ-12345",
  "task_type": "requirement"
}
```

**响应格式**：
```json
{
  "session_id": "p2p_{owner_id}_REQ-12345",
  "status": "PROCESSING",
  "created": true
}
```

**错误响应**：
- 400：保留名称 `_dispatch`
- 409：session 正在 PROCESSING

### 3.3 POST /sessions/{session_id}/message

内部接口：向已有 session 发送消息，供调度会话 agent 激活已存在的 session。

**请求格式**：
```json
{
  "message": "继续推进需求 REQ-12345"
}
```

**响应格式**：
```json
{
  "status": "PROCESSING",
  "queued": true
}
```

**错误响应**：
- 404：session 不存在
- 409：session 正在 PROCESSING

---

## 4. Session → 需求映射

### 4.1 SessionStore metadata 扩展

在 `data/sessions.json` 中增加字段：

```json
{
  "p2p_ou_xxx_REQ-12345": {
    "created_at": "2026-04-24T10:00:00Z",
    "last_active": "2026-04-24T10:30:00Z",
    "message_count": 5,
    "sender_name": "郭凯南",
    "claude_session_id": "session_xxx",
    "task_id": "REQ-12345",
    "task_type": "requirement"
  }
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `task_id` | string | 需求/Bug 的 record_id 或 task-dir |
| `task_type` | string | `requirement` / `bug` / `tech-requirement` |

### 4.2 调度会话 agent 查询流程

1. `curl GET /sessions/{OWNER_ID}` → 获取用户所有 session
2. 对每个 session，检查 metadata.task_id → 知道对应哪个需求
3. 对每个需求，反向查找：遍历 sessions，找到 task_id 匹配的 session_id
4. 制定计划：CREATED/READY → 可以推进；PROCESSING → 跳过

---

## 5. 调度会话 Agent 流程

### 5.1 提示词引导

调度会话 agent 是 Claude SDK 进程，通过提示词引导其行为：

```
你是调度会话 Agent。请执行以下步骤：

1. 查询飞书表格：
   - 产品需求池 + 技术需求池 + 缺陷表
   - 过滤 owner = {OWNER_ID}

2. 查询 session 状态（用 Bash curl）：
   curl -s http://localhost:8420/sessions/{OWNER_ID}

3. 制定计划：
   - 对每个需求：检查对应 session 状态
   - CREATED/READY → 可以推进
   - PROCESSING → 跳过（在汇报中明确标注）

4. 汇报给用户：
   列出所有需求及其状态、计划操作，等待用户回复「继续」或「取消」

5. 用户回复「继续」后：
   - 再次 curl 查询状态（确认当前状态，因为用户回复可能有延迟）
   - 状态变化 → 更新计划
   - 状态未变 → 执行计划：
     - CREATED → curl POST /sessions/{OWNER_ID}/create
     - READY → curl POST /sessions/{session_id}/message
     - PROCESSING → 跳过并告知用户
```

### 5.2 OWNER_ID 来源

OWNER_ID 在系统配置 `config.json` 中定义：
```json
{
  "owner_open_id": "ou_xxx"
}
```

调度会话 agent 的提示词直接告知 OWNER_ID 值，agent 用它拼接 HTTP API URL 和 session_id。

---

## 6. 状态转换时机

### 6.1 转换规则

| 事件 | 状态转换 | 代码位置 |
|------|---------|----------|
| `pool.get()` 创建 client | CREATED → READY | pool.py |
| `send_message()` query 后 | READY → PROCESSING | handler.py |
| `session_reader` ResultMessage 后 | PROCESSING → READY | handler.py |
| `session_reader` 异常退出 | PROCESSING → READY | handler.py |
| `/interrupt` 成功 | PROCESSING → READY | router.py |
| `pool.remove()` 清理 | READY/PROCESSING → CREATED | pool.py |
| LRU eviction | READY → CREATED | pool.py |

### 6.2 边界处理

1. **interrupt 中断后状态重置**：
   - `/interrupt` 发送控制指令后，立即设置 `is_processing=False`
   - SDK 被中断后，session_reader 可能收到 ResultMessage(is_error=True)，再次设置 READY

2. **session_reader 异常退出**：
   - 异常时清理 reaction + dequeue + 设置 `is_processing=False`
   - 防止 session 永久卡在 PROCESSING 状态

3. **进程重启后状态归零**：
   - `is_processing` 是内存状态，重启后自然清空
   - 所有 session 状态变为 CREATED（store 中有记录，但 _clients 为空）

4. **LRU 不清理 PROCESSING 状态**：
   - `_select_lru_session()` 只选择 `is_processing=False` 的 session
   - 正在执行的任务不会被强制 eviction

---

## 7. 轮询进程集成

### 7.1 config.json 配置

```json
{
  "owner_open_id": "ou_xxx",
  "bot_name": "AI Bot",
  "max_active_clients": 5,
  "scheduler": {
    "enabled": true,
    "interval_seconds": 3600
  }
}
```

### 7.2 启动流程

在 `main.py` 启动时创建轮询任务：

```python
async def start_scheduler(pool, dispatcher, config):
    """启动调度轮询"""
    scheduler_config = config.get("scheduler", {})
    if not scheduler_config.get("enabled", False):
        return
    
    interval = scheduler_config.get("interval_seconds", 3600)
    
    async def scheduler_loop():
        while True:
            await asyncio.sleep(interval)
            await trigger_dispatch_session(pool, dispatcher)
    
    asyncio.create_task(scheduler_loop())

async def trigger_dispatch_session(pool, dispatcher):
    """触发调度会话"""
    dispatch_session_id = f"p2p_{OWNER_ID}_dispatch"
    
    # 检查调度会话状态
    status = pool.get_status(dispatch_session_id)
    if status == "PROCESSING":
        log_debug("[Scheduler] 调度会话正在执行，本轮跳过")
        return
    
    # 构造虚拟 event（模拟所有者发送消息）
    event = {
        "chat_type": "p2p",
        "sender_id": OWNER_ID,
        "message_id": f"scheduler-{uuid4()}",
        "content": "请检查我的所有需求，制定推进计划。",
        "chat_id": OWNER_ID,
    }
    
    # dispatch 到调度会话
    await dispatcher.dispatch(...)
```

### 7.3 启动顺序

1. 注册崩溃通知钩子
2. 启动 lark-cli 子进程
3. 初始化 SessionStore + DefaultsStore
4. 构造 SessionDispatcher + ClientPool
5. 启动 HTTP server
6. **启动调度轮询任务** ← 新增步骤
7. 注册信号处理

---

## 8. 保留名称拦截

### 8.1 拦截位置

在 `router.py` 中拦截 `_dispatch`：

```python
RESERVED_SUFFIXES = ["_dispatch"]

def is_reserved_suffix(suffix: str) -> bool:
    return suffix in RESERVED_SUFFIXES
```

### 8.2 拦截时机

- `/new _dispatch 消息` → 返回错误提示
- `$dispatch 消息` → 返回错误提示
- HTTP API POST /sessions/{owner_id}/create → 返回 400 error

---

## 9. 测试计划

### 9.1 单元测试

1. **SessionStatus 状态判断**：
   - CREATED → session 在 store 但不在 _clients
   - READY → session 在 _clients 且 is_processing=False
   - PROCESSING → session 在 _clients 且 is_processing=True

2. **状态转换**：
   - pool.get() 后 CREATED → READY
   - send_message 后 READY → PROCESSING
   - ResultMessage 后 PROCESSING → READY
   - pool.remove() 后任意状态 → CREATED

3. **保留名称拦截**：
   - `/new _dispatch` → 返回错误提示
   - `$dispatch 消息` → 返回错误提示

4. **LRU 不清理 PROCESSING**：
   - 设置 is_processing=True 的 session 不被 eviction

### 9.2 HTTP API 测试

1. **GET /sessions/{owner_id}**：
   - 返回正确格式
   - 状态字段正确
   - task_id 字段正确

2. **POST /sessions/{owner_id}/create**：
   - 创建成功 → 返回 session_id + status=PROCESSING
   - 保留名称 → 返回 400 error
   - task_id 存入 store

3. **POST /sessions/{session_id}/message**：
   - 发送成功 → 返回 status=PROCESSING
   - session 不存在 → 返回 404
   - session 正在 PROCESSING → 返回 409

### 9.3 集成测试

1. 调度会话审计流程：
   - 配置 scheduler.enabled=true
   - 等待轮询触发
   - 调度会话回复列出需求 + 状态 + 计划
   - 用户回复「继续」后执行计划

2. 需求 session 推进：
   - 调度会话创建需求 session
   - 需求 session agent 接收消息后推进流程

---

## 10. 修改文件清单

| 文件 | 修改内容 |
|------|---------|
| `src/pool.py` | 增加 `_processing` 字典 + `get_status()` + `set_processing()` + 修改 `_select_lru_session()` |
| `src/handler.py` | send_message 设置 PROCESSING；session_reader ResultMessage 设置 READY；异常处理设置 READY |
| `src/router.py` | 增加 `RESERVED_SUFFIXES` + `is_reserved_suffix()` + 拦截 `_dispatch` |
| `src/server.py` | 增加 `GET /sessions/{owner_id}` + `POST /sessions/{owner_id}/create` + `POST /sessions/{session_id}/message` |
| `src/main.py` | 增加 `start_scheduler()` + `trigger_dispatch_session()` |
| `src/store.py` | metadata 增加 task_id/task_type 字段（可选，直接在 save 时传入即可） |
| `config.json` | 增加 `scheduler.enabled` + `scheduler.interval_seconds` |