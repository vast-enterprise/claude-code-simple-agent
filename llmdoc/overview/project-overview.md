# Tripo Work Center + Tripo Avatar

## 1. Identity

- **What it is:** 业务调度中枢（tripo-work-center）+ 基于 Claude Code SDK 的飞书数字分身（tripo-avatar）。
- **Purpose:** 集中管理 Tripo 各代码仓库的需求开发、发版、Bug 修复等工作流调度；同时通过飞书机器人提供 AI 数字分身，自动响应飞书消息并执行技术任务。

## 2. High-Level Description

`tripo-work-center` 是一个纯调度中枢，本身不含业务代码。它通过 CLAUDE.md 和 `.claude/skills/` 定义了一套 skill 体系（需求流程、发版、多维表格操作等），驱动 Agent 在多个外部代码仓库（tripo-cms、fe-tripo-homepage 等）中执行工作。

核心产物 `tripo-avatar` 是一个 Python 异步服务，通过 `lark-cli` 订阅飞书消息事件，经过滤后交由 Claude Code SDK 处理，实现"数字分身"自动回复。架构为多进程池模型——`ClientPool` 为每个 session 惰性创建独立 `ClaudeSDKClient`（独立 Claude 子进程），不同 session 并行，同一 session 内消息串行。所有飞书交互通过 `lark-cli` subprocess 完成。

系统内置可观测性体系：`SessionStore` 将 session 映射持久化到磁盘（原子写入），支持重启后 session resume（Pool 层通过 `--resume` 参数恢复 Claude 子进程上下文）；被清除的 session 自动归档到 `sessions_history.json`，保留元数据和 claude_session_id 以便后续通过历史记录页回溯完整对话内容；`MetricsCollector` 在内存中跟踪运行时指标和最近 200 条消息摘要；`aiohttp` HTTP API（端口 8420）暴露状态、session 管理端点、Dashboard、独立 Session 详情页（通过解析 Claude JSONL 日志展示完整对话时间线）和历史记录页（展示归档 session 列表，支持搜索和对话回溯）；`notify` 模块在进程崩溃或断连时推送飞书异常通知（60 秒同类防风暴）。飞书端仅保留 `/clear` 指令由 handler 自行处理，其他 slash commands（`/compact`、`/model` 等）直接透传给 Claude Code。

## 3. 技术栈

| 层面 | 技术 |
|------|------|
| 语言 | Python >= 3.12 |
| AI 引擎 | `claude-agent-sdk >= 0.1.56` |
| HTTP Server | `aiohttp >= 3.9`（Dashboard API） |
| 飞书交互 | `lark-cli`（CLI 工具，subprocess 调用，非 SDK） |
| 测试 | pytest，测试路径 `src/__tests__/` |
| 配置 | `config.json`（运行时，gitignore）+ `persona.md`（人格注入） |

## 4. 项目结构

```
tripo-work-center/
├── src/
│   ├── main.py          # 入口：事件循环、进程管理、信号处理、崩溃通知、HTTP server 启动
│   ├── pool.py          # ClientPool：per-session 独立 client 池 + SessionStore 集成 + session resume
│   ├── handler.py       # 消息过滤 + /clear 处理 + slash command 透传 + 名字解析 + metrics 集成
│   ├── session.py       # 并发调度器（SessionDispatcher）：per-session 队列 + worker
│   ├── permissions.py   # 工具调用权限门控（permission_gate），contextvars 隔离
│   ├── lark.py          # 飞书交互封装（reaction、reply、用户名/群名解析）
│   ├── config.py        # 配置加载 + 结构化日志 + NOTIFY_CONFIG
│   ├── notify.py        # 飞书异常通知，60 秒同类防风暴
│   ├── store.py         # Session 映射持久化（data/sessions.json）+ 历史归档（data/sessions_history.json），原子写入
│   ├── metrics.py       # 内存指标收集器，环形缓冲存最近 200 条消息摘要
│   ├── server.py        # aiohttp HTTP API server（端口 8420），Dashboard + Session 详情页 + 历史记录页 + REST 端点 + Conversation API
│   ├── dashboard.html   # 管理后台（暗色主题，Tailwind CDN，搜索过滤，session 链接到详情页，历史记录链接）
│   ├── session.html     # Session 详情页（对话时间线，工具调用折叠展示，支持历史模式）
│   ├── history.html     # 历史会话记录页（归档 session 列表，搜索过滤，对话回溯）
│   └── __tests__/       # 单元测试
├── persona.md           # 数字分身人格定义，注入 system_prompt
├── config.example.json  # 配置模板（owner_id、模型参数、API 环境变量）
├── CLAUDE.md            # Agent 行为约束 + Skills 目录
└── pyproject.toml       # 项目元数据，项目名 tripo-avatar
```

## 5. 核心依赖关系

```
main.py ──→ config.py（CONFIG, PERSONA, ROOT, HEADLESS_RULES, DISALLOWED_TOOLS）
   │──→ pool.py（ClientPool）
   │──→ handler.py（should_respond, handle_message, compute_session_id）
   │──→ permissions.py（permission_gate）
   │──→ session.py（SessionDispatcher）
   │──→ notify.py（notify_error — 崩溃通知 + 断连通知）
   │──→ metrics.py（MetricsCollector）
   │──→ store.py（SessionStore）
   │──→ server.py（start_server — HTTP API + Dashboard）
   │
pool.py ──→ config.py（log_debug, log_error）
   │──→ store.py（SessionStore — 持久化 session 映射 + Claude session_id）
   │──→ claude_agent_sdk（ClaudeSDKClient, ClaudeAgentOptions）
   │
handler.py ──→ config.py（OWNER_ID, BOT_NAME, log_debug）
   │──→ pool.py（ClientPool）
   │──→ lark.py（add_reaction, remove_reaction, reply_message, resolve_user_name, resolve_chat_name）
   │──→ permissions（set_sender）
   │──→ metrics.py（MetricsCollector — record_message）
   │
server.py ──→ config.py（log_info）
   │──→ aiohttp（web.Application, AppRunner, TCPSite）
   │
notify.py ──→ config.py（NOTIFY_CONFIG, log_error）
store.py ──→ config.py（log_error）
metrics.py ──→ 无内部依赖（纯数据收集器）
session.py ──→ config.py（log_error）
permissions.py ──→ config.py（OWNER_ID）+ contextvars
lark.py ──→ config.py（log_error）
config.py ──→ 无内部依赖（叶节点）
```

## 6. 数据流概要

`lark-cli stdout (NDJSON)` → `main.py` 逐行读取解析（`_read_or_shutdown` 多路复用）→ `should_respond` 过滤 → `compute_session_id` 计算会话标识 → `SessionDispatcher.dispatch` 分发到 per-session 队列 → `handle_message(pool, event, metrics=metrics)` 处理（`/clear` 自行处理，`/` 开头 slash commands 原样透传给 Claude Code，普通消息加发送者上下文前缀）→ `_ensure_display_names` 首次解析并存储 sender_name/chat_name → `ClientPool.get` 获取独立 client（惰性创建时自动 `--resume` 恢复 session）→ 组装 prompt 并调用 Claude SDK → `permission_gate` 拦截敏感工具调用 → `lark.reply_message` 回复飞书 → `MetricsCollector.record_message` 记录指标（try/finally 确保异常也计入）。

并行运行：`aiohttp` HTTP server（端口 8420）提供 REST 端点、Dashboard UI、Session 详情页和 Conversation API（解析 Claude JSONL 日志）；`notify` 在崩溃/断连时推送飞书通知。
