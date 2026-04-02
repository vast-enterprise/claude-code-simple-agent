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
1.接收 → 2.录入 → 3.评审 → 4.执行 → 5.技评 → 6.开发 → 7.PR → 8.测试 → 9.上线
   │         │         │         │         │         │        │        │
 创建目录   入需求池   输出文档   执行表    技术方案  worktree  PR审查   完成
```

## 双表联动

| 阶段 | 需求池状态 | 执行表状态 |
|------|-----------|-----------|
| 录入 | 未启动 | - |
| 定容 | 定容确认 | - |
| 开发 | 开发/交付中 | 研发中 |
| 测试 | 验收/提测中 | 测试中 |
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
| 7 | 提交 PR | [steps/7-pr.md](references/steps/7-pr.md) |
| 8 | 测试验收 | [steps/8-test.md](references/steps/8-test.md) |
| 9 | 发布上线 | [steps/9-release.md](references/steps/9-release.md) |

## 状态同步规则

**原则**: 提议 + 确认

```
📋 状态变更提议
需求: <描述>
建议: <字段> "<原值>" → "<新值>"
确认？
```

## 模板

| 模板 | 用途 |
|------|------|
| [templates/review.md](references/templates/review.md) | 需求评审文档 |
| [templates/technical-solution.md](references/templates/technical-solution.md) | 技术方案文档 |

## 异常处理

- **需求变更**: 暂停 → 更新描述 → 重新定容
- **开发阻塞**: 标记"风险" → 通知 Owner
- **开发超期**: 更新预期时间 → 通知 Owner

## 相关文档

- [TABLES.md](../../TABLES.md) - 表格结构
- [REPOSITORIES.md](../../REPOSITORIES.md) - 代码仓库
- [TASK-TRACKING.md](../../TASK-TRACKING.md) - 任务跟踪规范
- [references/commands.md](references/commands.md) - 命令速查