---
id: n4-tech-review
category: normal
origin: tripo-requirement step 5
touches_rules: []
expected_agent: architect
expected_skill: tripo-architecture
---

## User Prompt

需求已经评审通过：CMS 需要支持文章之间的"推荐阅读"关系，每篇文章可以关联最多 5 篇其他文章。帮我写技术方案。

## Expected Behavior

1. 识别为"技术方案"类任务（tripo-requirement 步骤 5 语义）
2. 派到 architect agent
3. architect 行为：
   - 加载 tripo-architecture skill
   - 加载 tripo-repos 了解 CMS 技术栈
   - 读 CMS llmdoc（铁律 3）了解当前数据模型
   - 按技术方案结构写：背景 / 目标 / 方案对比 / 风险 / 回退
   - 方案对比至少 2 种（如：字段内嵌 vs 独立 relation collection）
   - 标注跨仓库影响（如前端是否要改）

## Anti-Pattern

- 跳过调研直接给一个方案
- 不读 llmdoc 凭印象写
- 不对比多种方案

## Scoring Notes

- 路由准确：是否派到 architect agent
- 流程遵循：方案结构是否完整（背景/目标/对比/风险/回退）
- 铁律遵守：铁律 3（读 llmdoc）
- 产出质量：方案是否含 ≥2 个选项对比 + 跨仓库影响分析
