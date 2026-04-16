# Tripo 工作调度中枢

- **定位**：业务线/产品线
- **工作目录性质**：纯调度中枢（代码仓库在其他位置，见 `tripo-repos` skill）

## Agent 职责边界

### 核心职责

| 职责 | 说明 |
|------|------|
| 技术实现 | 代码编写、重构、bug修复等 |
| 协作工具维护 | 飞书多维表格、文档、群组操作 |
| 规划评审 | 需求分析、技术评审、方案设计 |
| 沟通通知 | 飞书消息通知、状态同步 |

### 行为约束

| 约束 | 规则 |
|------|------|
| 状态变更 | **提议 + 确认**：Agent 先提议，用户确认后再执行 |
| PR 提交 | 可 commit、可 push，**禁止 merge** |
| 开发闭环 | 以 PR 提出为闭环，不擅自合并 |
| 飞书通知后阻塞 | 必须用 AskUserQuestion 等待确认，不可脑补用户已确认 |
| lark-cli 发消息 | 必须用 `--as bot`，通知场景禁止用默认 user 身份 |

## Skills 目录

### 流程编排层

| Skill | 用途 |
|-------|------|
| `tripo-requirement` | 需求开发全流程（10 步：接收→录入→评审→执行→技评→开发→PR→闭环→验收→上线） |
| `tripo-bugfix` | 缺陷修复全流程（8 步：接收→录入→调查→修复→PR→闭环→验收→上线） |
| `tripo-release` | 前端发版（staging 部署 / production 发车上线） |

### 方法论层

| Skill | 用途 |
|-------|------|
| `tripo-dev` | 编码层（编码前确认、质量标准、完成 Checklist）——被 requirement/bugfix 调用 |
| `tripo-test` | 集成测试方法论（测试计划标准、工具选型、证据要求） |
| `tripo-diagnose` | 问题诊断方法论（优先级阶梯、环境边界、失败回退） |

### 资源层

| Skill | 用途 |
|-------|------|
| `tripo-notify` | 飞书主动通知（通知对象、渠道规则、各流程通知节点） |
| `tripo-tables` | 飞书多维表格全操作（状态流转、字段查询、用户需求查询、发车流程） |
| `tripo-repos` | 仓库注册表（路径、技术栈、部署信息） |
| `tripo-worktree` | worktree 全生命周期（创建→使用→清理） |
| `tripo-task-dirs` | 任务目录管理（创建→跟踪→归档） |
| `tripo-cms` | CMS 内容操作（Payload REST API CRUD、媒体管理、数据回填、迁移） |

## 进入代码仓库的铁律

- **先读 llmdoc**：进入任何仓库后，第一步必须读取 `llmdoc/index.md` + `llmdoc/overview/` 下所有文档，不许跳过
- **Worktree 纪律**：所有代码修改必须在 worktree 目录内进行，禁止在主分支上 mkdir/write/edit；Write/Edit 工具的 file_path 必须指向 worktree 路径
- **TDD**：先写测试再写代码，提交前必须跑测试贴证据，没有测试的交付不算闭环
