# Tripo Agent 工作调度中枢

> 本文档为 Agent 在 Tripo 工作时提供必要的上下文索引。
> 具体流程操作由项目级 skills 维护。

## Tripo 概览

- **定位**：业务线/产品线
- **工作目录性质**：纯调度中枢（代码仓库在其他位置）

## Agent 职责边界

### ✅ 核心职责

| 职责 | 说明 |
|------|------|
| 技术实现 | 代码编写、重构、bug修复等 |
| 协作工具维护 | 飞书多维表格、文档、群组操作 |
| 规划评审 | 需求分析、技术评审、方案设计 |
| 沟通通知 | 飞书消息通知、状态同步 |

### 🔒 行为约束

| 约束 | 规则 |
|------|------|
| 状态变更 | **提议 + 确认**：Agent 先提议，用户确认后再执行 |
| PR 提交 | 可 commit、可 push，**禁止 merge** |
| 开发闭环 | 以 PR 提出为闭环，不擅自合并 |

## 核心文档

| 文档 | 说明 |
|------|------|
| [TABLES.md](TABLES.md) | 多维表格结构（产品需求池、技术需求池、执行中需求） |
| [REPOSITORIES.md](REPOSITORIES.md) | 代码仓库信息 |
| [TASK-TRACKING.md](TASK-TRACKING.md) | 任务进度跟踪规范 |

## Skills 目录

| Skill | 触发场景 |
|-------|---------|
| `tripo-requirement` | 需求开发任务（录入、评审、开发、PR、上线） |
| `tripo-bugfix` | Bug 修复任务（待创建） |

## 快速参考

### 表格速查

| 表格 | Base Token | Table ID |
|------|------------|----------|
| 产品需求池 | `HMvbbjDHOaHyc6sZny6cMRT8n8b` | `tblb9E9PQHP79JHE` |
| 技术需求池 | `OCNcbuwpta7qc7sxAPOcSpngnbg` | `tblkb1Saexm0njaE` |
| 执行中需求 | `HMvbbjDHOaHyc6sZny6cMRT8n8b` | `tblxLMQ8Ih5Gs5oM` |

### 代码仓库

| 仓库 | 本地路径 |
|------|---------|
| tripo-cms | `/Users/macbookair/Desktop/projects/tripo-cms` |
| fe-tripo-homepage | `/Users/macbookair/Desktop/projects/fe-tripo-homepage` |
| fe-tripo-tools | `/Users/macbookair/Desktop/projects/fe-tripo-tools` |