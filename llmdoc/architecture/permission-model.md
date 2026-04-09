# 权限模型架构

## 1. Identity

- **What it is:** Digital Avatar 的双层权限控制体系——代码强制层（运行时拦截）与 prompt 约束层（行为引导）。
- **Purpose:** 确保非所有者无法通过飞书消息触发敏感系统操作，同时通过 prompt 约束覆盖代码未拦截的行为边界。

## 2. Core Components

- `src/permissions.py` (`permission_gate`, `SENSITIVE`, `_current_sender_id`): 运行时权限门控，唯一的代码强制执行点。
- `src/handler.py` (`handle_message`): 写入 `_current_sender_id` 全局状态，构造带 `[所有者]`/`[同事]` 角色标签的 prompt。
- `src/main.py` (`main`): 注册 `permission_gate` 为 `ClaudeAgentOptions.can_use_tool` 回调，设置 `permission_mode="bypassPermissions"`。
- `src/config.py` (`OWNER_ID`): 从 `config.json` 的 `owner_open_id` 字段加载，作为所有者身份判定基准。
- `persona.md` (权限规则章节): prompt 层权限定义——所有者全权，同事只读+非敏感。
- `CLAUDE.md` (行为约束表): prompt 层行为约束——禁止 merge、状态变更需确认、通知后阻塞等。

## 3. Execution Flow (LLM Retrieval Map)

### 第一层：代码强制（运行时拦截）

- **1. 身份写入:** 飞书消息到达后，`src/handler.py:42` 将 `sender_id` 写入 `permissions._current_sender_id`。
- **2. 角色标签注入:** `src/handler.py:44-45` 比对 `sender_id == OWNER_ID`，在 prompt 前缀注入 `[所有者]` 或 `[同事]`。
- **3. SDK 工具调用触发:** Claude SDK 每次调用工具前，回调 `src/main.py:45` 注册的 `permission_gate`。
- **4. 门控判定:** `src/permissions.py:15-25` 执行判定逻辑：
  - 仅拦截 `tool_name == "Bash"` 的调用
  - 若 `_current_sender_id != OWNER_ID`，检查 `command` 是否包含 `SENSITIVE` 列表中的子串
  - 命中 → `PermissionResultDeny`（附中文拒绝消息）
  - 未命中或为所有者 → `PermissionResultAllow`

### 第二层：Prompt 约束（行为引导）

- **5. persona.md 注入:** `src/main.py:42` 通过 `SystemPromptPreset(append=PERSONA)` 将 `persona.md` 全文注入 system prompt，其中"权限规则"和"能力边界"章节定义了 Claude 的行为边界。
- **6. CLAUDE.md 加载:** Claude SDK 以 `setting_sources=["project"]` 运行（`src/main.py:44`），自动读取项目根目录的 `CLAUDE.md` 作为会话级指令。

## 4. 所有者/非所有者分级规则

| 维度 | 所有者（`sender_id == OWNER_ID`） | 非所有者 |
|------|----------------------------------|---------|
| Bash 工具 | 全部放行 | SENSITIVE 命令被 Deny |
| 非 Bash 工具 | 全部放行 | 全部放行（代码层无拦截） |
| 部署操作 | prompt 层允许 staging | prompt 层拒绝一切部署 |
| PR 操作 | 可创建/查看，prompt 层禁止 merge | 同左（prompt 约束，非代码强制） |

## 5. SENSITIVE 命令列表

定义于 `src/permissions.py:9`，使用子串匹配（`in` 运算符，非正则）：

`deploy`, `git push`, `git merge`, `git reset`, `rm -rf`, `drop `（注意 drop 后有空格）

## 6. `_current_sender_id` 全局状态的已知限制

- **当前实现:** `src/permissions.py:12` 定义为模块级全局变量 `str | None`，由 `src/handler.py:42` 在每条消息处理前写入。
- **已知缺陷:** 代码注释明确标注"仅适用于串行处理"。当前系统为单进程串行消息处理，无并发风险。
- **并发迭代方向:** 注释指出需改为 per-request context 传递。可选方案包括 `contextvars.ContextVar`（asyncio 原生支持）或将 sender_id 作为参数透传至 `permission_gate`（需 SDK 支持自定义 context）。

## 7. Design Rationale

- **`bypassPermissions` + `can_use_tool` 组合:** SDK 层面绕过默认交互式权限确认（因飞书 bot 无人值守），由 `permission_gate` 回调实现应用层细粒度控制。
- **双层互补:** 代码层仅覆盖 Bash 工具的敏感命令子集；prompt 层覆盖更广的行为边界（如禁止 merge、能力边界、回复风格）。两层非冗余——代码层是硬拦截，prompt 层是软约束。
- **子串匹配而非正则:** 简单直接，但存在误判风险（如命令中包含 "deploy" 字样的非部署操作）。当前 SENSITIVE 列表足够具体，实际误判概率低。
