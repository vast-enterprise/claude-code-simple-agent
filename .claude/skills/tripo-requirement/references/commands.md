# 命令速查

## 表格 Token

| 表格 | Base Token | Table ID |
|------|------------|----------|
| 产品需求池 | `HMvbbjDHOaHyc6sZny6cMRT8n8b` | `tblb9E9PQHP79JHE` |
| 技术需求池 | `OCNcbuwpta7qc7sxAPOcSpngnbg` | `tblkb1Saexm0njaE` |
| 执行中需求 | `HMvbbjDHOaHyc6sZny6cMRT8n8b` | `tblxLMQ8Ih5Gs5oM` |

## 录入需求

```bash
lark-cli base +record-upsert \
  --base-token <base-token> \
  --table-id <table-id> \
  --json '{"fields": {
    "一句话描述需求": "<描述>",
    "需求详细描述（可附文档）": "<详细>",
    "需求Owner": [{"id": "<open-id>"}],
    "需求提出日期": <毫秒时间戳>,
    "需求状态": "未启动"
  }}'
```

## 查询需求

```bash
# 列表
lark-cli base +record-list --base-token <token> --table-id <id> --limit 10

# 单条
lark-cli base +record-get --base-token <token> --table-id <id> --record-id <id>
```

## 更新状态

```bash
lark-cli base +record-upsert \
  --base-token <token> \
  --table-id <id> \
  --record-id <record-id> \
  --json '{"fields": {"需求状态": "定容确认"}}'
```

## 更新阶段进度

```bash
# 字段名: 需求评审、技术评审、前端开发、后端开发、功能测试 等
--json '{"fields": {"<字段名>": "完成"}}'
```

## worktree 操作

```bash
# 创建
git worktree add .worktrees/feature/REQ-xxx-简述 -b feature/REQ-xxx-简述

# 列表
git worktree list

# 删除
git worktree remove .worktrees/feature/REQ-xxx-简述
```

## PR 操作

```bash
# 推送
git push -u origin feature/REQ-xxx-简述

# 创建 PR
gh pr create --title "feat: <简述>" --body-file <文件>
```