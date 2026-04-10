# 权限模型架构

## 1. Identity

- **What it is:** Digital Avatar 的双层权限控制体系——工具禁用层（SDK 硬拦截）与 prompt 约束层（行为引导）。注：`bypassPermissions` 模式下 `can_use_tool` 回调和 `permissions.deny` 规则均被跳过，代码强制层实际不生效，仅 `disallowed_tools` 和 prompt 约束有效。
- **Purpose:** 确保非所有者无法通过飞书消息触发敏感系统操作，同时通过 prompt 约束覆盖代码未拦截的行为边界。

## 2. Core Components

- `src/permissions.py` (`permission_gate`, `set_sender`, `get_sender`, `_current_sender_id`, `SENSITIVE`): 运行时权限门控，唯一的代码强制执行点。`_current_sender_id` 为 `contextvars.ContextVar`，支持并发隔离。
- `src/handler.py` (`handle_message`, `compute_session_id`): 调用 `permissions.set_sender(sender_id)` 写入 contextvars，构造带 `[所有者]`/`[同事]` 角色标签的 prompt。
- `src/main.py` (`main`): 构造 `ClaudeAgentOptions`（含 `permission_gate` 为 `can_use_tool` 回调、`permission_mode="bypassPermissions"`、`disallowed_tools`），传入 `ClientPool(options)`。Pool 为每个 session 惰性创建 client 时使用相同的 options。
- `src/config.py` (`OWNER_ID`, `HEADLESS_RULES`, `DISALLOWED_TOOLS`): 从 `config.json` 的 `owner_open_id` 字段加载所有者身份；`HEADLESS_RULES` 定义 headless 模式运行约束；`DISALLOWED_TOOLS` 硬编码禁用交互式工具（AskUserQuestion、ExitPlanMode、EnterPlanMode）。
- `persona.md` (权限规则章节): prompt 层权限定义——所有者全权，同事只读+非敏感。
- `CLAUDE.md` (行为约束表): prompt 层行为约束——禁止 merge、状态变更需确认、通知后阻塞等。

## 3. Execution Flow (LLM Retrieval Map)

### 第一层：工具禁用（SDK 硬拦截）

- **0. disallowed_tools:** `src/main.py` 通过 `ClaudeAgentOptions(disallowed_tools=["AskUserQuestion", "ExitPlanMode", "EnterPlanMode"])` 在 SDK 层面禁用交互式工具。模型尝试调用时 CLI 直接返回拒绝，不经过 `permission_gate`。
- **0a. HEADLESS_RULES prompt 引导:** `src/config.py` 定义 `HEADLESS_RULES` 常量，通过 `SystemPromptPreset(append=PERSONA + HEADLESS_RULES)` 拼接到 system prompt，从 prompt 层引导模型不要尝试调用这些工具。与 `disallowed_tools` 形成双保险。

### 第二层：Prompt 约束（行为引导）

- **1. persona.md 注入:** `src/main.py` 通过 `SystemPromptPreset(append=PERSONA + HEADLESS_RULES)` 将人格文本和运行环境约束注入 system prompt。
- **2. CLAUDE.md 加载:** 每个 per-session `ClaudeSDKClient` 以 `setting_sources=["user", "project"]` 运行，自动读取用户级和项目级 settings，加载 skills/plugins/mcp。

### 已验证不生效的机制（bypassPermissions 限制）

- **`can_use_tool` 回调（`permission_gate`）：** `bypassPermissions` 模式下 CLI 不发送 `can_use_tool` 控制请求，回调永远不被触发。`permission_gate` 中的 Bash 敏感命令拦截和 sender 身份检查实际不生效。保留代码是为未来迁移到 `default` 模式做准备。
- **`permissions.deny` 规则：** `bypassPermissions` 同样跳过 deny 规则，无法通过 settings 的 `permissions.deny` 拦截特定 Skill。
- **Skill 黑名单：** `disallowed_tools` 仅支持工具名级别匹配，不支持 `Skill(sigma)` 这种参数级匹配。在 `bypassPermissions` 模式下无可行方案精确禁用特定 Skill。

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

- **`bypassPermissions` + `can_use_tool` 组合的局限:** `bypassPermissions` 让 CLI 自动放行所有工具调用，不发送 `can_use_tool` 控制请求。`permission_gate` 回调实际不被触发。选择保留 `bypassPermissions` 是因为 headless 环境无人交互，且 `permission_gate` 的 Bash 敏感命令拦截在当前场景下投入产出比低（persona prompt 已覆盖行为边界）。若未来需要代码层强制拦截，需迁移到 `default` 模式 + `permissions.allow/deny` 体系。
- **`contextvars.ContextVar` 而非参数透传:** `permission_gate` 回调签名由 SDK 定义，不支持自定义 context 参数。选择 `ContextVar` 实现 per-task 隔离，无需修改 SDK 调用侧代码。
- **`disallowed_tools` 解决 headless 环境工具不可用问题:** Claude Code preset 的 system prompt 包含 `AskUserQuestion`、`ExitPlanMode`、`EnterPlanMode` 等交互式工具定义，模型会尝试调用。`disallowed_tools` 在 CLI 层面硬拦截（已验证在 `bypassPermissions` 下仍然生效），`HEADLESS_RULES` 在 prompt 层面引导模型不去尝试。两者分离于 `persona.md` 之外——persona 只管人格定义，运行环境约束由 `HEADLESS_RULES` 承担。
- **子串匹配而非正则:** 简单直接，但存在误判风险（如命令中包含 "deploy" 字样的非部署操作）。当前 SENSITIVE 列表足够具体，实际误判概率低。
