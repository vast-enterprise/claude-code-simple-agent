# 步骤 8：提交发车/Hotfix 候选

> **重要**：本步骤**只负责把 bug 推到「发车候选」状态**,**不负责真正发车上线**。
> 发车是独立流程,由用户/scrum-master 在合适时机统一编排 → 见 **tripo-release**。

## 前置条件

- 步骤 7 完成：用户验收通过
- Bug 表进度 = Resolved

## 做什么

### 8.1 确认准出路径

根据 Bug 优先级提议,AskUserQuestion 确认：

- **P0 / 紧急线上 bug** → Hotfix 通道(单独发车)
- **P1 / 可等下一班车** → 跟车
- **P2 / 低优可合并发车** → 跟车或排队

**不替用户决策**,默认 P0 也要问一次(有些 bug 其实可以跟车)。

### 8.2 入候选队列(lark-cli 操作,option_id → tripo-tables/references/release-flow.md)

| 路径 | 表 | 写入 |
|------|-----|------|
| Hotfix | Hotfix 管理 → upsert 记录;发车中需求 → upsert,状态=**上线中**,`上线类型=hotfix` | 关联原 Bug 记录 |
| 跟车 | 发车中需求 → upsert,状态=**待上线**,关联当前跟车 Sprint 版本 | — |

同步：

- Bug 表进度：Resolved(保持,**不改 Closed**,等真正上线后再改)
- 需求池(如该 bug 挂了需求):需求状态保持 **验收/提测中**

### 8.3 更新任务目录

1. STATUS.md：标注「已提交发车/Hotfix 候选,等待 scrum-master 统一发车」(→ tripo-task-dirs)
2. **不归档**——任务目录等真正上线后再归档
3. **不清理 worktree**——万一发车前发现还要改,worktree 还得用

### 8.4 通知(可选)

- 跟车场景:按 tripo-notify 节点,在发车群简短同步
- Hotfix 场景:显著通知报告人 + 发车群,以免被遗漏

## 不做什么

- ❌ **不调用 tripo-release 发 production**
- ❌ **不 tag、不触发 workflow、不勾部署 checkbox**
- ❌ **不把 Bug 表进度改为 Closed**(那是真正上线后的状态)
- ❌ **不归档任务目录、不清理 worktree**

## 如何定义完成

- [ ] 发车中需求/Hotfix 管理表已有本 Bug 的记录,状态=待上线/上线中
- [ ] Bug 表进度 = Resolved(未变 Closed)
- [ ] STATUS.md 标注「已提交发车候选」
- [ ] 任务目录**未归档**,worktree **未清理**

## 本步骤结束后的状态

| 表格 | 状态字段 | 值 |
|------|---------|-----|
| Bug 管理 | 进度 | Resolved |
| 发车中需求 | 状态 | 待上线(跟车)/ 上线中(Hotfix) |
| Hotfix 管理 | — | 已创建(如走 Hotfix) |

Bug 表进度 → Closed / 任务目录归档 / worktree 清理 发生在**发车流程结束**后(→ tripo-release Step 11-13,由 scrum-master 或用户推进收尾)。
