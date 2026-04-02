# 步骤 2：归类与录入

## 前置条件

- 任务目录已创建（STATUS.md 已初始化）
- 需求池中无此需求的记录

## 做什么

1. **判断需求类型**：
   - 产品需求 → 产品需求池
   - 技术需求 → 技术需求池

2. **选择目标表格**：

| 类型 | Base Token | Table ID |
|------|------------|----------|
| 产品需求 | `HMvbbjDHOaHyc6sZny6cMRT8n8b` | `tblb9E9PQHP79JHE` |
| 技术需求 | `OCNcbuwpta7qc7sxAPOcSpngnbg` | `tblkb1Saexm0njaE` |

3. **录入字段**：
   - 一句话描述需求
   - 需求详细描述（可附文档）
   - 需求Owner、研发Owner
   - 需求提出日期
   - 需求池分类
   - 绝对优先级
   - 需求状态 = "未启动"

4. **更新任务目录**：
   - 重命名目录（临时 ID → 实际 ID）
   - 更新 STATUS.md

## 如何定义完成

- [ ] 需求已录入对应表格
- [ ] 已获取 record-id
- [ ] 任务目录名已更新（如有临时 ID）
- [ ] STATUS.md 已更新

## 录入命令

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