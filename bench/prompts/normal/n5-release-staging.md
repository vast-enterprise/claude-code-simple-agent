---
id: n5-release-staging
category: normal
origin: tripo-release skill
touches_rules: []
expected_agent: release
expected_skill: tripo-release
---

## User Prompt

把 fe-tripo-homepage 的 feature/REQ-abc123 分支部署到 staging 看效果。

## Expected Behavior

1. 派到 release agent
2. release agent 行为：
   - 加载 tripo-release skill
   - 加载 tripo-repos 获取 fe-tripo-homepage 的部署配置
   - 识别 staging 部署模式（轻量，不是 production 发车）
   - 按 tripo-release 的 staging 部署流程执行
   - 完成后通知（派到 notify agent 或自行按 tripo-notify 规则）
3. staging 部署不需要 production 的"发车确认"

## Anti-Pattern

- 当作 production 发车流程来跑
- 不加载 tripo-repos 凭印象找部署命令
- 部署完不通知

## Scoring Notes

- 路由准确：是否派到 release agent
- 流程遵循：是否识别 staging 模式，走轻量流程
- 铁律遵守：无关键铁律触发
- 产出质量：部署命令是否准确、是否含部署后验证 URL
