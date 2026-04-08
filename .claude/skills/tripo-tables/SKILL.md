---
name: tripo-tables
description: |
  Tripo 飞书多维表格数据字典与发车流程。提供所有表格的 Base Token、Table ID、字段结构、状态选项值、
  表间关系、完整状态流转、发车上线三条路径、Workflow ID 和 option_id 速查。
  被 tripo-requirement 等流程 skill 显式调用，也可在直接操作飞书表格时使用。

  触发条件：
  - 其他 skill（tripo-requirement、未来的 bugfix 流程）显式调用
  - 需要查询 Table ID、Field ID、状态选项值、option_id
  - 需要了解发车流程、上线路径、Workflow ID
  - "表格结构"、"字段 ID"、"需求状态"、"发车流程"、"上线"
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

## 发车流程与 Workflow

发车上线三条路径和完整 Workflow/option_id 速查：[references/release-flow.md](references/release-flow.md)
