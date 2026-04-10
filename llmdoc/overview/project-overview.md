# Tripo Work Center + Tripo Avatar

## 1. Identity

- **What it is:** 业务调度中枢（tripo-work-center）+ 基于 Claude Code SDK 的飞书数字分身（tripo-avatar）。
- **Purpose:** 集中管理 Tripo 各代码仓库的需求开发、发版、Bug 修复等工作流调度；同时通过飞书机器人提供 AI 数字分身，自动响应飞书消息并执行技术任务。

## 2. High-Level Description

`tripo-work-center` 是一个纯调度中枢，本身不含业务代码。它通过 CLAUDE.md 和 `.claude/skills/` 定义了一套 skill 体系（需求流程、发版、多维表格操作等），驱动 Agent 在多个外部代码仓库（tripo-cms、fe-tripo-homepage 等）中执行工作。

核心产物 `tripo-avatar` 是一个 Python 异步服务，通过 `lark-cli` 订阅飞书消息事件，经过滤后交由 Claude Code SDK 处理，实现"数字分身"自动回复。架构为多进程池模型——`ClientPool` 为每个 session 惰性创建独立 `ClaudeSDKClient`（独立 Claude 子进程），不同 session 并行，同一 session 内消息串行。所有飞书交互通过 `lark-cli` subprocess 完成。

## 3. 技术栈

| 层面 | 技术 |
|------|------|
| 语言 | Python >= 3.12 |
| AI 引擎 | `claude-agent-sdk >= 0.1.56`（唯一运行时依赖） |
| 飞书交互 | `lark-cli`（CLI 工具，subprocess 调用，非 SDK） |
| 测试 | pytest，测试路径 `src/__tests__/` |
| 配置 | `config.json`（运行时，gitignore）+ `persona.md`（人格注入） |

## 4. 项目结构

```
tripo-work-center/
├── src/
│   ├── main.py          # 入口：事件循环、进程管理、asyncio-native 信号处理、ClientPool + SessionDispatcher 集成
│   ├── pool.py          # ClientPool：per-session 独立 ClaudeSDKClient 池，惰性创建 + Lock 防并发
│   ├── handler.py       # 消息过滤（should_respond）+ 处理（handle_message, 从 pool 获取 client）+ session 计算
│   ├── session.py       # 并发调度器（SessionDispatcher）：per-session 队列 + worker
│   ├── permissions.py   # 工具调用权限门控（permission_gate），contextvars 隔离
│   ├── lark.py          # 飞书交互封装（reaction、reply）
│   ├── config.py        # 配置加载（config.json + persona.md + HEADLESS_RULES）+ 结构化日志（avatar logger）
│   └── __tests__/       # 单元测试（handler、permissions、lark、pool、session）
├── persona.md           # 数字分身人格定义，注入 system_prompt
├── config.example.json  # 配置模板（owner_id、模型参数、API 环境变量）
├── CLAUDE.md            # Agent 行为约束 + Skills 目录
└── pyproject.toml       # 项目元数据，项目名 tripo-avatar
```

## 5. 核心依赖关系

```
main.py ──→ config.py（CONFIG, PERSONA, ROOT, log_debug, log_info）
   │──→ pool.py（ClientPool → per-session 独立 client 池）
   │──→ handler.py（should_respond, handle_message, compute_session_id）
   │──→ permissions.py（permission_gate → 注册为 SDK can_use_tool 回调）
   │──→ session.py（SessionDispatcher → 并发分发消息）
   │
pool.py ──→ config.py（log_debug, log_error）
   │──→ claude_agent_sdk（ClaudeSDKClient, ClaudeAgentOptions）
   │
handler.py ──→ config.py（OWNER_ID, BOT_NAME, log_debug）
   │──→ pool.py（ClientPool → pool.get(session_id) 获取独立 client）
   │──→ lark.py（add_reaction, remove_reaction, reply_message）
   │──→ permissions（set_sender → contextvars 写入当前发送者）
   │
session.py ──→ config.py（log_error）
   │
permissions.py ──→ config.py（OWNER_ID）
   │──→ contextvars（_current_sender_id 为 ContextVar，支持并发隔离）
   │
lark.py ──→ config.py（log_error）
config.py ──→ 无内部依赖（叶节点，读取 config.json + persona.md + HEADLESS_RULES + 日志系统）
```

## 6. 数据流概要

`lark-cli stdout (NDJSON)` → `main.py` 逐行读取解析（`_read_or_shutdown` 多路复用）→ `should_respond` 过滤 → `compute_session_id` 计算会话标识 → `SessionDispatcher.dispatch` 分发到 per-session 队列 → `handle_message(pool, event)` 从 `ClientPool` 获取独立 client → 组装 prompt 并调用 Claude SDK（带 session_id）→ `permission_gate` 拦截敏感工具调用（contextvars 隔离 sender）→ `lark.reply_message` 回复飞书。
