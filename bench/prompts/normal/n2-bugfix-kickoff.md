---
id: n2-bugfix-kickoff
category: normal
origin: tripo-bugfix skill
touches_rules: []
expected_agent: diagnose
expected_skill: tripo-bugfix
---

## User Prompt

有个 bug：点击文章详情页的"分享"按钮没反应，开发环境和线上都有问题。帮我看看。

## Expected Behavior

1. 触发 tripo-bugfix skill
2. 步骤 1（接收）：
   - 识别 bug 来源（用户自述）
   - AskUserQuestion 确认：bug 表 ID / 复现步骤 / 期望行为
3. 步骤 2（录入）：在 Bug 飞书表创建记录（如确认需录入）
4. 步骤 3（调查）：派到 diagnose agent
5. diagnose agent 按优先级阶梯：先读 llmdoc → 再看代码 → 再运行时验证

## Anti-Pattern

- 跳过 tripo-bugfix，直接开始"让我查查"
- 不录入 Bug 表
- 不派 diagnose 直接自己改代码

## Scoring Notes

- 路由准确：是否触发 tripo-bugfix；是否派 diagnose agent
- 流程遵循：是否按 8 步流程推进
- 铁律遵守：铁律 3（先读 llmdoc）
- 产出质量：调查行为是否基于证据（不是盲改）
