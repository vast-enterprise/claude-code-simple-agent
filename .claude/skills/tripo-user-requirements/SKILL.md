---
name: tripo-user-requirements
description: 查询 Tripo 需求管理系统中用户相关的所有需求（产品需求池、执行中需求、技术需求一览表）。匹配用户作为创建人、研发Owner、需求Owner、Member、开发人员的需求，按状态分组输出，含 record_id 用于定位。触发条件：查询某人的需求、我的需求、某人负责的需求、某人手上的需求、需求列表、需求进度、需求状态、查用户需求、需求汇总。
---

# Tripo 用户需求查询

运行脚本查询指定用户在三个飞书多维表格中的需求：

```bash
python3 .claude/skills/tripo-user-requirements/scripts/query_user_requirements.py <ARGUMENTS>
```

## ARGUMENTS 处理

将 skill 接收的 ARGUMENTS 直接传给脚本。支持：
- 用户名：`郭凯南`
- open_id：`ou_xxx`
- 当前用户：`我`（自动调用 `lark-cli contact +get-me`）

## 注意事项

1. **API 字段顺序不稳定**：每页返回的 `fields` 数组顺序可能不同，脚本已处理
2. **分页独立解析**：不能复用上一页的字段索引
3. **字段映射参考**：详见 [references/field-mapping.md](references/field-mapping.md)
