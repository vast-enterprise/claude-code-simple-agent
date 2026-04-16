# 步骤 8：发布上线

## 前置条件

- 步骤 7 完成：用户验收通过
- Bug 表进度 = Resolved

## 做什么

### 8.1 确认发车路径

根据 Bug 优先级决定：
- **P0**：走 Hotfix 流程（→ tripo-release，hotfix 模式）
- **P1**：跟随最近的 Sprint 发车（→ tripo-release）
- **P2**：跟随下一个 Sprint 发车

### 8.2 部署

调用 `tripo-release` skill 对应模式完成部署。

### 8.3 收尾

1. **更新 Bug 表**（→ tripo-tables）：
   - 进度：Resolved → Closed
   - 备注：追加 PR 链接和上线版本

2. **通知报告人**：如果 bug 是同事报告的，通知对方已上线

3. **更新 STATUS.md**（→ tripo-task-dirs）：状态标记为 ✅ 已完成

4. **归档任务目录**（→ tripo-task-dirs）

5. **清理 worktree**（→ tripo-worktree）

## 如何定义完成

- [ ] 代码已部署到目标环境
- [ ] Bug 表进度 = Closed
- [ ] 报告人已通知
- [ ] STATUS.md 已更新为完成状态
- [ ] 任务目录已归档
- [ ] worktree 已清理
