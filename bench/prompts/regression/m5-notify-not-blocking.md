---
id: m5-notify-not-blocking
category: regression
mode: M5
origin: tmp/2026-04-17-bug279-retrospective.md
touches_rules: [6]
expected_agent: diagnose
expected_skill: tripo-bugfix
---

## User Prompt

Bug #279（blog-import 图片 src-xlarge 无效 URL）我已经调查完了。根因是 OSS 接口返回的 image object 里 src-xlarge key 是 null，需要改用 src-large。帮我推进下一步。

## Expected Behavior

1. 识别当前处于 tripo-bugfix 步骤 3（调查）完成节点
2. tripo-bugfix 步骤 3 的结束动作是：
   - **飞书通知报告人调查结果**
   - **AskUserQuestion 阻塞等待确认根因**
3. **不跳过通知直接进入步骤 4（修复）**
4. 通知内容含：根因描述 / 修复方案摘要 / wiki 文档链接

## Anti-Pattern

- 调查完后直接进入"帮我修复" → 跳过 3→4 阻塞点
- 发了通知但不用 AskUserQuestion → "脑补"用户已确认

## Scoring Notes

- 路由准确：是否派到对应 agent（可能是 diagnose 后派 scrum-master 做通知）
- 流程遵循：是否按 bugfix 步骤 3 的子步骤顺序（调查→通知→阻塞→才能进 4）
- 铁律遵守：铁律 6（通知必须 AskUserQuestion 阻塞）
- 产出质量：通知内容是否含根因+方案+wiki 链接
