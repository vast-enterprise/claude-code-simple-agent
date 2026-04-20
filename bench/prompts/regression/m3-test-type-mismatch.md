---
id: m3-test-type-mismatch
category: regression
mode: M3
origin: tmp/2026-04-17-bug279-retrospective.md
touches_rules: [5, 12]
expected_agent: tester
expected_skill: tripo-test
---

## User Prompt

Bug #279 的修复是：blog-import 从 OSS 拉图片时，之前用 `src-xlarge` key 拿 URL 拿到了 null。改成 `src-large` 后正常。帮我设计集成测试：
1. 验证修复后图片 URL 正确
2. 验证数据库里写入的 Post 图片字段有真实 URL

## Expected Behavior

1. 加载 tripo-test skill
2. 对照分类表拆分：
   - 场景 1（图片拉取）→ API 集成测试 → **curl + 脚本**
   - 场景 2（数据库写入）→ 数据验证 → **mongosh**
   - 可加：场景 3（端到端导入）→ UI 流程 → **playwright**
3. 至少一个场景的证据是"真实服务输出"（不是 vitest mock）

## Anti-Pattern

- S1-S5 全写 vitest，mock fetch、mock mongo
- S7 playwright 标记为 DEFERRED
- 用"先用 vitest 快速验证"作为理由

## Scoring Notes

- 路由准确：是否派到 tester agent
- 流程遵循：是否执行 tripo-test 四步法
- 铁律遵守：铁律 12（分类对照）+ 铁律 5（证据先贴再结论）
- 产出质量：测试方案是否含真实服务验证（curl/mongosh/playwright 至少一种）
