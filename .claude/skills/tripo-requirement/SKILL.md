---
name: tripo-requirement
description: |
  **最高优先级流程 skill**：用户说"做需求"/"开发需求"/"帮我实现"时，必须首先触发本 skill，
  即使需求涉及特定仓库（如 CMS、前端），也应先走本流程再在步骤内加载对应仓库 skill。
  本 skill 是流程编排层，tripo-cms/tripo-repos 等是执行层——编排先于执行。

  Tripo 需求开发全流程管理：接收→录入→评审→开发→PR→闭环→验收→提交发车候选,10 步闭环。
  **本 skill 终点是「提交发车候选」,不包含真正发车上线**；发车是独立流程（→ tripo-release）,由用户/scrum-master 显式触发。

  触发条件（任一命中即触发）：
  - `/tripo-requirement` 或"做需求"、"开发需求"、"帮我实现"、"新需求"
  - 用户提供需求描述、PRD 文档、飞书链接或需求 ID
  - 需求状态流转：PR 合并、验收通过、更新执行表/需求池状态、提交发车候选
  - 关键词："合并了"、"merged"、"自测通过"、"验收"、"提测"、"准出"、"发车候选"
  - 评估需求进度、查看需求状态
  - **不自动触发**：只说"发车"、"上线"、"部署 production"——走 tripo-release,不重启本流程

  消歧规则：当"做需求"与其他 skill 触发词同时出现（如"做需求，关于 CMS 的 XX"），
  本 skill 优先级高于 tripo-cms、tripo-repos 等执行层 skill。
---

# Tripo 需求开发流程

## 如何确定起始步骤

每个步骤声明了**前置条件**和**完成标准**。从步骤 1 开始扫描，找到第一个"前置条件已满足、完成标准未满足"的步骤，从该步骤开始执行。

> **⚠️ 步骤执行协议**：执行任何步骤前，**必须先 Read 对应的 detail 文件**（步骤详解表的"详情"列）。概览和说明列仅供导航定位，**不是执行依据**——detail 文件中的子步骤、前置条件、完成标志才是唯一执行标准。

## 流程概览

```
1.接收 → 2.录入 → 3.评审 → 4.执行 → 5.技评 → 6.开发 → 7.PR → 8.闭环 → 9.验收 → 10.提交发车候选
   │         │         │         │         │         │        │        │        │         │
 创建目录   入需求池   输出文档   执行表    技术方案  worktree  创建PR   自动验证  客户验收  入发车队列
                      🔔通知              🔔通知                       🔔通知    🔔通知
                                                                                        ↓
                                                             发车流程独立（→ tripo-release,用户显式触发）
```

## 双表联动

| 阶段 | 需求池状态 | 执行表状态 |
|------|-----------|-----------|
| 录入 | 未启动 | - |
| 定容 | 定容确认 | - |
| 开发 | 开发/交付中 | 研发中 |
| 提测 | 验收/提测中 | 测试中 |
| 完成 | 已完成 | 完成 |

## 步骤详解

| 步骤 | 说明 | 详情 |
|------|------|------|
| 1 | 接收需求 & 创建目录 | [steps/1-receive.md](references/steps/1-receive.md) |
| 2 | 归类与录入 | [steps/2-record.md](references/steps/2-record.md) |
| 3 | 需求评审 | [steps/3-review.md](references/steps/3-review.md) |
| 4 | 进入执行表 | [steps/4-enter-execution.md](references/steps/4-enter-execution.md) |
| 5 | 技术评审 | [steps/5-tech-review.md](references/steps/5-tech-review.md) |
| 6 | 编码开发 | [steps/6-develop.md](references/steps/6-develop.md) |
| 7 | 创建 PR | [steps/7-pr.md](references/steps/7-pr.md) |
| 8 | 自动化闭环 | [steps/8-test.md](references/steps/8-test.md) |
| 9 | 用户验收 | [steps/9-acceptance.md](references/steps/9-acceptance.md) |
| 10 | 提交发车候选（**不发车**） | [steps/10-release.md](references/steps/10-release.md) |

## 状态同步规则

**原则**: 提议 + 确认

```
📋 状态变更提议
需求: <描述>
建议: <字段> "<原值>" → "<新值>"
确认？
```

## 飞书通知阻塞点

流程中有 4 个阻塞点，通知后必须暂停等待用户确认（→ tripo-notify）：

| 步骤 | 触发时机 |
|------|---------|
| 3 | review.md 输出后 |
| 5 | technical-solution.md 输出后 |
| 8 | Review + 测试通过后 |
| 10 | 用户验收通过 → 发车候选入队后 |

## 异常处理

- **需求变更**: 暂停 → 更新描述 → 重新定容
- **开发阻塞**: 标记"风险" → 飞书通知 Owner
- **开发超期**: 更新预期时间 → 飞书通知 Owner

## 相关文档

### 流程支撑 skill（资源层）
- `tripo-notify` skill - 飞书主动通知（通知对象、渠道规则、节点模板）
- `tripo-tables` skill - 表格结构、字段 ID、状态选项、发车相关数据字典
- `tripo-repos` skill - 代码仓库注册表（路径、技术栈、部署信息）
- `tripo-task-dirs` skill - 任务目录管理、状态跟踪、归档
- `tripo-release` skill - **独立的发车上线流程**（13 步编排）,本 skill 只到「提交发车候选」,不调用 release 的发车编排

### 方法论 skill（步骤内加载）
- `tripo-dev` skill - 编码方法论（步骤 6 加载）：先理解再编码、运行时验证、完成 Checklist
- `tripo-test` skill - 测试方法论（步骤 8 加载）：工具-证据映射、证据先贴结论、计划先于执行
- `tripo-diagnose` skill - 诊断方法论（异常处理时加载）：优先级阶梯、环境边界、失败回退

### 参考
- [references/commands.md](references/commands.md) - 命令速查