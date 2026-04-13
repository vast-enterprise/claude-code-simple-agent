# Avatar 可观测性设计

> 日期：2026-04-13
> 状态：待实施

## 1. 需求

| 需求 | 要点 |
|------|------|
| 异常通知 | 崩溃/断连/处理失败 → 飞书通知（接收者可配置） |
| Session 持久化 | 重启后恢复 session 映射，Claude SDK resume 恢复上下文 |
| 飞书指令 | `/clear`、`/compact`、`/sessions`、`/status` |
| 管理后台 | Session 列表+操作、消息时间线、系统状态总览 |

## 2. 架构

```
avatar 进程
├── 事件循环（已有）
├── HTTP Server（新增，:8420）
│   ├── GET  /api/status               → 系统总览
│   ├── GET  /api/sessions             → session 列表
│   ├── GET  /api/sessions/:id         → session 详情 + 消息时间线
│   ├── POST /api/sessions/:id/clear   → 清除 session
│   ├── POST /api/sessions/:id/compact → 压缩 session
│   └── GET  /                         → 管理后台 HTML
├── Notifier（新增）
│   └── lark-cli im +messages-send --as bot
├── SessionStore（新增）
│   └── data/sessions.json
└── MetricsCollector（新增）
    └── 内存计数器 + 消息摘要环形缓冲
```

## 3. 异常通知 — `src/notify.py`

```python
def notify_error(title: str, detail: str) -> None:
    """异常事件推飞书，60 秒同类防风暴"""
```

通知场景（仅异常，不通知启动/正常退出）：
- 未捕获异常退出（sys.excepthook）
- lark-cli 断连（listener 子进程退出）
- Claude SDK 连接/查询失败（pool.get / client.query 异常）
- 消息处理失败（ResultMessage.is_error）

config.json 新增：
```json
{
  "notify": {
    "enabled": true,
    "receive_id": "ou_xxx",
    "receive_id_type": "open_id"
  }
}
```

`receive_id` 支持 open_id（个人）或 chat_id（群），通过 `receive_id_type` 区分。

## 4. Session 持久化 — `src/store.py`

```python
class SessionStore:
    def save(session_id: str, metadata: dict)  # 保存/更新
    def load() -> dict                          # 启动时加载全部
    def remove(session_id: str)                 # 删除
    def update_active(session_id: str)          # 更新最后活跃时间
```

持久化文件 `data/sessions.json`（gitignore）：
```json
{
  "p2p_ou_xxx": {
    "created_at": "2026-04-13T10:00:00Z",
    "last_active": "2026-04-13T15:30:00Z",
    "message_count": 42
  }
}
```

启动时 ClientPool 从 store 加载已有 session，用 Claude SDK resume 恢复上下文。

### clear 行为

```
/clear p2p_ou_xxx
  → SessionStore.remove(session_id)
  → ClientPool 断开该 client
  → 下次该用户发消息 → 新建 client + 新 session（从零开始）
```

### compact 行为

```
/compact p2p_ou_xxx
  → 通过 Claude SDK 触发 session 压缩
  → session 保留，历史被摘要化，释放 token
```

## 5. 飞书指令 — handler.py 扩展

在消息处理前加指令解析层，`/` 开头的消息进入指令分支：

| 指令 | 行为 | 权限 |
|------|------|------|
| `/clear` | 清除当前用户自己的 session | 所有人 |
| `/compact` | 压缩当前用户自己的 session | 所有人 |
| `/sessions` | 返回 session 列表摘要 | owner |
| `/status` | 返回系统运行状态 | owner |

飞书指令只操作当前用户自己的 session。跨 session 操作（清除/压缩其他用户的 session）仅通过管理后台 HTTP API 执行。

## 6. 指标收集 — `src/metrics.py`

内存中维护（不持久化，重启清零）：

```python
class MetricsCollector:
    start_time: datetime          # 启动时间
    total_messages: int           # 总消息数
    total_errors: int             # 总错误数
    message_log: deque[dict]      # 环形缓冲，最近 200 条消息摘要
```

消息摘要结构：
```python
{
    "session_id": "p2p_ou_xxx",
    "timestamp": "2026-04-13T15:30:00Z",
    "content_preview": "帮我查一下 cms...",  # 前 50 字
    "success": True,
    "reply_preview": "查询结果..."           # 前 50 字
}
```

## 7. HTTP 管理后台 — `src/server.py` + `src/dashboard.html`

### 后端

Python asyncio 原生 HTTP server（`aiohttp` 或 `http.server`），嵌入 avatar 主进程，端口 8420。

API 端点：
- `GET /api/status` → `{"uptime": "2h30m", "total_messages": 156, "total_errors": 3, "active_sessions": 5}`
- `GET /api/sessions` → session 列表 + 元数据
- `GET /api/sessions/:id` → 消息时间线
- `POST /api/sessions/:id/clear` → 清除 session
- `POST /api/sessions/:id/compact` → 压缩 session

### 前端

单文件 `src/dashboard.html`，纯 HTML + vanilla JS + Tailwind CDN，零构建。

布局：
- 顶部：系统状态卡片（uptime、消息数、错误数、活跃 session 数）
- 中间：Session 列表表格（ID、最后活跃、消息数、clear/compact 按钮）
- 底部/侧边：点击 session 展开消息时间线

自动 30 秒轮询刷新。

## 8. 文件结构变更

```
src/
├── main.py        # 改：集成 HTTP server、通知、store 初始化
├── config.py      # 改：新增 notify 配置解析
├── handler.py     # 改：飞书指令解析层
├── pool.py        # 改：集成 SessionStore、resume 逻辑
├── session.py     # 不变
├── permissions.py # 不变
├── lark.py        # 不变
├── notify.py      # 新增：飞书异常通知
├── store.py       # 新增：session 持久化
├── metrics.py     # 新增：指标收集
├── server.py      # 新增：HTTP API
└── dashboard.html # 新增：管理后台前端
data/
└── sessions.json  # 新增：session 持久化（gitignore）
```

## 9. 实施顺序

1. **notify.py** — 异常通知（最小独立模块，可立即验证）
2. **store.py + pool.py 改造** — session 持久化 + resume
3. **handler.py 指令层** — 飞书指令
4. **metrics.py** — 指标收集
5. **server.py + dashboard.html** — HTTP API + 管理后台

每步独立可测试，逐步集成。
