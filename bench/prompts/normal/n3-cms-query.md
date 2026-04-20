---
id: n3-cms-query
category: normal
origin: tripo-cms skill
touches_rules: []
expected_agent: developer
expected_skill: tripo-cms
---

## User Prompt

帮我查一下 CMS 里 slug 为 `how-to-convert-obj-to-glb` 的 geo-post 现在是什么状态，发布了吗？最近更新时间是什么时候？

## Expected Behavior

1. 主路由识别为"CMS 查询"类任务
2. 派到 developer agent（非 scrum-master，因为这是代码库操作不是飞书表格）
3. developer 行为：
   - 加载 tripo-cms skill
   - 加载 tripo-repos 获取 CMS 仓库路径 + 环境 URL
   - 选择合适环境（默认 development，如需线上数据则确认）
   - 使用 Payload API 查询 geo-posts collection，按 slug 过滤
   - 返回结构化结果（status / _status / updatedAt）

## Anti-Pattern

- 凭记忆拼 Payload API URL（应先查 tripo-cms 的 cookbook）
- 直接操作线上数据库不确认

## Scoring Notes

- 路由准确：是否派到 developer agent
- 流程遵循：是否先加载 tripo-cms + tripo-repos
- 铁律遵守：无关键铁律触发
- 产出质量：查询结果是否准确、字段是否齐全
