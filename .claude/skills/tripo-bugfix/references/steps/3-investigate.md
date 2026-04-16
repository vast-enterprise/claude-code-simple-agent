# 步骤 3：调查 & 定位根因

## 前置条件

- 步骤 2 完成：Bug 已录入管理表

## 做什么

1. **进入涉及的代码仓库**（→ tripo-repos）

2. **加载 `tripo-diagnose` skill 执行调查**

3. **编写 Bug 定位报告**：
   - 路径：`tasks/$TASK_ID/bug-investigation.md`
   - 内容：
     - Bug 现象与环境
     - 根因分析（定位到具体代码位置）
     - 受影响范围清单
     - 修复建议

4. **Wiki 同步**（→ tripo-task-dirs wiki 同步规则）：
   - 将 bug-investigation.md 同步到飞书 wiki

5. **飞书通知相关人员**（→ tripo-notify，节点 B1）：
   通知后**暂停**，等待确认后继续

6. **更新 STATUS.md**（→ tripo-task-dirs）

7. **更新 Bug 表**（→ tripo-tables）：
   - 进度：Open → In progress
   - 更新 `复现步骤` 字段（补充根因分析）

## 如何定义完成

- [ ] 根因已定位到具体代码位置
- [ ] 受影响范围已列出完整清单
- [ ] bug-investigation.md 已输出
- [ ] Wiki 已同步
- [ ] 已通知相关人员并等待确认
- [ ] Bug 表已更新为 In progress
