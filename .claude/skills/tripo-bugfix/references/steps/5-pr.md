# 步骤 5：创建 PR

## 前置条件

- 步骤 4 完成：代码修改完成，tripo-dev 完成 Checklist 通过（含 lint/typecheck/test/运行时验证）
- 尚未创建 PR

## 做什么

1. **推送分支到远程**：
   - `git push -u origin <branch-name>`

2. **创建 PR**：
   ```bash
   gh pr create --title "fix: <一句话描述>" --body "$(cat <<'EOF'
   ## Bug
   <Bug 现象描述>

   ## 根因
   <根因分析>

   ## 修复
   <修复方式和涉及文件>

   ## Bug 记录
   Bug #<bugID>，record_id: <record_id>
   EOF
   )"
   ```

3. **更新 STATUS.md**（→ tripo-task-dirs）

## ⚠️ 注意

创建 PR 后**继续步骤 6**，不要通知用户。

## 如何定义完成

- [ ] 分支已推送到远程
- [ ] PR 已创建，包含完整的 bug 描述、根因、修复信息
- [ ] STATUS.md 已更新
