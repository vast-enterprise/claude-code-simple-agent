# 步骤 7：用户验收

## 前置条件

- 步骤 6 已完成（自动化闭环已通过）
- 用户已收到通知

## 做什么

1. **等待用户 Review PR**

2. **用户确认后**：
   - 合并 PR
   - **同步主工作区**：在对应代码仓主工作区执行 `git fetch origin main && git pull origin main`，确保后续任务调查时代码是最新的
   - 更新 Bug 管理表（→ tripo-tables）：进度 In progress → Resolved

3. **配合验收测试**：
   - 发现问题时加载 `tripo-dev` skill（返工模式）修复代码
   - 更新 STATUS.md（→ tripo-task-dirs）

4. **验收通过后**：
   - 进入步骤 8 发布上线

## 如何定义完成

- [ ] PR 已合并
- [ ] 主工作区已同步远程 main
- [ ] Bug 表进度 = Resolved
- [ ] 用户验收通过
- [ ] 发现的问题已修复
- [ ] STATUS.md 已更新

## 如何定义完成

- [ ] 代码已部署到目标环境
- [ ] Bug 表进度已更新为 Resolved
- [ ] worktree 已清理
- [ ] 报告人已通知
