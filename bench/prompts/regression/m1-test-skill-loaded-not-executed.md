---
id: m1-test-skill-loaded-not-executed
category: regression
mode: M1
origin: tmp/2026-04-16-bug275-postmortem.md
touches_rules: [12]
expected_agent: tester
expected_skill: tripo-test
---

## User Prompt

Bug #275 SSR 空标签问题已经定位完。现在要写集成测试验证修复效果：博客详情页服务端渲染后，文章正文区域 `<article>` 是否包含实际内容（不能是空标签）。帮我设计并实现测试。

## Expected Behavior

1. 加载 tripo-test skill
2. **逐场景对照 tripo-test 分类表**：
   - 验证对象 = "页面元素在 SSR 渲染时是否有内容"
   - 测试类型 = **UI 渲染测试**
   - 工具 = **playwright**（不是 vitest）
   - 证据形式 = SSR HTML 快照 / 页面 DOM 断言
3. 测试计划主力应为 playwright，vitest 只做辅助（如验证渲染函数的 VNode 结构）
4. 不把 playwright 测试标记为 "DEFERRED"

## Anti-Pattern（本次要检测的失败）

- 加载 tripo-test 但不对照分类表，S1-S6 全写 vitest
- 把唯一的 playwright 测试标记为 DEFERRED
- 用"vitest 更快"作为借口

## Scoring Notes

- 路由准确：是否派到 tester agent（baseline 期望 0，P5 后期望 5）
- 流程遵循：是否按 tripo-test 的"4 步法"（对照分类表→选工具→设计→执行）
- 铁律遵守：铁律 12（测试类型对照）是否遵守
- 产出质量：测试代码是否能跑、是否真的验证 SSR 渲染（而不是组件结构）
