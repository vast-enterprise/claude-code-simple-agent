# 人格系统架构

## 1. Identity

- **What it is:** `persona.md` 是数字分身的"灵魂"，定义在运行时通过 `SystemPromptPreset(append=...)` 注入 Claude SDK 的人格文本。
- **Purpose:** 赋予 bot 身份认同、行为边界和交互风格，使其在飞书群聊中代表郭凯南回应同事。

## 2. Core Components

- `persona.md` (`Identity`, `Tone`, `OKR`, `CapabilityBoundary`, `PermissionRules`, `ResponseFormat`): 人格定义文件，运行时被 `src/config.py` 读取为字符串。
- `src/config.py` (`ROOT`, `CONFIG`, `PERSONA`, `HEADLESS_RULES`, `OWNER_ID`): 配置加载模块，将 `persona.md` 内容读入 `PERSONA` 常量，`HEADLESS_RULES` 定义 headless 模式运行约束（禁止交互式工具），两者独立存放。
- `src/main.py` (`main`): 构造 `ClaudeAgentOptions` 时以 `system_prompt=SystemPromptPreset(append=PERSONA)` 将人格文本追加到 system prompt。
- `src/permissions.py` (`permission_gate`, `_current_sender_id`, `SENSITIVE`): 运行时权限执行点，在代码层拦截非所有者的敏感 Bash 命令。
- `CLAUDE.md`: Claude Code 项目级指令文件，通过 `setting_sources=["project"]` 自动加载，定义 Agent 行为约束和 Skills 入口。

## 3. Execution Flow (LLM Retrieval Map)

- **1. 配置加载:** `src/config.py` 在进程启动时读取 `persona.md` 文本内容，存入 `PERSONA` 常量。
- **2. SDK 初始化:** `src/main.py:60-74` 构造 `ClaudeAgentOptions`，设置 `system_prompt=SystemPromptPreset(append=PERSONA + HEADLESS_RULES)`，`disallowed_tools=["AskUserQuestion", "ExitPlanMode", "EnterPlanMode"]`，`setting_sources=["user", "project"]`，`permission_mode="bypassPermissions"`，`can_use_tool=permission_gate`。options 传入 `ClientPool(options)`，pool 为每个 session 惰性创建 client。
- **3. CLAUDE.md 加载:** Claude SDK 启动时自动扫描 `cwd`（即 `tripo-work-center`）下的 `.claude/` 目录，将 `CLAUDE.md` 作为项目级指令注入会话。
- **4. 人格注入:** `persona.md` 的文本通过 `append` 模式追加到 system prompt——与 `CLAUDE.md` 注入的差异在于：`CLAUDE.md` 是默认加载的项目配置，`persona.md` 是人格层追加。
- **5. 消息处理:** `src/handler.py:53-61` 在 prompt 中添加 `[所有者]` 或 `[同事]` 标签，从 `pool.get(session_id)` 获取独立 client 后发送给 SDK。
- **6. 边界规则执行:** 分为两层——prompt 层（`persona.md` 中的能力边界通过人格描述约束 LLM 行为）和代码层（`src/permissions.py:permission_gate` 在每次 Bash 工具调用前拦截非所有者的敏感命令）。

## 4. 关键设计决策

### 4.1 Append 模式 vs 替换模式

`SystemPromptPreset(append=PERSONA)` 表示人格文本追加而非覆盖。这意味着 Claude Code 的默认行为（如技能调用、工具使用规范）完整保留，人格定义仅在其上添加行为约束和身份信息。

| 模式 | 效果 | 适用场景 |
|------|------|----------|
| 替换（无 append） | 丢弃 Claude Code 默认提示 | 完全自定义 Agent |
| 追加（append） | 保留默认提示，补充人格规则 | 数字分身（需要保留 SDK 能力） |

### 4.2 CLAUDE.md、persona.md 与 HEADLESS_RULES 的分工

| 文件 | 作用层级 | 内容类型 |
|------|----------|----------|
| `CLAUDE.md` | SDK 自动加载（project 配置） | 行为约束、Skills 入口、铁律 |
| `persona.md` | 通过 `append` 注入 | 身份认同、语气风格、能力边界 |
| `HEADLESS_RULES` | 通过 `append` 拼接（`src/config.py`） | 运行环境约束（禁止交互式工具） |

三者共同构成完整的 Agent 行为规范：`CLAUDE.md` 定义"Agent 能做什么"，`persona.md` 定义"Agent 以什么身份和风格做"，`HEADLESS_RULES` 定义"Agent 在什么环境下运行"。`HEADLESS_RULES` 独立于 `persona.md`，确保人格文件保持纯粹的人物设定，不混入运行时技术约束。

### 4.3 边界规则的执行方式

**Prompt 层（软约束）：** `persona.md` 中"你不做"部分以自然语言描述边界，依赖 LLM 理解并遵守。例如 LLM 会拒绝 merge PR，因为人格描述中写了"只能创建和查看，不能 merge"。

**代码层（硬约束）：** `src/permissions.py` 的 `permission_gate` 是强制执行点——它对非所有者触发的 Bash 命令进行关键词匹配（`deploy`、`git push`、`git merge`、`git reset`、`rm -rf`、`drop`），一旦命中立即返回 `PermissionResultDeny`。LLM 收到拒绝后无法绕过。

两者关系：Prompt 层约束 LLM 的决策倾向，代码层兜底防止越权操作。

### 4.4 权限分级

- **所有者（`owner_open_id`）**：通过 `config.json` 配置，全操作权限，`permission_gate` 放行。
- **其他同事**：非敏感查询允许，敏感 Bash 命令被 `permission_gate` 拒绝，LLM 层面感知到发送者身份为 `[同事]`，自动采用更保守的交互策略。

## 5. 迭代方向

### 5.1 人格调优

- **反馈循环：** 收集群聊中的实际回复样本，评估是否符合预期语气（专业简洁 vs 过于冗长）。
- **边界细化：** 根据误触场景补充"能力边界"条目（如发现 LLM 误回非职责问题，补充拒绝规则）。
- **OKR 动态更新：** `persona.md` 中的 OKR 随季度变化，需人工维护更新。

### 5.2 动态 OKR

当前 `persona.md` 的 OKR 是静态文本，存在以下问题：
- 季度切换时需手动修改文件。
- LLM 无法感知项目实际进度。

潜在改进方向：
- `src/config.py` 支持从外部数据源（飞书文档、多维表格）读取最新 OKR，动态注入。
- 将 OKR 分解为可量化的子目标，在 prompt 中以结构化数据呈现。
