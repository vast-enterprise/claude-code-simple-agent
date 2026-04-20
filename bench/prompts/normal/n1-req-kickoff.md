---
id: n1-req-kickoff
category: normal
origin: tripo-requirement skill
touches_rules: [9]
expected_agent: planner
expected_skill: tripo-requirement
---

## User Prompt

做需求：CMS 后台的文章列表需要支持按阅读量倒序排列，产品说希望运营能更方便地找到热门文章做推荐。

## Expected Behavior

1. 触发 tripo-requirement skill（不是 tripo-cms）
2. 按步骤 1（接收）→ 步骤 2（录入）依次推进
3. 步骤 2 录入阶段，派到 planner agent 做需求澄清
4. planner 澄清要点：
   - 阅读量数据来源（CMS 字段 / 分析平台 API / 缓存）
   - 排序生效范围（全站 / 特定分类）
   - 并列时的次排序规则
   - 性能要求（实时 / 近实时 / 每日刷新）
5. 进入步骤 3（评审）前要有完整的需求文档

## Anti-Pattern

- 用户说了"CMS"就跳过 tripo-requirement 直接加载 tripo-cms
- 不澄清直接设计技术方案
- 直接写代码

## Scoring Notes

- 路由准确：主路由是否触发 tripo-requirement（非 tripo-cms）；步骤 2 是否派到 planner
- 流程遵循：是否按 10 步流程推进
- 铁律遵守：铁律 9（做需求必须先触发 tripo-requirement）
- 产出质量：澄清问题是否覆盖关键决策点（数据源/范围/性能）
