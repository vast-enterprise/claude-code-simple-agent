# 权限模型架构

## 1. Identity

- **What it is:** Digital Avatar 的三层权限控制体系——工具禁用层（SDK 硬拦截）、代码强制层（运行时拦截）与 prompt 约束层（行为引导）。
- **Purpose:** 确保非所有者无法通过飞书消息触发敏感系统操作，同时通过 prompt 约束覆盖代码未拦截的行为边界。

## 2. Core Components

- `src/permissions.py` (`permission_gate`, `set_sender`, `get_sender`, `_current_sender_id`, `SENSITIVE`): 运行时权限门控，唯一的代码强制执行点。`_current_sender_id` 为 `contextvars.ContextVar`，支持并发隔离。
- `src/handler.py` (`handle_message`, `compute_session_id`): 调用 `permissions.set_sender(sender_id)` 写入 contextvars，构造带 `[所有者]`/`[同事]` 角色标签的 prompt。
- `src/main.py` (`main`): 注册 `permission_gate` 为 `ClaudeAgentOptions.can_use_tool` 回调，设置 `permission_mode="bypassPermissions"`；通过 `disallowed_tools` 硬拦截交互式工具；拼接 `HEADLESS_RULES` 到 system prompt。
- `src/config.py` (`OWNER_ID`, `HEADLESS_RULES`, `DISALLOWED_TOOLS`, `DISALLOWED_SKILLS`): 从 `config.json` 的 `owner_open_id` 字段加载所有者身份；`HEADLESS_RULES` 定义 headless 模式运行约束；`DISALLOWED_TOOLS` 合并硬编码（交互式工具）+ config 中的纯工具名；`DISALLOWED_SKILLS` 从 config 中 `Skill(xxx)` 格式解析出 skill 名集合，供 `permission_gate` 拦截。
- `persona.md` (权限规则章节): prompt 层权限定义——所有者全权，同事只读+非敏感。
- `CLAUDE.md` (行为约束表): prompt 层行为约束——禁止 merge、状态变更需确认、通知后阻塞等。

## 3. Execution Flow (LLM Retrieval Map)

### 第一层：工具禁用（SDK 硬拦截）

- **0. disallowed_tools:** `src/main.py` 通过 `ClaudeAgentOptions(disallowed_tools=["AskUserQuestion", "ExitPlanMode", "EnterPlanMode"])` 在 SDK 层面禁用交互式工具。模型尝试调用时 CLI 直接返回拒绝，不经过 `permission_gate`。
- **0a. HEADLESS_RULES prompt 引导:** `src/config.py` 定义 `HEADLESS_RULES` 常量，通过 `SystemPromptPreset(append=PERSONA + HEADLESS_RULES)` 拼接到 system prompt，从 prompt 层引导模型不要尝试调用这些工具。与 `disallowed_tools` 形成双保险。

### 第二层：代码强制（运行时拦截）

- **1. Skill 黑名单拦截:** `permission_gate` 检查 `tool_name == "Skill"` 时，从 `tool_input["skill"]` 取 skill 名，若在 `DISALLOWED_SKILLS` 集合中则返回 `PermissionResultDeny`。此机制弥补了 `disallowed_tools` 无法精确到 Skill 参数的限制。
- **2. 身份写入:** 飞书消息到达后，`src/handler.py:53` 调用 `permissions.set_sender(sender_id)` 将 sender_id 写入 `_current_sender_id`（`ContextVar`）。
- **3. 角色标签注入:** `src/handler.py:55-56` 比对 `sender_id == OWNER_ID`，在 prompt 前缀注入 `[所有者]` 或 `[同事]`。
- **4. SDK 工具调用触发:** Claude SDK 每次调用工具前，回调 `src/main.py` 注册的 `permission_gate`。
- **5. Bash 门控判定:** `src/permissions.py` 执行判定逻辑：
  - 仅拦截 `tool_name == "Bash"` 的调用
  - 若 `sender is None`（context 丢失，如 SDK 内部调用未经 handler 设置 sender）→ 直接 `PermissionResultDeny`
  - 若 `get_sender() != OWNER_ID`，检查 `command` 是否包含 `SENSITIVE` 列表中的子串
  - 命中 → `PermissionResultDeny`（附中文拒绝消息）
  - 未命中或为所有者 → `PermissionResultAllow`

### 第三层：Prompt 约束（行为引导）

- **5. persona.md 注入:** `src/main.py:42` 通过 `SystemPromptPreset(append=PERSONA)` 将 `persona.md` 全文注入 system prompt，其中"权限规则"和"能力边界"章节定义了 Claude 的行为边界。
- **6. CLAUDE.md 加载:** Claude SDK 以 `setting_sources=["user", "project"]` 运行，自动读取用户级和项目级 settings，加载 skills/plugins/mcp。通过 `config.json` 的 `disallowed_tools` 字段配置黑名单裁剪不需要的工具。

## 4. 所有者/非所有者分级规则

| 维度 | 所有者（`sender_id == OWNER_ID`） | 非所有者 | Unknown（`sender is None`） |
|------|----------------------------------|---------|---------------------------|
| Bash 工具 | 全部放行 | SENSITIVE 命令被 Deny | 一律 Deny |
| 非 Bash 工具 | 全部放行 | 全部放行（代码层无拦截） | 全部放行 |
| 部署操作 | prompt 层允许 staging | prompt 层拒绝一切部署 | 代码层 Deny + prompt 层拒绝 |
| PR 操作 | 可创建/查看，prompt 层禁止 merge | 同左（prompt 约束，非代码强制） | 同非所有者 |

## 5. SENSITIVE 命令列表

定义于 `src/permissions.py:9`，使用子串匹配（`in` 运算符，非正则）：

`deploy`, `git push`, `git merge`, `git reset`, `rm -rf`, `drop `（注意 drop 后有空格）

## 6. `_current_sender_id` 并发隔离实现

- **当前实现:** `src/permissions.py:14-16` 定义为 `contextvars.ContextVar[str | None]`，通过 `set_sender()` / `get_sender()` 公开 API 访问（`src/permissions.py:19-26`）。
- **并发安全:** `ContextVar` 是 Python 3.7+ 内置的 per-task 上下文隔离机制，在 `SessionDispatcher` 并发分发场景下，每个 worker task 持有独立的 sender 上下文，`permission_gate` 回调中 `get_sender()` 正确返回当前请求的发送者。
- **测试覆盖:** `src/__tests__/permissions.py` 中的 `test_concurrent_sender_isolation` 验证了并发场景下 sender 隔离正确性。

## 7. Design Rationale

- **`bypassPermissions` + `can_use_tool` 组合:** SDK 层面绕过默认交互式权限确认（因飞书 bot 无人值守），由 `permission_gate` 回调实现应用层细粒度控制。
- **`contextvars.ContextVar` 而非参数透传:** `permission_gate` 回调签名由 SDK 定义，不支持自定义 context 参数。选择 `ContextVar` 实现 per-task 隔离，无需修改 SDK 调用侧代码。
- **双层互补:** 代码层仅覆盖 Bash 工具的敏感命令子集；prompt 层覆盖更广的行为边界（如禁止 merge、能力边界、回复风格）。两层非冗余——代码层是硬拦截，prompt 层是软约束。
- **`disallowed_tools` 解决 headless 环境工具不可用问题:** Claude Code preset 的 system prompt 包含 `AskUserQuestion`、`ExitPlanMode`、`EnterPlanMode` 等交互式工具定义，模型会尝试调用。`disallowed_tools` 在 CLI 层面硬拦截，`HEADLESS_RULES` 在 prompt 层面引导模型不去尝试。两者分离于 `persona.md` 之外——persona 只管人格定义，运行环境约束由 `HEADLESS_RULES` 承担。
- **Skill 黑名单通过 `permission_gate` 而非 `disallowed_tools` 实现:** CLI 的 `--disallowedTools` 只支持工具名级别的匹配（如 `Bash(git:*)`），不支持 `Skill(sigma)` 这种按参数值匹配。因此 `config.json` 中 `Skill(xxx)` 格式的条目由 `src/config.py` 解析为 `DISALLOWED_SKILLS` 集合，在 `permission_gate` 回调中拦截。配置格式统一为 `disallowed_tools` 数组，解析逻辑自动分流。
- **子串匹配而非正则:** 简单直接，但存在误判风险（如命令中包含 "deploy" 字样的非部署操作）。当前 SENSITIVE 列表足够具体，实际误判概率低。
