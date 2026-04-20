---
name: tripo-tables
description: |
  飞书多维表格全操作：表结构/字段/记录/用户需求查询、状态流转数据字典。
  被 tripo-requirement、tripo-release 等流程 skill 显式调用，也可独立使用。

  触发条件：
  - 查表格、查字段、查需求、录入需求、更新状态
  - 查询某人的需求、我的需求、需求列表、需求进度
  - 需要 Table ID、Field ID、状态选项值、option_id、Workflow ID
  - **不触发**："发车"、"上线"、"上车"（属 tripo-release 编排，本 skill 只被其调用获取字典数据）
---

# Tripo 飞书多维表格

## 两个 Base

| 名称 | Base Token | Wiki 链接 |
|------|------------|-----------|
| Tripo 需求一览表 | `HMvbbjDHOaHyc6sZny6cMRT8n8b` | [链接](https://a9ihi0un9c.feishu.cn/wiki/VUsowxr0FicXlSktlxncRZsAnAu) |
| 技术需求一览表 | `OCNcbuwpta7qc7sxAPOcSpngnbg` | [链接](https://a9ihi0un9c.feishu.cn/wiki/SpxCwqWVeiYQvhkXW6FcJwB6nwc) |

## 数据表速查

### Tripo 需求一览表（`HMvbbjDHOaHyc6sZny6cMRT8n8b`）

| 表名 | Table ID | 定位 | 字段详情 |
|------|----------|------|----------|
| 产品需求池 | `tblb9E9PQHP79JHE` | 需求全生命周期户口本 | [fields-product-pool.md](references/fields-product-pool.md) |
| 执行中需求 | `tblxLMQ8Ih5Gs5oM` | 开发工单，跟踪各环节进度 | [fields-execution.md](references/fields-execution.md) |
| 发车中需求 | `tblPlaxVsLBvKMRl` | 需求绑定到版本后的车票 | — |
| Sprint 版本计划 | `tblm2FGJjiK4frzt` | 班车本身，每周自动创建 | [fields-sprint.md](references/fields-sprint.md) |
| Hotfix管理 | `tblzLyiFJtsYZRsN` | hotfix 跟踪 | [fields-hotfix.md](references/fields-hotfix.md) |
| 需求Bug管理 | `tblkGH8uvmXS80CB` | bug 跟踪 | [fields-bug.md](references/fields-bug.md) |
| SSS级需求管理 | `tblvLgFVpQJDWXpp` | 待废弃 | — |
| 数据表 | `tblo2UCnfgHYb0aT` | 辅助数据 | — |

### 技术需求一览表（`OCNcbuwpta7qc7sxAPOcSpngnbg`）

| 表名 | Table ID | 定位 | 字段详情 |
|------|----------|------|----------|
| 技术需求管理 | `tblkb1Saexm0njaE` | 技术需求池 | [fields-tech-pool.md](references/fields-tech-pool.md) |

## 表间关系

```
产品需求池 ──[需求准入]──→ 执行中需求 ──[需求准出]──→ 发车中需求
技术需求管理 ──[需求准入]──→ 执行中需求        ↑
                                          Sprint 版本计划
                                               ↑
                                    需求Bug管理 → Hotfix管理
```

- 产品需求池.`预计/实际版本`（link）→ Sprint 版本计划
- 发车中需求.`发车版本`（link）→ Sprint 版本计划

## 完整状态流转

```
产品需求池.需求状态:
  未启动 → 定容确认 → 开发/交付中 → 验收/提测中 → 已完成

执行中需求.状态:
  评审中 → 研发中 → 测试中 → 完成

发车中需求.状态:
  待上线 → 上线中 → 完成

Sprint版本计划.班车状态:
  已启动 → 已完成

Sprint版本计划.部署进度（接力式）:
  □算法 → ✓算法 □后端 → ✓算法 ✓后端 □前端 → ✓全部完毕
```

## 发车相关数据字典

发车涉及表格的 option_id / Workflow ID / checkbox 字段 ID / lark-cli 业务参数：[references/release-flow.md](references/release-flow.md)

> 发车**业务流程**（三条路径语义、接力部署、前端视角关键节点）见 `tripo-release/references/dispatch-board.md`。本 skill 只管数据字典。

## 记录查询

### 按关键词搜索记录（优先使用）

在任意表中按关键词搜索，自动分页、自动解析返回结构：

```bash
python3 <skill-path>/scripts/search_records.py <表名|table_id> <关键词> [--field 字段名]
```

示例：

```bash
# 在发车中需求表搜 blog 相关记录
python3 <skill-path>/scripts/search_records.py 发车中需求 blog

# 在执行中需求表按研发Owner搜
python3 <skill-path>/scripts/search_records.py 执行中需求 郭凯南 --field 研发Owner
```

支持表名简写：产品需求池 / 执行中需求 / 发车中需求 / Sprint版本计划 / Hotfix管理 / 需求Bug管理 / 技术需求管理

### 按用户查询需求

查询指定用户在三个表中的需求：

```bash
python3 <skill-path>/scripts/query_user_requirements.py <用户名|open_id|我>
```

- `我` 自动调用 `lark-cli contact +get-me` 获取当前用户
- 字段映射参考：[references/field-mapping.md](references/field-mapping.md)

### 手写 lark-cli 查询

`record-list/record-get` 返回结构解析、分页、中文字段名、WARN 干扰 stdout 等通用坑 → 查 **lark-base skill**。本 skill 只管业务侧的 Table ID / 字段语义 / 状态 option_id / Workflow ID。

