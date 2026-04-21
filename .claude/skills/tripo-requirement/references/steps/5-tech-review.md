# 步骤 5：技术评审（方案 + 原型）

## 前置条件

- 执行表记录已存在
- 执行表"技术评审"字段 ≠ "完成"
- 任务目录下无 technical-solution.md（或涉及 UI 时，prototype/index.html 也未产出）

## 做什么

本步骤是**技术评审的合集**——包含两个子阶段，两者都完成才推进 R2 通知和状态变更。

### 子阶段 5a：架构技术方案（architect）

1. **分析技术方案**：
   - 评估多种实现方案
   - 考虑性能、可维护性、风险

2. **输出技术方案文档**：
   - 创建 `technical-solution.md`
   - 内容应包含：
     - 需求概述
     - 方案对比（多种方案、优缺点、推荐理由）
     - 详细设计（涉及模块、接口设计、数据模型）
     - 工作量评估
     - 风险评估
     - 测试计划

### 子阶段 5b：视觉原型（designer）

**触发条件判断**：

- 需求涉及**新页面 / 新组件 / 视觉变更 / 交互调整** → **必须走 5b**
- 纯后端 / 纯数据 / 无 UI 变更的需求 → 跳过 5b（在 STATUS.md 中显式标注"5b: 不适用，无 UI 变更"）

**5b 做什么**（触发时）：

1. **前置检查**：确认 5a 已完成——`technical-solution.md` 已产出且完整
2. **派 designer**（→ `tripo-frontend-design` 方法论 + `frontend-design:frontend-design` 美学层）
3. **产出**：`tasks/<task-dir>/prototype/index.html` + 配套 css/js/assets + `README.md`
4. **README.md 必含三段**：启动方式 / 验收点映射（逐条对照 review.md 验收标准）/ 版本痕迹
5. **浏览器验证**：designer 自己跑通主路径 + 响应式断点，贴截图

详见 `tripo-frontend-design` SKILL.md。

### 子阶段 5c：汇总与通知（scrum-master）

**必须等 5a 和 5b 都完成后才执行**（5b 不适用时只等 5a）：

1. **派 scrum-master 同步 Wiki + 更新 STATUS.md**（→ tripo-task-dirs wiki 同步铁律）：
   - `technical-solution.md` 走同步链
   - 原型 `prototype/index.html` 保留在 `tasks/<task-dir>/` 下供直接打开，**不同步 wiki**（HTML 在 wiki 里不可交互）
   - 5a/5b 完成状态记入 STATUS.md
2. **飞书通知用户**（→ tripo-notify，节点 R2）：
   - 消息模板的方案链接从 STATUS.md 读取 Wiki URL；原型链接保持 `tasks/<task-dir>/prototype/index.html`
   - 通知后**暂停**，等待用户确认
3. **提议状态变更**：
   - 执行表"技术评审"字段 → "完成"
   - 执行表"计划提测时间" → 根据 `technical-solution.md` 工作量评估推算（启动时间 + 总工作量天数），覆盖 Step 4 的粗估值

## 如何定义完成

- [ ] 5a：`technical-solution.md` 已输出，方案对比 / 详设 / 工作量 / 风险 / 回退齐全
- [ ] 5b：若需求涉及 UI 变更，`prototype/index.html` 已产出且浏览器跑通；若无 UI 变更，STATUS.md 显式标注"不适用"
- [ ] 5b 触发时，`prototype/README.md` 的验收点映射表与 `review.md` 验收标准一一对应
- [ ] `technical-solution.md` 已按 tripo-task-dirs wiki 同步铁律处理（Wiki 已同步、`node_token` 记入 STATUS.md 关联资源区）
- [ ] STATUS.md 已更新（5a/5b 状态清晰）
- [ ] 已提议"技术评审"="完成"
- [ ] 执行表"计划提测时间"已根据工作量更新
- [ ] R2 通知消息模板的方案链接从 STATUS.md 读取 Wiki URL；原型链接同时附上（原型适用时）
- [ ] 用户已确认方案 + 原型
