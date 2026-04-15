# 步骤 6：创建 PR

## 前置条件

- 步骤 5 完成：staging 验证通过

## 做什么

1. **创建 PR**：
   ```bash
   gh pr create --title "fix: <一句话描述>" --body "$(cat <<'EOF'
   ## Bug
   <Bug 现象描述>
   
   ## 根因
   <根因分析>
   
   ## 修复
   <修复方式和涉及文件>
   
   ## 验证
   - staging 验证：<链接/截图>
   - 本地验证：<测试结果>
   
   ## Bug 记录
   Bug #<bugID>，record_id: <record_id>
   EOF
   )"
   ```

2. **🔔 通知所有者**：
   - AskUserQuestion 等待确认："PR 已创建：<PR链接>，请 review"
   - **必须等待确认后才能继续**（铁律 6）

3. **等待 PR 合并**：
   - 所有者确认后，等待 review 和合并
   - 如有 review 意见，修改后更新 PR

## 如何定义完成

- [ ] PR 已创建，包含完整的 bug 描述、根因、修复、验证信息
- [ ] 已通知所有者
- [ ] PR 已合并（或等待合并中）
