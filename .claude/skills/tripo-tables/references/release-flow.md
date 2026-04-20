# 发车相关数据字典

> **定位**:发车流程涉及表格的 option_id、workflow_id、字段 ID、lark-cli 业务参数速查。
> 业务流程(三条路径语义、接力部署、前端视角关键节点)见 `tripo-release/references/dispatch-board.md`。

## option_id 速查

| 表 | 字段 | 值 | option_id |
|---|---|---|---|
| 发车中需求 | 状态 | 待上线 | `opt4en3kmH` |
| 发车中需求 | 状态 | 上线中 | `optC9AGWNi` |
| 发车中需求 | 状态 | 完成 | `optePqTXTq` |
| 产品需求池 | 需求状态 | 定容确认 | `optQAzToIi` |
| 产品需求池 | 需求状态 | 开发/交付中 | `optCOhdvhV` |
| 产品需求池 | 需求状态 | 验收/提测中 | `optTwz2oGG` |
| 产品需求池 | 需求状态 | 已完成 | `optIA6pmzn` |
| Sprint版本计划 | 班车状态 | 已启动 | `optCOhdvhV` |
| Sprint版本计划 | 班车状态 | 已完成 | `optIA6pmzn` |
| Sprint版本计划 | 上线类型 | 跟车 | `optDJP1vHX` |
| Sprint版本计划 | 上线类型 | sss | `optNWVwviv` |
| Sprint版本计划 | 上线类型 | hotfix | `optsxcYV2l` |
| 执行中需求 | 状态 | 评审中 | `optyJLYX3O` |
| 执行中需求 | 状态 | 完成 | `optePqTXTq` |
| 执行中需求 | 需求类型 | Sprint需求 | `optUUNNlJr` |
| 执行中需求 | 需求类型 | SSS级需求 | `optGajhwE4` |

## Workflow 速查

| workflow_id | 名称 | 触发方式 | 作用 |
|---|---|---|---|
| `wkfEdyvotjKQHMr6` | 每周创建发车版本 | TimerTrigger(每周) | 自动创建本周班车 |
| `wkftpEooZBMc2AUa` | 需求准入确认 | ButtonTrigger | 产品需求池 → 执行中需求 |
| `wkfCTuzpHvY4FghE` | 需求准出确认 | ButtonTrigger | 执行中需求 → 发车中需求(跟车) |
| `wkfufcEDGQeXQfTF` | 临时发车确认 | ButtonTrigger | SSS 紧急通道 |
| `wkf1daTXkGSUjGLY` | 创建发车hotfix | ButtonTrigger | Hotfix 通道 |
| `wkf9ICnGBZyU2G0R` | 启动发车 | ButtonTrigger | 待上线 → 上线中 |
| `wkfiXUddmigXTMvK` | 发车流程监控 | SetRecordTrigger | 监控 3 个 checkbox 接力通知 |
| `wkfQpKcvFM3J7v10` | 发版信息同步 | ButtonTrigger | 添加群成员,通知发车信息 |
| `wkfv7lNEMo3XlRlR` | 发版完成确认 | ButtonTrigger | 上线中→完成,需求池→已完成 |
| `wkfDZswkBew4cDpN` | 每日执行中需求状态同步 | TimerTrigger | 每日同步状态 |

## 部署 checkbox 字段 ID(Sprint 版本计划)

| 字段 | Field ID |
|------|----------|
| 算法部署完毕 | `fldDgrQRTd` |
| 后端部署完毕 | `fldWGA6C5g` |
| 前端部署完毕 | `fldy6ym5PN` |

## lark-cli 直接操作(绕过 workflow 按钮)

所有记录的增改查 → 调用 **lark-base skill**(`+record-list` / `+record-upsert` / `+record-update`)。
本表只提供业务参数:

| 场景 | 涉及表 | 关键字段 | 写入值来源 |
|---|---|---|---|
| 需求准出(跟车) | Sprint 版本计划(查已启动的跟车版本)→ 发车中需求(upsert 状态=待上线,关联发车版本)→ 执行中需求(update 状态=完成)→ 产品需求池(update 需求状态=验收/提测中) | 班车状态 / 上线类型 / 状态 / 需求状态 / 发车版本(link) | 上方「option_id 速查」 |
| 需求准出(SSS 紧急) | Sprint 版本计划(upsert 新版本,上线类型=sss、班车状态=已启动)→ 发车中需求(upsert 状态=上线中)→ 执行中需求 + 产品需求池(同跟车后半段) | 同上 | 同上 |
| 勾部署 checkbox | Sprint 版本计划(update checkbox=true) | 算法部署完毕 / 后端部署完毕 / 前端部署完毕 | 上方「部署 checkbox 字段 ID」 |
| 发版完成确认 | 发车中需求(update 状态=完成)+ 产品需求池(update 需求状态=已完成)+ Sprint 版本计划(update 班车状态=已完成) | 同上 | 同上 |

Base Token / Table ID / 字段详情见 SKILL.md「数据表速查」。`record-upsert` 的 link 字段写法(`[{"record_id": "..."}]`)、中文字段名的坑、WARN 污染 stdout 等解析/构造细节 → **lark-base skill**。
