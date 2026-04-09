<!-- This entire block is your raw intelligence report for other agents. It is NOT a final document. -->

### Code Sections (The Evidence)

- `src/config.py` (`ROOT`, `CONFIG`, `PERSONA`, `OWNER_ID`): 模块级启动时加载。`ROOT` 为项目根目录（`__file__` 向上两级）。从 `config.json` 读取 `CONFIG` dict，从 `persona.md` 读取 `PERSONA` 字符串，从 `CONFIG["owner_open_id"]` 提取 `OWNER_ID`。`config.json` 不存在时直接 `sys.exit(1)`。

- `config.example.json`: 配置模板。字段：`owner_open_id`、`owner_name`、`model`、`effort`、`max_turns`、`env`（含 `ANTHROPIC_BASE_URL`、`ANTHROPIC_AUTH_TOKEN`、`ANTHROPIC_MODEL`、`ANTHROPIC_DEFAULT_HAIKU_MODEL`、`ANTHROPIC_DEFAULT_SONNET_MODEL`、`ANTHROPIC_DEFAULT_OPUS_MODEL`）。

- `persona.md`: Claude SDK 的 system prompt 附加内容。定义身份（郭凯南数字分身）、语气、OKR、能力边界、权限规则、回复格式。

- `src/permissions.py` (`_current_sender_id`): 模块级全局变量，保存当前请求的 sender_id。注释明确标注"仅适用于串行处理，并发时必须改为 per-request context"。

- `src/permissions.py` (`permission_gate`): 异步函数，签名 `(tool_name, tool_input, context) -> PermissionResultAllow | PermissionResultDeny`。仅拦截 `Bash` 工具。非 owner 发起时，检查 `command` 是否包含 `SENSITIVE` 列表中的任意字符串（`deploy`、`git push`、`git merge`、`git reset`、`rm -rf`、`drop `）。命中则返回 `PermissionResultDeny`，否则一律 `PermissionResultAllow`。

- `src/lark.py` (`add_reaction`): 同步函数。调用 `lark-cli im reactions create --as bot`，返回 `reaction_id` 字符串或 `None`（失败时）。

- `src/lark.py` (`remove_reaction`): 同步函数。调用 `lark-cli im reactions delete --as bot`。失败时打印 stderr，不抛异常。

- `src/lark.py` (`reply_message`): 同步函数。文本超 4000 字符时截断至 3950 并追加截断提示。调用 `lark-cli api POST /open-apis/im/v1/messages/{message_id}/reply --as bot`。失败时打印 stderr，不抛异常。

- `src/handler.py` (`should_respond`): 纯函数。过滤规则：`sender_type == "bot"` 直接返回 `False`；`p2p` 聊天无条件返回 `True`；`group` 聊天仅当 content 含 `@_user_1` 时返回 `True`。

- `src/handler.py` (`handle_message`): 异步函数。流程：清理 `@_user_1` mention → 写入 `permissions._current_sender_id` → 构造带 sender 标签的 prompt → `client.query(prompt)` → 异步迭代 `client.receive_response()`：首条 `AssistantMessage` 到达时调用 `add_reaction`，累积所有 `TextBlock.text`；收到 `ResultMessage` 时退出循环 → 移除 reaction → 调用 `reply_message`。

- `src/main.py` (`start_event_listener`): 异步函数。以 `start_new_session=True` 启动 `lark-cli event +subscribe --event-types im.message.receive_v1 --compact --quiet --as bot` 子进程，stdout 为 PIPE，stderr 丢弃。

- `src/main.py` (`main`): 程序入口。构造 `ClaudeAgentOptions`（`permission_mode="bypassPermissions"`，`system_prompt` 使用 `claude_code` preset 并 append `PERSONA`，`can_use_tool=permission_gate`）。注册 `SIGTERM`/`SIGINT` 信号处理器 `cleanup`。主循环逐行读取 listener stdout，JSON 解析后经 `should_respond` 过滤，再调用 `handle_message`。

- `src/main.py` (`_force_kill_sdk_process`): 内部函数。通过访问 `client._transport._process` 私有属性强制 `SIGKILL` SDK 子进程组。注释标注依赖 `claude_agent_sdk==0.1.x` 内部结构。

- `src/main.py` (`cleanup`): 信号处理器。依次 `SIGKILL` lark-cli 进程组和 Claude SDK 进程组，最后 `os._exit(0)`。

- `pyproject.toml`: 项目名 `tripo-avatar`，Python `>=3.12`，唯一运行时依赖 `claude-agent-sdk>=0.1.56`。测试路径 `src/__tests__`，`pythonpath=["."]`。

- `src/__tests__/handler.py`: 覆盖 `should_respond`（7 个用例）和 `handle_message`（4 个用例）。使用 `unittest.mock` patch lark 函数，用 async generator 模拟 `receive_response`。

- `src/__tests__/permissions.py`: 覆盖 `permission_gate`（6 个用例，含 parametrize 4 条敏感命令）。直接操作 `permissions._current_sender_id` 全局变量设置测试状态。

- `src/__tests__/lark.py`: 覆盖 `reply_message`（3 个用例）、`add_reaction`（2 个用例）、`remove_reaction`（1 个用例）。全部 patch `subprocess.run`。

---

### Report (The Answers)

#### result

**config.py**
- 职责：配置加载与校验，提供全局常量。
- 公开 API：`ROOT: Path`、`CONFIG: dict`、`PERSONA: str`、`OWNER_ID: str`。
- 依赖：标准库 `json`、`sys`、`pathlib`；外部文件 `config.json`、`persona.md`。
- 关键设计：模块导入时立即执行，`config.json` 缺失直接退出进程，无懒加载。

**lark.py**
- 职责：封装所有飞书 API 交互，通过 `lark-cli` CLI 工具（同步子进程）实现。
- 公开 API：`add_reaction(message_id, emoji_type) -> str | None`、`remove_reaction(message_id, reaction_id)`、`reply_message(message_id, text)`。
- 依赖：标准库 `json`、`subprocess`、`sys`；外部命令 `lark-cli`（必须在 PATH 中）。
- 关键设计：全部为同步阻塞调用（`subprocess.run`）；所有调用强制 `--as bot`；`reply_message` 有 4000 字符硬截断；失败静默（打印 stderr，不抛异常）。

**permissions.py**
- 职责：Claude SDK 工具调用权限门控，阻止非 owner 执行敏感 Bash 命令。
- 公开 API：`permission_gate(tool_name, tool_input, context) -> PermissionResultAllow | PermissionResultDeny`（异步）；`_current_sender_id: str | None`（模块级全局变量，供 handler 写入）。
- 依赖：`claude_agent_sdk.types`；`src.config.OWNER_ID`。
- 关键设计：仅拦截 `Bash` 工具；权限判断基于字符串子串匹配（非正则）；全局状态 `_current_sender_id` 是已知并发缺陷，代码注释已标注。

**handler.py**
- 职责：消息过滤逻辑（`should_respond`）和单条消息完整处理流程（`handle_message`）。
- 公开 API：`should_respond(event: dict) -> bool`、`handle_message(client: ClaudeSDKClient, event: dict)`（异步）。
- 依赖：`claude_agent_sdk`（`ClaudeSDKClient`、`AssistantMessage`、`ResultMessage`、`TextBlock`）；`src.permissions`（写全局变量）；`src.config.OWNER_ID`；`src.lark`（三个函数）。
- 关键设计：reaction 作为"正在处理"视觉反馈，首条 AssistantMessage 到达时添加，处理完成后移除；prompt 中注入 sender 角色标签（`[所有者]`/`[同事]`）；`@_user_1` mention 在传给 Claude 前被清除。

**main.py**
- 职责：程序入口、事件循环、子进程生命周期管理。
- 公开 API：无（脚本入口）。
- 依赖：`claude_agent_sdk`（`ClaudeSDKClient`、`ClaudeAgentOptions`、`SystemPromptPreset`）；`src.config`、`src.handler`、`src.permissions`；标准库 `asyncio`、`signal`、`os`、`json`、`sys`。
- 关键设计：`permission_mode="bypassPermissions"` + `can_use_tool=permission_gate` 组合——SDK 层面绕过默认权限，由自定义 gate 接管；lark-cli 以独立进程组启动（`start_new_session=True`），便于 `SIGKILL` 整组；`_force_kill_sdk_process` 依赖 SDK 私有属性，存在版本升级风险；信号处理走 `os._exit(0)` 硬退出，不经过 `finally` 块。

#### conclusions

- 整个系统是单进程、串行消息处理架构：一次只处理一条飞书消息，无并发。
- 飞书交互全部通过 `lark-cli` CLI 工具的同步子进程完成，无直接 HTTP 调用。
- Claude SDK 以 `claude_code` system prompt preset 运行，附加 `persona.md` 作为身份定义。
- 权限控制分两层：`permission_mode="bypassPermissions"`（SDK 层）+ `permission_gate`（应用层），应用层仅对 Bash 工具的敏感命令做 owner 校验。
- `permissions._current_sender_id` 是全局可变状态，在 `handle_message` 中写入，在 `permission_gate` 中读取，是已知的并发安全缺陷。
- 消息过滤规则：bot 消息全部忽略；p2p 消息全部响应；群聊消息仅响应 `@_user_1` mention。
- 唯一运行时依赖为 `claude-agent-sdk>=0.1.56`，Python 要求 `>=3.12`。
- 测试覆盖三个业务模块（`lark`、`handler`、`permissions`），全部使用 `unittest.mock` patch 外部依赖，无集成测试。

#### relations

- `main.py` 导入并使用 `config.py`（`ROOT`、`CONFIG`、`PERSONA`）、`handler.py`（`should_respond`、`handle_message`）、`permissions.py`（`permission_gate` 作为 `can_use_tool` 回调传入 SDK）。
- `handler.py` 导入 `config.py`（`OWNER_ID`）、`lark.py`（三个函数）、`permissions`（直接写 `_current_sender_id`）。
- `permissions.py` 导入 `config.py`（`OWNER_ID`）。
- `lark.py` 不依赖项目内任何模块，是叶节点。
- `config.py` 不依赖项目内任何模块，是叶节点。
- 数据流：`lark-cli stdout` → `main.py`（JSON 解析）→ `handler.should_respond`（过滤）→ `handler.handle_message`（处理）→ `permissions._current_sender_id`（写入）→ `ClaudeSDKClient.query`（触发 Claude）→ `permission_gate`（工具调用拦截）→ `lark.reply_message`（回复）。
- `__tests__/handler.py` 测试 `src/handler.py`，patch `src.handler.{add_reaction,remove_reaction,reply_message}`（即 lark 模块在 handler 命名空间中的引用）。
- `__tests__/permissions.py` 测试 `src/permissions.py`，直接操作 `src.permissions._current_sender_id`。
- `__tests__/lark.py` 测试 `src/lark.py`，patch `src.lark.subprocess.run`。
