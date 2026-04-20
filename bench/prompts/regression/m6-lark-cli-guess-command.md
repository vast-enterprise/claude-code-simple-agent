---
id: m6-lark-cli-guess-command
category: regression
mode: M6
origin: tmp/2026-04-16-bug275-postmortem.md
touches_rules: [7]
expected_agent: scrum-master
expected_skill: tripo-tables
---

## User Prompt

把飞书 Bug 表里 recvgPTEr2SYZL 这条的「状态」字段更新为「已关闭」。

## Expected Behavior

1. 派到 scrum-master agent（负责飞书表格操作）
2. scrum-master 行为：
   - 加载 tripo-tables skill
   - 查「Bug 表」的 Table ID 和「状态」字段的 option_id（不凭记忆）
   - 用 `lark-cli base +record-upsert`（具体命令从 tripo-tables 查）
   - 参数用正确 flag 名（如 `--base-token` 不是 `--base`）
3. 如果是通知场景需用 `--as bot`（铁律 7）

## Anti-Pattern

- 凭记忆拼 `lark-cli base --base xxx --record xxx`（不存在的 flag）
- 使用不存在的子命令（如 `+record-update`）
- 中文字段名用 `-q` jq 表达式裸写

## Scoring Notes

- 路由准确：是否派到 scrum-master
- 流程遵循：是否先查 Table ID / option_id 再发命令
- 铁律遵守：铁律 7（--as bot）+ 不凭记忆
- 产出质量：lark-cli 命令是否实际可跑（flag 正确、子命令存在）
