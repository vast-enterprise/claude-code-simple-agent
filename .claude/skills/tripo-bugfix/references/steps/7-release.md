# 步骤 7：上线

## 前置条件

- 步骤 6 完成：PR 已合并

## 做什么

1. **确认 PR 已合并**：
   - `gh pr view <PR-number> --json state`

2. **同步主分支**（铁律：代码合入后需求仓主工作区同步远程 main）：
   - `git fetch origin main && git pull origin main`

3. **根据优先级决定上线方式**：
   - **P0**：走 Hotfix 流程（→ tripo-release，hotfix 模式）
   - **P1**：跟随最近的 Sprint 发车（→ tripo-release）
   - **P2**：跟随下一个 Sprint 发车

4. **更新 Bug 管理表**（→ tripo-tables）：
   - 进度：In progress → Resolved
   - 备注：追加 PR 链接和上线版本

5. **通知报告人**：
   - 如果 bug 是同事报告的，通知对方已修复

6. **清理 worktree**（→ tripo-worktree）

7. **上线后验证**（可选，需所有者确认）：
   - 生产环境验证修复效果
   - 验证通过后：进度 Resolved → Closed

## 如何定义完成

- [ ] 代码已部署到目标环境
- [ ] Bug 表进度已更新为 Resolved
- [ ] worktree 已清理
- [ ] 报告人已通知
