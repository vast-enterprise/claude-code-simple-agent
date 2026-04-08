# 步骤 6：编码开发

## 前置条件

- 技术方案已确认（technical-solution.md 已存在，执行表"技术评审"= "完成"）
- 对应开发字段（前端开发/后端开发）≠ "完成"

## 做什么

1. **进入代码仓库**（→ tripo-repos）

2. **创建 worktree**（→ tripo-worktree）

3. **阅读项目文档**：
   - 读取 llmdoc/index.md 了解项目

4. **编码实现**：
   - 编写代码
   - 编写测试

5. **实时更新 STATUS.md**（→ tripo-task-dirs）

6. **提议阶段状态变更**（→ tripo-tables）：
   - 开始时：对应开发字段 → "进行中"
   - 完成时：对应开发字段 → "完成"

7. **更新 llmdoc（如需要）**：
   - 使用 `tr:recorder` agent 更新项目文档
   - 触发条件：代码涉及新架构、新目录结构、新组件模式、API 变更
   - **注意**：llmdoc 更新不是强制步骤，需按需执行

## 如何定义完成

- [ ] worktree 已创建
- [ ] 代码已编写
- [ ] 测试已编写
- [ ] lint、typecheck 通过
- [ ] llmdoc 已更新（如涉及架构/模式变更）
- [ ] STATUS.md 已更新
- [ ] 已提议阶段状态为"完成"
