# 技术需求管理

**Table ID**: `tblkb1Saexm0njaE`
**Base Token**: `OCNcbuwpta7qc7sxAPOcSpngnbg`

技术需求管理有 `是否发版` 字段（select），表示技术需求可以不走发车流程。

> 注：技术需求一览表的字段结构与产品需求池类似但独立维护。
> 具体字段 ID 查询 → lark-base skill，此处只记录核心元信息。

## 录入关键字段

与产品需求池语义一致，字段名如下（Field ID 请用 `lark-base base table-field-list` 现场拉取，本表的 ID 与产品需求池不同）：

- 需求Owner（默认 = 提出人，代录入时可修正）【录入关键字段，需确认】
- 研发Owner【录入关键字段，需确认】
- 绝对优先级【录入关键字段，需确认】
- 需求池分类【录入关键字段，需确认】

> 录入前确认机制 → `tripo-tables` SKILL「录入前确认机制」。
