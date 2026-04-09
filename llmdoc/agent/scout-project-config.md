<!-- This entire block is your raw intelligence report for other agents. It is NOT a final document. -->

### Code Sections (The Evidence)

- `pyproject.toml` (`[project]`): 项目名 `tripo-avatar`，版本 `0.1.0`，Python >= 3.12，唯一运行时依赖 `claude-agent-sdk>=0.1.56`。
- `pyproject.toml` (`[tool.pytest.ini_options]`): 测试路径 `src/__tests__`，pythonpath 为 `.`，匹配 `Test*` 类和 `test_*` 函数。
- `config.example.json` (root config schema): 定义运行时配置结构：`owner_open_id`、`owner_name`、`model`（默认 `opus`）、`effort`（默认 `max`）、`max_turns`（默认 100）、`env` 子对象（含 5 个 Anthropic 环境变量）。
- `persona.md` (persona definition): 定义数字分身身份为"郭凯南的数字分身"，规定语气、OKR、能力边界、权限规则、回复格式。
- `CLAUDE.md` (agent behavior constraints): 定义 Agent 职责边界（技术实现、协作工具、规划评审、沟通通知）、行为约束（提议+确认、禁止 merge、飞书通知后阻塞、lark-cli 必须 `--as bot`）、Skills 目录、进入代码仓铁律。
- `.gitignore` (ignored files): 忽略 `.playwright-cli`、`config.json`（含真实密钥）、`__pycache__`、`tmp`、`.pytest_cache`。
- `src/config.py` (`ROOT`, `CONFIG`, `PERSONA`, `OWNER_ID`): 加载 `config.json`（不存在则 exit(1)）、读取 `persona.md` 文本、暴露 `OWNER_ID` 字符串。
- `src/main.py` (`main`, `start_event_listener`): 入口，启动 `lark-cli event +subscribe` 子进程，构造 `ClaudeAgentOptions`（`permission_mode="bypassPermissions"`，`system_prompt` 附加 persona，`can_use_tool=permission_gate`），事件循环读取飞书消息并调用 `handle_message`。
- `src/handler.py` (`should_respond`, `handle_message`): 过滤逻辑（p2p 全响应，group 仅响应 @bot），构造带 `[所有者]`/`[同事]` 标签的 prompt，调用 Claude SDK，收集 `TextBlock` 拼接后回复。
- `src/lark.py` (`add_reaction`, `remove_reaction`, `reply_message`): 通过 `lark-cli` subprocess 实现飞书表情反馈和消息回复，全部使用 `--as bot`，回复超 4000 字符截断。
- `src/permissions.py` (`permission_gate`, `SENSITIVE`, `_current_sender_id`): 非所有者发起的 Bash 工具调用，若命令包含 `SENSITIVE` 关键词则 Deny；全局变量 `_current_sender_id` 仅适用于串行处理。

### Report (The Answers)

#### result

- 项目定位：`tripo-work-center` 是一个纯调度中枢，不含业务代码仓库。其核心产物是 `tripo-avatar`——一个基于 Claude Code SDK 的飞书机器人数字分身，代表用户郭凯南在飞书群中自动响应消息。
- 依赖管理：使用 `pyproject.toml` 管理，Python >= 3.12，唯一运行时依赖为 `claude-agent-sdk>=0.1.56`，无其他第三方库。测试框架为 pytest，配置内嵌于 `pyproject.toml`。
- 运行配置：通过 `config.json`（从 `config.example.json` 复制并填写）加载，包含所有者 open_id、模型选择（opus/sonnet/haiku）、effort 级别、max_turns 上限，以及 5 个 Anthropic 环境变量。`config.json` 被 `.gitignore` 排除，不进入版本控制。
- 人格定义：`persona.md` 以 Markdown 形式定义，在运行时由 `src/config.py` 读取为字符串，作为 `system_prompt` 的 `append` 字段注入 Claude SDK。人格规定了语气、OKR、能力边界（可查询/部署 staging，不可 merge PR/生产部署）、双级权限（所有者全权，同事只读+非敏感）。
- Agent 行为约束：`CLAUDE.md` 定义了 5 条行为约束（状态变更需提议+确认、禁止 merge、开发以 PR 为闭环、飞书通知后必须 AskUserQuestion 阻塞、lark-cli 必须 `--as bot`）和 7 个 Skills 入口。这些约束作用于 Claude Code 会话层，不是运行时代码强制执行的。
- 运行时权限强制：`src/permissions.py` 的 `permission_gate` 是唯一运行时权限执行点，仅拦截非所有者触发的 Bash 工具中包含敏感关键词（deploy、git push、git merge、git reset、rm -rf、drop）的调用。其余约束（如禁止 merge）依赖 persona/CLAUDE.md 的 prompt 层约束，无代码强制。

#### conclusions

- 项目是 Python 异步服务，入口为 `src/main.py`，通过 `asyncio` 事件循环驱动。
- 飞书交互全部通过 `lark-cli` CLI 工具的 subprocess 调用实现，不直接调用飞书 SDK。
- Claude SDK 以 `bypassPermissions` 模式运行，但通过 `can_use_tool=permission_gate` 回调实现细粒度的运行时权限控制。
- `_current_sender_id` 是全局变量，代码注释明确标注"仅适用于串行处理"，并发场景存在竞态风险。
- `config.json` 含真实密钥，被 `.gitignore` 排除；`config.example.json` 是安全的模板文件，进入版本控制。
- 消息处理流程：飞书事件 → `should_respond` 过滤 → 设置 `_current_sender_id` → 构造带角色标签的 prompt → Claude SDK query → 流式收集 TextBlock → 回复飞书消息。

#### relations

- `src/main.py` 依赖 `src/config.py`（加载 CONFIG/PERSONA/ROOT）、`src/handler.py`（should_respond/handle_message）、`src/permissions.py`（permission_gate）。
- `src/handler.py` 依赖 `src/config.py`（OWNER_ID）、`src/lark.py`（add_reaction/remove_reaction/reply_message）、`src/permissions.py`（设置 `_current_sender_id`）。
- `src/config.py` 读取文件系统上的 `config.json` 和 `persona.md`，两者均位于项目根目录。
- `src/permissions.py` 的 `permission_gate` 被 `src/main.py` 注册为 `ClaudeAgentOptions.can_use_tool`，由 Claude SDK 在每次工具调用前回调；`_current_sender_id` 由 `src/handler.py` 在每次消息处理前写入。
- `persona.md` 通过 `src/config.py` → `src/main.py` 的 `SystemPromptPreset(append=PERSONA)` 注入 Claude SDK，影响所有会话的系统提示。
- `CLAUDE.md` 作用于 Claude Code 会话层（项目级指令），与运行时代码无直接调用关系，但约束 Agent 在会话中的行为决策。
