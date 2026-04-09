# Skill 集成架构

## 1. Identity

- **What it is:** Skill 体系与 Agent 系统（CLI 会话 + 数字分身）的集成机制。
- **Purpose:** 描述 skill 如何被加载、发现、路由和执行，以及在数字分身场景下的复用方式与限制。

## 2. Core Components

- `CLAUDE.md` (`Skills 目录`): 项目级指令文件，声明 7 个 skill 的名称与用途，是 Claude Code 发现 skill 的入口索引。
- `.claude/skills/*/SKILL.md` (各 skill 的 `name`, `description`, 触发条件): 每个 skill 的元数据与流程定义，Claude Code 通过 frontmatter 中的 `description` 字段理解 skill 的适用场景。
- `src/main.py:37-47` (`ClaudeAgentOptions`): 数字分身初始化 SDK 客户端时的关键配置，`setting_sources=["project"]` 和 `cwd=ROOT` 决定了 skill 加载行为。
- `src/config.py` (`ROOT`): 解析项目根目录路径，作为 `cwd` 传入 SDK，使 skill 发现路径锚定到 `tripo-work-center`。

## 3. Execution Flow (LLM Retrieval Map)

### 3.1 Skill 加载机制

- **1. SDK 初始化:** `src/main.py:44` 设置 `setting_sources=["project"]`，指示 Claude Code 仅从项目级配置加载（不加载全局 `~/.claude/` 下的 skill）。
- **2. cwd 锚定:** `src/main.py:38` 设置 `cwd=str(ROOT)`，ROOT 指向 `tripo-work-center` 项目根目录。
- **3. 自动发现:** Claude Code 根据 cwd 读取 `CLAUDE.md`（项目指令）和 `.claude/skills/` 目录下所有 `SKILL.md` 文件。
- **4. 结果:** 6 个已实现的 skill（tripo-requirement、tripo-tables、tripo-repos、tripo-worktree、tripo-task-dirs、tripo-release）被注入会话上下文。

### 3.2 数字分身复用 Skill 体系

- **1. 同一 cwd:** 数字分身的 `ClaudeSDKClient` 与 CLI 会话使用相同的 `cwd`（`tripo-work-center`），因此自动发现相同的 skill 集合。
- **2. 同一 CLAUDE.md:** 行为约束（提议+确认、禁止 merge、通知后阻塞等）对数字分身同样生效，因为它们定义在项目级 `CLAUDE.md` 中。
- **3. 零额外配置:** 不需要为数字分身单独注册或复制 skill 文件，`setting_sources=["project"]` + `cwd` 即完成全部 skill 注入。

### 3.3 Skill 路由（Claude 自主选择）

Skill 路由完全由 Claude 的推理能力驱动，无硬编码路由表：

- **1. 用户消息到达:** CLI 输入或飞书消息经 `handle_message` 组装为 prompt。
- **2. 上下文匹配:** Claude 根据 prompt 内容与每个 `SKILL.md` 的 `description`/触发条件进行语义匹配。
- **3. Skill 选择:** Claude 自主决定调用哪个 skill（或不调用任何 skill）。例如"部署 staging"匹配 `tripo-release`，"做需求"匹配 `tripo-requirement`。
- **4. 子 skill 调用:** 主 skill（如 `tripo-requirement`）在流程步骤中通过文档引用指向子 skill（如步骤 6 引用 `tripo-repos` 和 `tripo-worktree`），Claude 按引用链自主跳转。

### 3.4 Skill 与 Bash 工具的关系

Skill 本身是纯 Markdown 文档，不含可执行代码。实际操作通过 Bash 工具调用外部 CLI 完成：

- **飞书操作:** Skill 文档中定义 `lark-cli` 命令模板（如 `.claude/skills/tripo-tables/references/notification.md`），Claude 读取模板后通过 Bash 工具执行。
- **Git 操作:** `tripo-worktree` 定义 worktree 命令规范，Claude 通过 Bash 执行 `git worktree add/remove`。
- **部署操作:** `tripo-release` 定义 GitHub Actions 触发命令，Claude 通过 Bash 执行 `gh workflow run`。
- **权限拦截:** 数字分身场景下，所有 Bash 调用经过 `src/permissions.py:permission_gate` 回调，非所有者的敏感命令被拦截。

## 4. Design Rationale

**为什么 skill 是纯 Markdown 而非代码？**
Skill 作为 Claude Code 的上下文注入，本质是"结构化 prompt"。纯 Markdown 格式使非开发者也能编写和维护流程定义，同时 Claude 的推理能力负责将文档指令转化为工具调用序列。

**扩展方式：** 新增 skill 只需在 `.claude/skills/` 下创建目录和 `SKILL.md`，无需修改任何代码。Claude Code 下次启动时自动发现。`CLAUDE.md` 的 Skills 目录表建议同步更新，但非强制。

**数字分身场景的限制：**
- Skill 无法主动触发——必须等待用户消息到达后，由 Claude 推理决定是否调用。
- 路由准确性完全依赖 Claude 的语义理解，无 fallback 机制；模糊消息可能导致错误路由或不路由。
- `setting_sources=["project"]` 排除了全局 skill（如 `~/.claude/skills/` 下的 lark-*、seo-* 等），数字分身无法使用这些 skill。
