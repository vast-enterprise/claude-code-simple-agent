<!-- This entire block is your raw intelligence report for other agents. It is NOT a final document. -->

### Code Sections (The Evidence)

- `docs/plans/2026-04-08-digital-avatar-design.md`: 设计文档原文，定义架构、组件清单、消息处理流程、权限模型、MVP 范围、后续迭代方向。
- `src/main.py` (`main`, `start_event_listener`): 入口主进程。启动 lark-cli 事件订阅子进程，初始化 `ClaudeSDKClient`，串行读取 NDJSON 事件行，调用 `should_respond` 过滤后交给 `handle_message`。注册 SIGTERM/SIGINT 清理钩子，强制 kill 两个子进程组。
- `src/config.py` (`ROOT`, `CONFIG`, `PERSONA`, `OWNER_ID`): 配置加载模块。从 `config.json` 读取运行参数，从 `persona.md` 读取人格文本，导出 `OWNER_ID` 供权限判断使用。
- `src/handler.py` (`should_respond`, `handle_message`): 消息过滤与处理。`should_respond` 实现三条过滤规则；`handle_message` 组装 prompt、调用 SDK、收集流式回复、管理表情反馈、调用 `reply_message`。
- `src/permissions.py` (`permission_gate`, `_current_sender_id`): 权限判断。全局变量 `_current_sender_id` 在每次请求前由 `handle_message` 写入，`permission_gate` 作为 `can_use_tool` 回调，对非所有者的敏感 Bash 命令返回 `PermissionResultDeny`。
- `src/lark.py` (`add_reaction`, `remove_reaction`, `reply_message`): 飞书交互层。`add_reaction` 打表情（处理中状态），`remove_reaction` 移除表情，`reply_message` 调用飞书 reply API，超过 4000 字符截断。
- `persona.md`: 人格定义文件，注入 `system_prompt`。包含身份、语气、OKR、能力边界、权限规则、回复格式。
- `config.json`: 运行配置。包含 `owner_open_id`、`model`、`effort`、`max_turns`、`env`（模型 API 地址和 token）。
- `pyproject.toml`: 项目依赖声明。唯一运行时依赖 `claude-agent-sdk>=0.1.56`，Python 要求 `>=3.12`，测试路径 `src/__tests__`。
- `src/__tests__/permissions.py` (`TestPermissionGate`): 权限模块单元测试，覆盖所有者允许、非所有者拒绝、安全命令放行、非 Bash 工具放行、参数化敏感命令拒绝。
- `src/__tests__/handler.py` (`TestShouldRespond`, `TestHandleMessage`): handler 模块单元测试，覆盖 p2p/group 过滤逻辑、完整回复流程、空内容跳过、错误兜底、@mention 清理。

---

### Report (The Answers)

#### result

**架构设计**

系统由两个长驻子进程构成：
1. `lark-cli event +subscribe` — WebSocket 长连接，接收飞书 `im.message.receive_v1` 事件，输出 NDJSON 到 stdout。
2. `ClaudeSDKClient` — Claude Code SDK 客户端，`cwd` 指向 `tripo-work-center`，自动加载 `CLAUDE.md` 和全部 skill。

`main.py` 是事件循环，逐行读取 lark-cli 的 NDJSON 输出，过滤后串行调用 SDK 处理。

**组件清单**

| 组件 | 文件 | 职责 |
|------|------|------|
| 主进程 | `src/main.py` | 事件循环、进程管理、信号处理 |
| 消息过滤与处理 | `src/handler.py` | 过滤规则、prompt 组装、流式回复收集 |
| 权限判断 | `src/permissions.py` | `can_use_tool` 回调，敏感操作拦截 |
| 飞书交互 | `src/lark.py` | 表情反馈、消息回复 |
| 配置加载 | `src/config.py` | config.json 读取、persona.md 读取 |
| 人格定义 | `persona.md` | 注入 system_prompt 的身份/语气/边界规则 |
| 运行配置 | `config.json` | owner_id、模型参数、API 环境变量 |

**消息处理流程**

1. `lark-cli` 收到飞书事件，输出一行 JSON 到 stdout。
2. `main.py` 读取该行，`json.loads` 解析。
3. `should_respond(event)` 过滤：
   - `sender_type == "bot"` → 忽略（防循环）
   - `chat_type == "p2p"` → 直接响应
   - `chat_type == "group"` 且 content 含 `@_user_1` → 响应，否则忽略
4. `handle_message` 执行：
   - 清除 content 中的 `@_user_1` 标记
   - 写入全局 `permissions._current_sender_id = sender_id`
   - 组装 prompt：`"[所有者/同事] 在群聊/私聊中说：{content}"`
   - `client.query(prompt)` 发送给 Claude SDK
   - 异步迭代 `client.receive_response()`：首条 `AssistantMessage` 到达时打表情 "OnIt"，累积 `TextBlock.text`；收到 `ResultMessage` 时退出循环
   - 移除表情，调用 `reply_message` 回复
5. `reply_message` 调用飞书 `/open-apis/im/v1/messages/{id}/reply`，超 4000 字符截断。

**权限模型**

- 两级权限：所有者（`owner_open_id`）和其他同事。
- 判断时机：每次 Bash 工具调用前，SDK 触发 `permission_gate` 回调。
- 敏感关键词列表：`deploy`, `git push`, `git merge`, `git reset`, `rm -rf`, `drop `。
- 非所有者触发敏感命令 → `PermissionResultDeny`，回复固定文案。
- 非 Bash 工具调用 → 无论发送者身份，一律 `PermissionResultAllow`。
- 已知缺陷（代码注释明确标注）：`_current_sender_id` 是全局变量，仅适用于串行处理，并发场景需改为 per-request context。

**MVP 范围**

- 单 session 串行处理（所有消息共用 default session）
- @bot 触发 + P2P 直接响应
- 人格注入（`persona.md` append 到 `system_prompt`）
- 权限分级（owner vs 同事）
- 复用现有 skill 体系（`setting_sources=["project"]`，`permission_mode="bypassPermissions"`）

**后续迭代方向**

| 优先级 | 方向 | 说明 |
|--------|------|------|
| P1 | 多 session 隔离 | 按 单聊/群聊 + 用户 分配不同 session_id |
| P1 | 并发排队 | 同一 session 串行排队 |
| P1 | 进程重连 | SDK 子进程崩溃后自动重连 |
| P2 | 多会话可观测性 | session 列表、token 消耗监控 |
| P2 | 消息长度处理 | 长回复分段或转 Markdown 卡片 |
| P2 | 费用控制 | `max_budget_usd` / `max_turns` 防失控 |
| P3 | 服务端部署 | 迁移到容器，7x24 运行 |

---

#### conclusions

- 实际实现与设计文档高度一致，但代码已拆分为 `src/` 下的 4 个模块（设计文档描述的是单文件 `avatar.py`）。
- `ClaudeAgentOptions` 中 `permission_mode="bypassPermissions"` 表示 SDK 默认跳过所有工具确认，权限控制完全依赖 `can_use_tool=permission_gate` 回调。
- 人格文件 `persona.md` 位于项目根目录（非 `avatar/` 子目录），与设计文档中的文件结构图有出入。
- `config.json` 中模型配置为 `opus`，`effort=max`，`max_turns=100`，API 指向自建代理 `http://120.48.38.233:4000`。
- 消息回复使用飞书 reply API（非 `lark-cli im +messages-reply`），与设计文档架构图描述不同，实际通过 `lark-cli api POST` 直接调用原始接口。
- 表情反馈机制（OnIt 表情 → 处理完成后移除）是设计文档未提及的实现细节，在 `handler.py` 中实现。
- 测试覆盖 `permissions` 和 `handler` 两个核心模块，使用 `pytest`，测试路径 `src/__tests__/`。

---

#### relations

- `main.py` 依赖 `config.py`（读取 CONFIG/PERSONA/ROOT）、`handler.py`（should_respond/handle_message）、`permissions.py`（permission_gate 作为 SDK 回调传入）。
- `handler.py` 依赖 `permissions.py`（写入 `_current_sender_id`）、`config.py`（OWNER_ID 用于 prompt 标签）、`lark.py`（add_reaction/remove_reaction/reply_message）。
- `permissions.py` 依赖 `config.py`（OWNER_ID）。
- `lark.py` 无内部依赖，直接调用 `lark-cli` 子进程。
- `config.py` 读取文件系统上的 `config.json` 和 `persona.md`，无其他内部依赖。
- `ClaudeSDKClient` 在 `main.py` 中初始化，`cwd=ROOT`，通过 `setting_sources=["project"]` 加载 `CLAUDE.md` 和 `.claude/skills/` 下所有 skill，`can_use_tool=permission_gate` 将权限判断注入 SDK 工具调用链。
