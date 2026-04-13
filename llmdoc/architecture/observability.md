# 可观测性架构

## 1. Identity

- **What it is:** Digital Avatar 的可观测性体系——异常通知、session 持久化、运行指标收集、HTTP API + Dashboard、飞书指令管理。
- **Purpose:** 让 Avatar 从"启动后黑盒"变为可监控、可管理、可恢复的服务：崩溃/断连自动通知，重启后 session 自动恢复，运行状态可通过 HTTP API 和飞书指令实时查看。

## 2. Core Components

- `src/notify.py` (`notify_error`): 飞书异常通知。60 秒同类防风暴（title 为节流键），仅发送成功后才写入节流缓存。
- `src/store.py` (`SessionStore`): Session 映射持久化到 `data/sessions.json`。原子写入（tmpfile -> fsync -> rename），损坏文件自动备份。
- `src/metrics.py` (`MetricsCollector`): 内存运行指标收集器。环形缓冲（`deque(maxlen=200)`）存最近消息摘要，跟踪 uptime、总消息数、错误率。
- `src/server.py` (`start_server`, `_create_app`): aiohttp HTTP API server（`127.0.0.1:8420`），提供 REST 端点和 Dashboard 静态页面。
- `src/dashboard.html`: 单文件管理后台（暗色主题，Tailwind CDN），状态卡片 + Session 表格 + 消息时间线，30 秒轮询。
- `src/handler.py` (`parse_command`, `handle_command`): 飞书指令解析层，支持 `/clear`、`/compact`、`/sessions`、`/status` 四个指令。
- `src/pool.py` (`ClientPool.get_claude_session_id`, `save_claude_session_id`, `remove`): SessionStore 集成，session resume 和 per-session lock 防并发。

## 3. Execution Flow (LLM Retrieval Map)

### 3.1 异常通知流

- **1. 崩溃通知:** `src/main.py:27-35` 注册 `sys.excepthook` 钩子 `_crash_hook`，未捕获异常触发 `notify_error("数字分身崩溃", ...)`.
- **2. 断连通知:** `src/main.py:110-111` 当 lark-cli stdout EOF 且非主动 shutdown 时，调用 `notify_error("飞书事件监听断连", ...)`.
- **3. 发送:** `src/notify.py:14-46` 检查 enabled -> 检查节流缓存（60 秒内同 title 跳过）-> 通过 `lark-cli api POST /open-apis/im/v1/messages` 发送 -> 成功后写入缓存。
- **4. 配置:** `src/config.py:57` `NOTIFY_CONFIG = CONFIG.get("notify", {"enabled": False})`。

### 3.2 Session 持久化与 Resume

- **1. 创建:** `src/main.py:95-96` 初始化 `SessionStore(ROOT / "data" / "sessions.json")` 并注入 `ClientPool`.
- **2. 写入:** `src/pool.py:52-53` `pool.get()` 创建新 client 后调用 `store.save(session_id, {})`，复用时调用 `store.update_active(session_id)`.
- **3. Claude session_id 保存:** `src/handler.py:150-152` 首次收到 `AssistantMessage.session_id` 时调用 `pool.save_claude_session_id()`.
- **4. Resume:** `src/handler.py:142-143` 查询 `pool.get_claude_session_id(session_id)` 获取上次 Claude session_id，传入 `client.query(prompt, session_id=claude_sid)`.
- **5. 原子写入:** `src/store.py:58-73` `_write()` 使用 `tempfile.mkstemp` -> `os.fdopen` -> `f.flush()` -> `os.fsync()` -> `os.replace()`.
- **6. 损坏恢复:** `src/store.py:22-30` `load_all()` 解析失败时备份坏文件（`.json.bad.{timestamp}`）并返回空 dict.

### 3.3 指标收集

- **1. 初始化:** `src/main.py:97` `MetricsCollector()` 创建，`start_time` 记录启动时间。
- **2. 记录:** `src/handler.py:177-179` `handle_message` 的 `finally` 块调用 `metrics.record_message()`，确保异常也计入。
- **3. 查询:** `src/metrics.py:28-39` `status()` 返回 uptime、总消息数、错误数、错误率。

### 3.4 HTTP API

- **1. 启动:** `src/main.py:100` `start_server(pool, metrics, port=8420)` 返回 `AppRunner`.
- **2. 端点:**

| 端点 | 方法 | 说明 | 代码位置 |
|------|------|------|----------|
| `/` | GET | Dashboard 静态页 | `src/server.py:57-60` |
| `/api/status` | GET | 运行指标 + 活跃 session 数 | `src/server.py:16-21` |
| `/api/sessions` | GET | 全部 session 元数据（过滤 claude_session_id） | `src/server.py:32-34` |
| `/api/sessions/{id}/messages` | GET | 指定 session 的消息历史 | `src/server.py:37-41` |
| `/api/sessions/{id}/clear` | POST | 断开并删除指定 session | `src/server.py:44-48` |
| `/api/sessions/{id}/compact` | POST | 会话压缩（TODO） | `src/server.py:51-54` |

- **3. 安全:** 仅绑定 `127.0.0.1`，不对外暴露。`_sanitize_sessions()` 过滤 `claude_session_id` 等内部字段。
- **4. 退出:** `src/main.py:136-137` `finally` 块中 `server_runner.cleanup()` 在清理最前执行。

### 3.5 飞书指令

- **1. 解析:** `src/handler.py:50-57` `parse_command()` 检测 `/` 开头，匹配 `_COMMANDS` 集合。
- **2. 路由:** `src/handler.py:124-127` `handle_message` 中指令优先于 Claude 处理。
- **3. 指令:**

| 指令 | 权限 | 说明 |
|------|------|------|
| `/clear` | 所有人 | 清除当前 session，下次新建 |
| `/compact` | 所有人 | 会话压缩（TODO） |
| `/sessions` | 仅 owner | 列出所有 session 概览 |
| `/status` | 仅 owner | 查看运行指标 |

## 4. Design Rationale

- **节流仅在成功后写入:** `src/notify.py:41-42` 避免发送失败但被节流导致后续真正异常被静默。
- **原子写入:** 防止进程在写 JSON 中途崩溃导致 `sessions.json` 半损坏，`os.replace` 是 POSIX 原子操作。
- **环形缓冲:** `deque(maxlen=200)` 自动淘汰旧消息，内存占用恒定，无需 GC。
- **HTTP server 仅 localhost:** 管理端点不设鉴权，通过网络层限制（仅 `127.0.0.1`）保证安全。
- **指令不经过 Claude:** `/clear` 等管理指令直接处理，节省 API 调用开销和延迟。
