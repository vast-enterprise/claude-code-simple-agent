# 可观测性架构

## 1. Identity

- **What it is:** Digital Avatar 的可观测性体系——异常通知、session 持久化、历史归档、运行指标收集、HTTP API + Dashboard + Session 详情页 + 历史记录页、名字解析。
- **Purpose:** 让 Avatar 从"启动后黑盒"变为可监控、可管理、可恢复的服务：崩溃/断连自动通知，重启后 session 自动恢复，运行状态可通过 HTTP API 实时查看，对话内容可通过 JSONL 日志回溯，已清除的 session 元数据归档到历史记录供后续查阅。

## 2. Core Components

- `src/notify.py` (`notify_error`): 飞书异常通知。60 秒同类防风暴（title 为节流键），仅发送成功（returncode=0）后才写入节流缓存，发送失败时检查 returncode 并通过 `log_error` 记录 stderr。
- `src/store.py` (`SessionStore`): Session 映射持久化到 `data/sessions.json`，历史归档到 `data/sessions_history.json`。原子写入（tmpfile -> fsync -> rename），损坏文件自动备份。存储 sender_name、chat_name 等显示名信息。`archive()` 将 session 复制到历史列表（不从活跃表删除），`load_history()` 加载归档记录，`_write()` 泛化支持 `dict | list`。
- `src/metrics.py` (`MetricsCollector`): 内存运行指标收集器。环形缓冲（`deque(maxlen=200)`）存最近消息摘要，跟踪 uptime、总消息数、错误率。
- `src/server.py` (`start_server`, `_create_app`, `_parse_session_log`, `_get_claude_log_dir`, `_handle_history`, `_handle_history_conversation`): aiohttp HTTP API server（`127.0.0.1:8420`），提供 REST 端点、Dashboard、Session 详情页和历史记录页。conversation API 解析 Claude JSONL 日志。compact 端点直接调用 Claude Code `/compact` slash command。历史端点通过 store 读取归档记录。
- `src/dashboard.html`: 管理后台（暗色主题，Tailwind CDN），状态卡片 + Session 表格 + 搜索过滤。Session ID 链接跳转到独立详情页，右上角「历史记录」链接跳转到历史页。
- `src/session.html`: 独立 session 详情页，展示完整对话时间线（用户消息蓝色气泡 + Claude 回复 + 工具调用折叠展示），标题栏显示人名和群名。支持 `?history=<index>` 参数进入历史查看模式（隐藏删除按钮，返回链接指向历史页），底部有「直达底部」悬浮按钮。
- `src/history.html`: 历史会话记录页（暗色主题，Tailwind CDN），展示归档 session 列表，支持搜索过滤（用户名、群名、session ID），按归档时间降序排列，点击「查看对话」跳转 session.html。
- `src/lark.py` (`resolve_user_name`, `resolve_chat_name`): 通过 lark-cli 解析 open_id 为用户名、chat_id 为群名。
- `src/handler.py` (`_ensure_display_names`): 首次遇到新 session 时调用名字解析并存入 store。
- `src/pool.py` (`ClientPool.get_claude_session_id`, `save_claude_session_id`, `remove`): SessionStore 集成，session resume 和 per-session lock 防并发。`remove()` 先调用 `store.archive()` 归档再调用 `store.remove()` 删除活跃记录，即使内存中无 client 也会执行。

## 3. Execution Flow (LLM Retrieval Map)

### 3.1 异常通知流

- **1. 崩溃通知:** `src/main.py:27-35` 注册 `sys.excepthook` 钩子 `_crash_hook`，未捕获异常触发 `notify_error("数字分身崩溃", ...)`。
- **2. 断连通知:** `src/main.py:110-111` 当 lark-cli stdout EOF 且非主动 shutdown 时，调用 `notify_error("飞书事件监听断连", ...)`。
- **3. 发送:** `src/notify.py:14-46` 检查 enabled -> 检查节流缓存（60 秒内同 title 跳过）-> 通过 `lark-cli api POST /open-apis/im/v1/messages` 发送 -> **仅 returncode=0 时**写入缓存 -> 失败时 `log_error` 记录 exit code 和 stderr。
- **4. 配置:** `src/config.py` `NOTIFY_CONFIG = CONFIG.get("notify", {"enabled": False})`。

### 3.2 Session 持久化与 Resume

- **1. 创建:** `src/main.py:95-96` 初始化 `SessionStore(ROOT / "data" / "sessions.json")` 并注入 `ClientPool`。
- **2. 写入:** `src/pool.py:60-61` `pool.get()` 创建新 client 后调用 `store.save(session_id, {})`，复用时调用 `store.update_active(session_id)`。
- **3. 名字存储:** `src/handler.py:49-72` `_ensure_display_names()` 首次遇到新 session 时调用 `resolve_user_name`/`resolve_chat_name`，将 `sender_name` 和 `chat_name` 存入 store。
- **4. Claude session_id 保存:** `src/handler.py:127-130` 首次收到 `AssistantMessage.session_id` 时调用 `pool.save_claude_session_id()`。
- **5. Resume（Pool 层）:** `src/pool.py:44-49` `pool.get()` 创建新 client 时，自动检查 store 中的 `claude_session_id`，若存在则 `dataclasses.replace(options, resume=stored_sid)` 传递 `--resume` 给 Claude 子进程。
- **6. Resume（Query 层）:** `src/handler.py:119-120` 查询 `pool.get_claude_session_id()` 获取上次 session_id 传入 `client.query()`。
- **7. 原子写入:** `src/store.py:58-73` `_write()` 使用 `tempfile.mkstemp` -> `os.fdopen` -> `f.flush()` -> `os.fsync()` -> `os.replace()`。
- **8. 损坏恢复:** `src/store.py:22-30` `load_all()` 解析失败时备份坏文件（`.json.bad.{timestamp}`）并返回空 dict。
- **9. 归档:** `src/pool.py:90-92` `remove()` 先调用 `store.archive(session_id)` 将元数据（含 claude_session_id）复制到 `data/sessions_history.json` 列表。`src/store.py:52-71` `archive()` 添加 `session_id` 和 `archived_at` 字段，同一 session 可多次归档。
- **10. 清理:** `src/pool.py:92` 归档完成后调用 `store.remove(session_id)` 从活跃表删除。即使内存中无 client（如重启后），也会执行归档+清理。
- **11. 历史加载:** `src/store.py:73-92` `load_history()` 读取 `sessions_history.json`，损坏时备份并返回空列表，非 list 类型也返回空列表。

### 3.3 指标收集

- **1. 初始化:** `src/main.py:97` `MetricsCollector()` 创建，`start_time` 记录启动时间。
- **2. 记录:** `src/handler.py:154-156` `handle_message` 的 `finally` 块调用 `metrics.record_message()`，确保异常也计入。
- **3. 查询:** `src/metrics.py` `status()` 返回 uptime、总消息数、错误数、错误率。

### 3.4 HTTP API

- **1. 启动:** `src/main.py:100` `start_server(pool, metrics, port=8420)` 返回 `AppRunner`。
- **2. 端点:**

| 端点 | 方法 | 说明 | 代码位置 |
|------|------|------|----------|
| `/` | GET | Dashboard 静态页 | `src/server.py:165-168` |
| `/session.html` | GET | Session 详情页（支持 `?history=<index>` 历史模式） | `src/server.py:248-252` |
| `/history.html` | GET | 历史记录页 | `src/server.py:255-259` |
| `/api/status` | GET | 运行指标 + 活跃 session 数 | `src/server.py:110-115` |
| `/api/sessions` | GET | 全部 session 元数据（含 sender_name/chat_name，过滤 claude_session_id） | `src/server.py:126-128` |
| `/api/sessions/history` | GET | 归档 session 列表（过滤 claude_session_id） | `src/server.py:198-208` |
| `/api/sessions/history/{index}/conversation` | GET | 指定历史记录的完整对话（通过存储的 claude_session_id 读取 JSONL） | `src/server.py:211-245` |
| `/api/sessions/{id}/messages` | GET | 指定 session 的消息历史（metrics 环形缓冲） | `src/server.py:131-135` |
| `/api/sessions/{id}/conversation` | GET | 完整对话内容（从 Claude JSONL 日志解析） | `src/server.py:174-195` |
| `/api/sessions/{id}/clear` | POST | 归档后断开并删除指定 session | `src/server.py:138-142` |
| `/api/sessions/{id}/compact` | POST | 会话压缩（直接发 `/compact` 给 Claude Code） | `src/server.py:145-162` |

- **3. Conversation API 解析:** `src/server.py:29-104` `_parse_session_log()` 纯函数解析 Claude JSONL 日志文件，提取用户文本、assistant blocks（text + tool_use）和 tool_result，跳过 thinking block，tool_result content 截断到 5000 字符。`_get_claude_log_dir()` 从 `config.ROOT` 推导 `~/.claude/projects/<encoded-path>/` 日志目录。
- **4. 历史端点:** `src/server.py:198-245` 归档列表端点从 `pool._store.load_history()` 读取并过滤内部字段；历史对话端点通过索引定位归档记录，使用存储的 `claude_session_id` 读取 JSONL 日志，返回 sender_name/chat_name/archived_at 等元数据。
- **5. 路由注册顺序:** `src/server.py:270-281` `/api/sessions/history` 必须在 `/api/sessions/{session_id}` 通配路由之前注册，否则 `history` 会被当作 session_id 匹配。
- **6. 安全:** 仅绑定 `127.0.0.1`，不对外暴露。`_sanitize_sessions()` 过滤 `claude_session_id` 等内部字段。历史端点同样过滤 `claude_session_id`。
- **7. 退出:** `src/main.py:136-137` `finally` 块中 `server_runner.cleanup()` 在清理最前执行。

### 3.5 名字解析

- **1. 用户名解析:** `src/lark.py:43-55` `resolve_user_name(open_id)` 通过 `lark-cli contact +get-user` 解析 open_id 为用户名。
- **2. 群名解析:** `src/lark.py:58-70` `resolve_chat_name(chat_id)` 通过 `lark-cli im chats get` 解析 chat_id 为群名。
- **3. 触发时机:** `src/handler.py:49-72` `_ensure_display_names()` 在 `handle_message` 中首次遇到新 session 时调用（检查 store 中是否已有 `sender_name`），解析结果通过 `pool._store.save()` 持久化。
- **4. 消费端:** Dashboard session 列表和 session 详情页从 `/api/sessions` 读取 `sender_name`/`chat_name` 展示（如"郭凯南 @ 测试 bot"）。

## 4. Design Rationale

- **节流仅在成功后写入:** `src/notify.py:41-44` 避免发送失败但被节流导致后续真正异常被静默。失败时记录 exit code 和 stderr 便于排查。
- **原子写入:** 防止进程在写 JSON 中途崩溃导致 `sessions.json` 半损坏，`os.replace` 是 POSIX 原子操作。
- **环形缓冲:** `deque(maxlen=200)` 自动淘汰旧消息，内存占用恒定，无需 GC。
- **HTTP server 仅 localhost:** 管理端点不设鉴权，通过网络层限制（仅 `127.0.0.1`）保证安全。
- **Conversation API 基于 JSONL 日志:** 直接解析 Claude 的 JSONL 日志文件而非在内存中维护对话历史，实现零额外存储开销，且天然支持重启后历史回溯。
- **名字解析惰性执行:** 仅首次遇到 session 时调用 lark-cli 解析，结果持久化到 store，避免每条消息都触发 API 调用。
- **compact 直接透传 Claude Code:** compact 端点直接向 Claude SDK 发送 `/compact` slash command，不再需要 handler 层的指令拦截。
- **remove() 先归档再删除:** `pool.remove()` 在删除活跃记录前先调用 `store.archive()`，确保 session 元数据（尤其是 claude_session_id）不会丢失，归档后仍可通过历史页查看对话内容。即使内存中无 client（如重启后），也会执行归档+清理。
- **历史文件为列表结构:** `sessions_history.json` 使用列表而非以 session_id 为 key 的 dict，允许同一 session 多次归档（如同一会话被反复 clear/resume），通过列表索引访问。
- **历史端口基于索引:** 历史对话端点使用列表索引（`/api/sessions/history/{index}/conversation`）而非 session_id，因为列表结构中同一 session_id 可能有多条记录。
