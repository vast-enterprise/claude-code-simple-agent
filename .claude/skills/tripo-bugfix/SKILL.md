---
name: tripo-bugfix
description: |
  Tripo 缺陷修复全流程：接收→录入→调查→修复→PR→闭环→验收→上线，8 步闭环。
  用户说"修 bug"/"有 bug"/"出问题了"/"不显示"/"报错"时触发本 skill。
  本 skill 是缺陷修复的流程编排层，tripo-repos/tripo-tables/tripo-worktree 等是执行层。

  触发条件（任一命中即触发）：
  - `/tripo-bugfix` 或"修 bug"、"有 bug"、"出问题了"、"fix"、"hotfix"
  - 用户转发同事的 bug 反馈消息
  - 关键词：bug、缺陷、修复、regression、不显示、报错、crash、样式问题

  消歧规则：当 bug 信息中涉及特定仓库（如"CMS 的 XX 有 bug"），
  本 skill 优先级高于 tripo-cms、tripo-repos 等执行层 skill。
  先走 bugfix 流程，步骤内按需加载仓库 skill。
---

# Tripo 缺陷修复流程

## 如何确定起始步骤

每个步骤声明了**前置条件**和**完成标准**。从步骤 1 开始扫描，找到第一个"前置条件已满足、完成标准未满足"的步骤，从该步骤开始执行。

> **⚠️ 步骤执行协议**：执行任何步骤前，**必须先 Read 对应的 detail 文件**（步骤详解表的"详情"列）。概览和说明列仅供导航定位，**不是执行依据**——detail 文件中的子步骤、前置条件、完成标志才是唯一执行标准。

## 流程概览

```
1.接收 → 2.录入 → 3.调查 → 4.修复 → 5.PR → 6.闭环 → 7.验收 → 8.上线
   │        │        │        │        │       │        │        │
 理解问题   Bug表    定位根因  worktree  创建PR  CR+测试   review   发车
                    报告+wiki                   🔔通知    合并
                    🔔通知
```

## Bug 状态流转

| 阶段 | Bug 表进度 |
|------|-----------|
| 录入 | Open |
| 调查中 | In progress |
| 修复完成 | In progress |
| PR 合并 | Resolved |
| 上线 | Closed |

## 步骤详解

| 步骤 | 说明 | 详情 |
|------|------|------|
| 1 | 接收 Bug | [steps/1-receive.md](references/steps/1-receive.md) |
| 2 | 录入 Bug 管理表 | [steps/2-record.md](references/steps/2-record.md) |
| 3 | 调查 & 定位根因 | [steps/3-investigate.md](references/steps/3-investigate.md) |
| 4 | 修复 | [steps/4-fix.md](references/steps/4-fix.md) |
| 5 | 创建 PR | [steps/5-pr.md](references/steps/5-pr.md) |
| 6 | 自动化闭环 | [steps/6-test.md](references/steps/6-test.md) |
| 7 | 用户验收 | [steps/7-acceptance.md](references/steps/7-acceptance.md) |
| 8 | 发布上线 | [steps/8-release.md](references/steps/8-release.md) |

## 状态同步规则

**原则**: 提议 + 确认

```
📋 Bug 状态变更提议
Bug: <描述>
建议: 进度 "<原值>" → "<新值>"
确认？
```

## 飞书通知阻塞点

流程中有 2 个阻塞点，通知后必须暂停等待用户确认：

| 步骤 | 触发时机 |
|------|---------|
| 3 | Bug 定位报告输出 + Wiki 同步后 |
| 6 | Code Review + 集成测试全部通过后 |

## 铁律（违反 = 3.25）

### 🔒 禁止未经确认操作生产环境
不连生产数据库、不 curl 生产 API、不在线上页面注入脚本。本地环境和 staging 环境可以自由使用。如确实需要访问生产环境，必须 AskUserQuestion 让所有者本人确认。

### 🔒 一个 bug 进，一个品类出
发现一处问题后，必须检查所有同类代码是否有相同问题。不能只修一处就收工。

### 🔒 全量验证
提出的每一个受影响项都必须有验证证据。不能只说"理论上有问题"而不去验证。

## 异常处理

- **根因不明**: 输出当前分析进展 → AskUserQuestion 请求更多信息
- **跨仓库 bug**: 各仓库独立 worktree（→ tripo-worktree），分别修复

## 相关 skill

- `tripo-notify` - 飞书主动通知（通知对象、渠道规则、节点模板）
- `tripo-tables` - Bug 管理表结构、字段 ID、状态选项
- `tripo-repos` - 代码仓库注册表
- `tripo-worktree` - worktree 生命周期管理
- `tripo-release` - 发版上线
- `tripo-test` - 验证方法论
