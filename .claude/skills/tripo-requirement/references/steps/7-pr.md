# 步骤 7：提交 PR

## 前置条件

- 代码已编写并通过 lint、typecheck、test
- 尚未创建 PR

## 做什么

1. **代码检查**：
   - lint 通过
   - typecheck 通过
   - test 通过

2. **提交代码**：
   ```bash
   git add .
   git commit -m "feat: <描述>"
   git push -u origin feature/REQ-xxx-简述
   ```

3. **创建 PR**：
   - 关联需求 ID
   - 关联任务目录
   - 描述变更内容

4. **更新 STATUS.md**

5. **提议状态变更**：
   - 执行表状态 → "测试中"
   - 需求池状态 → "验收/提测中"

## 如何定义完成

- [ ] 代码检查全部通过
- [ ] PR 已创建
- [ ] STATUS.md 已更新
- [ ] 已提议状态变更

## PR 格式

```markdown
## 关联需求
- 需求ID: <record-id>
- 任务目录: tasks/2026-04-02_REQ-xxx_xxx/

## 变更内容
- ...

## 测试计划
- [ ] 单元测试
- [ ] 本地验证
```

## ⚠️ 注意

**禁止 merge**，等待用户审查。