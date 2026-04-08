---
name: tripo-requirement
description: |
  Tripo 需求开发流程管理。执行完整的需求开发流程：录入、评审、开发、PR、上线。

  触发条件：
  - `/tripo-requirement` 或"开发需求"、"做需求"、"帮我实现"
  - 用户提供需求描述、PRD 文档、飞书链接或需求 ID
---

# Tripo 需求开发流程

## 如何确定起始步骤

每个步骤声明了**前置条件**和**完成标准**。从步骤 1 开始扫描，找到第一个"前置条件已满足、完成标准未满足"的步骤，从该步骤开始执行。

## 流程概览

```
1.接收 → 2.录入 → 3.评审 → 4.执行 → 5.技评 → 6.开发 → 7.PR → 8.闭环 → 9.验收 → 10.上线
   │         │         │         │         │         │        │        │        │
 创建目录   入需求池   输出文档   执行表    技术方案  worktree  创建PR   自动验证  客户验收  发布
                      🔔通知              🔔通知                       🔔通知    🔔通知
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
| 10 | 发布上线 | [steps/10-release.md](references/steps/10-release.md) |

## 状态同步规则

**原则**: 提议 + 确认

```
📋 状态变更提议
需求: <描述>
建议: <字段> "<原值>" → "<新值>"
确认？
```

## 飞书通知阻塞点

流程中有 4 个阻塞点，通知后必须暂停等待用户确认（→ tripo-tables，notification.md）：

| 步骤 | 触发时机 |
|------|---------|
| 3 | review.md 输出后 |
| 5 | technical-solution.md 输出后 |
| 8 | Review + 测试通过后 |
| 10 | 用户验收通过后 |

## 异常处理

- **需求变更**: 暂停 → 更新描述 → 重新定容
- **开发阻塞**: 标记"风险" → 飞书通知 Owner
- **开发超期**: 更新预期时间 → 飞书通知 Owner

## 相关文档

- `tripo-tables` skill - 表格结构、字段 ID、状态选项、发车流程
- `tripo-repos` skill - 代码仓库注册表（路径、技术栈、部署信息）
- `tripo-task-dirs` skill - 任务目录管理、状态跟踪、归档
- [references/commands.md](references/commands.md) - 命令速查