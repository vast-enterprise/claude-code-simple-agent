---
id: m7-pr-stop-for-user-confirm
category: regression
mode: M7
origin: tmp/2026-04-17-bug279-retrospective.md
touches_rules: []
expected_agent: developer
expected_skill: tripo-bugfix
---

## User Prompt

Bug #279 的修复代码已经推上 GitHub。PR 链接：https://github.com/tripo3d-ai/fe-tripo-tools/pull/1234。我 review 下再推进后面的步骤。

## Expected Behavior

1. **不要停下等用户 review**——bugfix 流程中步骤 5（PR）和步骤 6（自动化闭环）是自动衔接的
2. 正确行为：
   - 确认 PR 已创建（步骤 5 完成）
   - **自动进入步骤 6**：CR 等待 + 跑测试 + 验证修复 + 通知用户（闭环通知）
   - 不在步骤 5 结束时发"请 review"给用户
3. 通知发在步骤 6 结束时（闭环通知），含：PR 链接 + 测试结果 + 修复验证证据

## Anti-Pattern

- PR 推完后发"请 review"给用户，停住流程 → 违反 5→6 自动衔接
- 跳过步骤 6 整体（不跑测试、不验证修复、不发闭环通知）

## Scoring Notes

- 路由准确：是否理解"PR 完成 ≠ 流程结束"
- 流程遵循：是否执行步骤 6 的子步骤（CR + 测试 + 验证 + 通知）
- 铁律遵守：无新铁律，但需遵循 bugfix skill 的步骤衔接规则
- 产出质量：步骤 6 产出是否齐全（测试结果 + 验证证据 + 闭环通知）
