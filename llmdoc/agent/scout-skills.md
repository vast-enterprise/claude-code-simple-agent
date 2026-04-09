<!-- This entire block is your raw intelligence report for other agents. It is NOT a final document. -->

### Code Sections (The Evidence)

- `.claude/skills/tripo-requirement/SKILL.md` (tripo-requirement): 需求开发全流程 skill，定义 10 步流程（接收→录入→评审→执行→技评→开发→PR→闭环→验收→上线），包含双表联动规则和 4 个飞书通知阻塞点。
- `.claude/skills/tripo-requirement/references/steps/1-receive.md` (步骤1): 接收需求并创建任务目录，解析输入来源（文字/文件/飞书链接/需求ID），调用 tripo-task-dirs。
- `.claude/skills/tripo-requirement/references/steps/2-record.md` (步骤2): 判断需求类型（产品/技术），录入对应需求池，更新任务目录。
- `.claude/skills/tripo-requirement/references/steps/3-review.md` (步骤3): 输出 review.md，含合规风险审查，提议状态→"定容确认"，发飞书通知后阻塞等待用户确认。
- `.claude/skills/tripo-requirement/references/steps/4-enter-execution.md` (步骤4): 在执行中需求表创建记录（状态=评审中），更新需求池状态→"开发/交付中"。
- `.claude/skills/tripo-requirement/references/steps/5-tech-review.md` (步骤5): 输出 technical-solution.md，发飞书通知后阻塞，提议"技术评审"="完成"，更新计划提测时间。
- `.claude/skills/tripo-requirement/references/steps/6-develop.md` (步骤6): 进入代码仓库，创建 worktree，读 llmdoc，编码+测试，实时更新 STATUS.md，按需更新 llmdoc。
- `.claude/skills/tripo-requirement/references/steps/7-pr.md` (步骤7): 提交代码，创建 PR（关联需求ID和任务目录），更新 STATUS.md，创建后直接进入步骤8不通知用户。
- `.claude/skills/tripo-requirement/references/steps/8-test.md` (步骤8): 自动化闭环，5个子步骤顺序执行：Code Review → 测试计划 → 集成测试 → 验证报告 → 飞书通知阻塞。
- `.claude/skills/tripo-requirement/references/steps/9-acceptance.md` (步骤9): 等待用户 Review PR，合并后同步主工作区 main，配合验收测试。
- `.claude/skills/tripo-requirement/references/steps/10-release.md` (步骤10): 需求准出+搭车，调用 tripo-release production 模式部署，收尾归档。
- `.claude/skills/tripo-requirement/references/commands.md` (命令速查): lark-cli 录入/查询/更新需求的命令模板，worktree 和 PR 操作命令。
- `.claude/skills/tripo-repos/SKILL.md` (tripo-repos): 仓库注册表，记录 3 个仓库（tripo-cms、fe-tripo-homepage、fe-tripo-tools）的本地路径、远程地址、技术栈、部署信息和仓库间依赖关系。
- `.claude/skills/tripo-tables/SKILL.md` (tripo-tables): 飞书多维表格全操作，定义 2 个 Base（需求一览表/技术需求一览表）、8 张数据表的 Table ID、状态流转、发车流程和通知模板入口。
- `.claude/skills/tripo-tables/references/field-mapping.md` (字段映射): 产品需求池、执行中需求、技术需求三张表的字段名/类型/状态值对照。
- `.claude/skills/tripo-tables/references/fields-product-pool.md` (产品需求池字段): 产品需求池完整字段结构，含 Field ID、类型、状态选项（未启动/定容确认/开发交付中/验收提测中/已完成/暂停）和需求池分类选项。
- `.claude/skills/tripo-tables/references/fields-execution.md` (执行中需求字段): 执行中需求完整字段结构，含 10 个阶段进度字段（需求评审/技术评审/前端开发/后端开发等）及其 Field ID。
- `.claude/skills/tripo-tables/references/notification.md` (通知模板): 4 个通知节点的完整 lark-cli 命令模板，通知对象 open_id 固定为 `ou_8adc8aca7ad728142eb6669e5b13fb52`，强制使用 `--as bot`。
- `.claude/skills/tripo-tables/references/release-flow.md` (发车流程): 3 条上线路径（跟车/SSS/hotfix）的 Workflow ID、option_id 速查表、lark-cli 操作指南和部署 checkbox 字段 ID。
- `.claude/skills/tripo-worktree/SKILL.md` (tripo-worktree): worktree 全生命周期管理，定义命名规范（feature/REQ-recXxx-ascii-desc）、使用纪律、扫描/分类/清理流程和安全规则。
- `.claude/skills/tripo-release/SKILL.md` (tripo-release): 前端发版编排，两种模式路由（staging/production），tag 命名规范（v{YYYY}.{MM}.{DD}），引用 tripo-tables 和 tripo-repos 数据。
- `.claude/skills/tripo-release/references/deploy-staging.md` (staging部署): 轻量模式，4步：确认 workflow → 触发部署 → 等待完成 → 验证 HTTP 200。
- `.claude/skills/tripo-release/references/deploy-production.md` (production部署): 完整模式，6步：确认班车 → 创建 release/tag → 触发部署 → 验证 → 勾 checkbox → 通知。
- `.claude/skills/tripo-task-dirs/SKILL.md` (tripo-task-dirs): 任务目录生命周期管理，定义目录命名规范（{日期}_{类型}-{ID}_{简述}）、STATUS.md 更新规则、归档操作。
- `.claude/skills/tripo-task-dirs/assets/STATUS.template.md` (STATUS模板): STATUS.md 的标准模板，含基本信息表、状态历史表、当前状态、关联资源和备注区。
- `CLAUDE.md` (项目根配置): 定义项目定位（纯调度中枢）、Agent 核心职责（技术实现/协作工具维护/规划评审/沟通通知）、行为约束规则和 skills 目录索引。

---

### Report (The Answers)

#### result

**项目定位**

- `tripo-work-center` 定位为"业务线/产品线调度中枢"，本身不存放业务代码，代码仓库在其他位置（由 `tripo-repos` skill 管理）。
- 工作目录性质：纯调度，通过 skills 编排跨仓库、跨工具（飞书/GitHub）的完整研发流程。

**Agent 核心职责（4类）**

| 职责 | 说明 |
|------|------|
| 技术实现 | 代码编写、重构、bug修复 |
| 协作工具维护 | 飞书多维表格、文档、群组操作 |
| 规划评审 | 需求分析、技术评审、方案设计 |
| 沟通通知 | 飞书消息通知、状态同步 |

**行为约束规则（5条）**

1. 状态变更：提议 + 确认，Agent 先提议，用户确认后再执行。
2. PR 提交：可 commit、可 push，禁止 merge。
3. 开发闭环：以 PR 提出为闭环，不擅自合并。
4. 飞书通知后阻塞：必须用 `AskUserQuestion` 等待确认，不可脑补用户已确认。
5. lark-cli 发消息：必须用 `--as bot`，通知场景禁止用默认 user 身份。

**进入代码仓库的铁律（3条）**

1. 先读 llmdoc：进入任何仓库后，第一步必须读取 `llmdoc/index.md` + `llmdoc/overview/` 下所有文档。
2. Worktree 纪律：所有代码修改必须在 worktree 目录内进行，禁止在主分支上 mkdir/write/edit。
3. TDD：先写测试再写代码，提交前必须跑测试贴证据。

**可用 Skills（6个，含1个待创建）**

| Skill | 触发条件 | 核心功能 |
|-------|---------|---------|
| `tripo-requirement` | "开发需求"、"做需求"、"帮我实现" | 需求开发全流程（10步） |
| `tripo-tables` | 查表格、查需求、录入、更新状态、发车 | 飞书多维表格全操作 |
| `tripo-repos` | 查仓库路径、技术栈、部署信息 | 仓库注册表（3个仓库） |
| `tripo-worktree` | 创建/清理 worktree | worktree 全生命周期管理 |
| `tripo-task-dirs` | 创建任务目录、更新状态、归档 | tasks/ 目录生命周期管理 |
| `tripo-release` | "部署 staging"、"上线"、"发车" | 前端发版编排（staging/production） |
| `tripo-bugfix` | （待创建） | Bug 修复流程 |

**tripo-requirement 10步流程**

```
1.接收 → 2.录入 → 3.评审🔔 → 4.执行 → 5.技评🔔 → 6.开发 → 7.PR → 8.闭环🔔 → 9.验收 → 10.上线🔔
```

4 个飞书通知阻塞点：步骤3（评审完成）、步骤5（技评完成）、步骤8（集成测试通过）、步骤10（验收通过准备上线）。

**tripo-tables 数据结构**

- 2 个 Base：Tripo 需求一览表（`HMvbbjDHOaHyc6sZny6cMRT8n8b`）、技术需求一览表（`OCNcbuwpta7qc7sxAPOcSpngnbg`）。
- 核心数据表：产品需求池（`tblb9E9PQHP79JHE`）、执行中需求（`tblxLMQ8Ih5Gs5oM`）、发车中需求（`tblPlaxVsLBvKMRl`）、Sprint 版本计划（`tblm2FGJjiK4frzt`）。
- 上线三条路径：跟车（`wkfCTuzpHvY4FghE`）、SSS 临时发车（`wkfufcEDGQeXQfTF`）、Hotfix（`wkf1daTXkGSUjGLY`）。

**tripo-repos 仓库注册表**

| 仓库 | 本地路径 | 技术栈 |
|------|---------|--------|
| tripo-cms | `/Users/macbookair/Desktop/projects/tripo-cms` | Payload CMS 3.x + Next.js 15 + MongoDB |
| fe-tripo-homepage | `/Users/macbookair/Desktop/projects/fe-tripo-homepage` | Nuxt 4 + Vue 3 + Three.js |
| fe-tripo-tools | `/Users/macbookair/Desktop/projects/fe-tripo-tools` | pnpm monorepo + TypeScript |

**tripo-release 发版规则**

- staging 模式：轻量，4步，不涉及发车流程。
- production 模式：完整，6步，需关联班车，创建 tag（格式 `v{YYYY}.{MM}.{DD}`），勾 checkbox，通知。
- 前置条件：PR 已合入 main，本地 main 已 pull 到最新。

---

#### conclusions

- `tripo-work-center` 本身不含业务代码，是一个纯粹的 Agent 调度中枢，通过 `.claude/skills/` 下的 skill 文件编排跨仓库研发流程。
- 所有 skills 存放在项目本地 `.claude/skills/` 目录，而非全局 `~/.claude/skills/`（全局目录存放的是 lark-* 和 seo-* 等通用 skills）。
- `tripo-requirement` 是主流程 skill，其他 5 个 skill（tripo-tables、tripo-repos、tripo-worktree、tripo-task-dirs、tripo-release）均作为子模块被其调用。
- 飞书通知机制是流程控制的核心手段，4 个阻塞点强制 Agent 在关键决策节点等待人工确认，防止自动越权。
- `tripo-bugfix` skill 在 CLAUDE.md 中已列出但标注"待创建"，当前不存在对应的 SKILL.md 文件。
- worktree 纪律是跨仓库操作的核心约束：每个仓库独立 worktree，所有 Write/Edit 操作必须指向 worktree 路径，Bash 命令必须使用绝对路径。
- lark-cli 是飞书操作的唯一工具，通知场景强制 `--as bot`，表格操作通过 `base +record-*` 子命令完成。
- 发车流程有 9 个 Workflow ID，通过 lark-cli 直接操作等效于飞书表格上的按钮触发。

---

#### relations

- `CLAUDE.md` 是入口配置，定义项目定位和 skills 目录索引，所有 skill 从此处被引用。
- `tripo-requirement` 在步骤6调用 `tripo-repos`（获取仓库路径）、`tripo-worktree`（创建 worktree）、`tripo-task-dirs`（更新 STATUS.md）；在步骤3/5/8/10调用 `tripo-tables`（通知模板）；在步骤10调用 `tripo-release`（production 部署）。
- `tripo-worktree` 调用 `tripo-repos` 获取仓库路径，不硬编码。
- `tripo-release` 引用 `tripo-repos`（获取 GitHub Action 文件名、域名）和 `tripo-tables`（发车流程、checkbox 字段 ID、通知模板）。
- `tripo-tables` 的 `notification.md` 被 `tripo-requirement` 步骤3/5/8/10 和 `tripo-release` 的 deploy-production.md 共同引用。
- `tripo-tables` 的 `release-flow.md` 被 `tripo-requirement` 步骤10 和 `tripo-release` 的 deploy-production.md 共同引用。
- `tripo-task-dirs` 被 `tripo-requirement` 的每个步骤调用，用于维护 `tasks/` 目录下的 STATUS.md。
- 产品需求池 → 执行中需求 → 发车中需求 是三张表的数据流向，Sprint 版本计划作为版本容器被发车中需求关联。
