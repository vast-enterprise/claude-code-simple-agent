# 产品需求池

**Table ID**: `tblb9E9PQHP79JHE`
**Base Token**: `HMvbbjDHOaHyc6sZny6cMRT8n8b`

## 字段结构

| 字段名 | Field ID | 类型 | 说明 |
|--------|----------|------|------|
| 需求提出日期 | `fldl4EsNYi` | datetime | 需求创建时间 |
| 需求Owner | `fldeFXWrBP` | user | 需求负责人 |
| 研发Owner | `fldcrC0dNU` | user | 研发负责人 |
| 测试Owner | `fldpu0tTDa` | user | 测试负责人 |
| 需求状态 | `fldrcs9dZA` | select | 需求当前状态 |
| 绝对优先级 | `fldEoiYN2X` | select | 优先级排序 |
| 需求池 | `fldboFiGvi` | select | 需求池分类 |
| 需求描述 | `fldSJQfqQD` | text | 简要描述 |
| 需求详细描述 | `fldQ2spTUo` | text | 详细描述（可附文档） |
| 技术评审文档 | `fldjaF5fXE` | text | 技术评审链接 |
| 测试用例 | `fldO8kGnvv` | text | 测试用例链接 |
| 预期提测时间 | `fldVphL3FJ` | datetime | 计划提测日期 |
| 预期上线时间 | `fldahODYXi` | datetime | 计划上线日期 |
| 实际上线时间 | `fldDJCyFl7` | datetime | 实际上线日期 |
| 预计/实际版本 | `fldrnlaVAx` | link | 关联版本计划 |
| Member | `fldsr1pwhD` | user | 团队成员 |
| 创建人 | `fldWRUzUPb` | created_by | 系统字段 |
| 创建周数标签 | `fld5GtbwH7` | formula | 计算字段 |

## 状态选项

**需求状态** (`fldrcs9dZA`)

| 选项 | 说明 |
|------|------|
| 未启动 | 需求已录入，等待启动 |
| 定容确认 | 容量评估确认中 |
| 开发/交付中 | 开发进行中 |
| 验收/提测中 | 测试验收阶段 |
| 已完成 | 需求已上线 |
| 暂停 | 需求暂停处理 |

**绝对优先级** (`fldEoiYN2X`)

| 选项 | 说明 |
|------|------|
| SSS 紧急插入 | 最高优先级紧急需求 |
| L1 | 一级优先 |
| L2 | 二级优先 |
| L3 | 三级优先 |
| L4 | 四级优先 |
| L5 | 五级优先 |
| 未启动 | 尚未排期 |

**需求池** (`fldboFiGvi`)

| 选项 | 说明 |
|------|------|
| Studio - 营收 | 营收相关需求 |
| Studio - 用户满意度 | 用户体验优化 |
| Studio - 用户增长 | 用户增长相关 |
| 数据需求 | 数据分析需求 |
| 基建类需求 | 基础设施需求 |
| OpenAPI | API 相关需求 |
| 内部提效 | 内部工具需求 |
| 紧急插入需求 | 紧急插入 |
| 营收子项-订阅方案整合 | 营收子项 |
| 营收子项-用户管理 | 营收子项 |
| 营收子项-用户裂变 | 营收子项 |
