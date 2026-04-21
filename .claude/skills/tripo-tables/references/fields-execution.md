# 执行中需求

**Table ID**: `tblxLMQ8Ih5Gs5oM`
**Base Token**: `HMvbbjDHOaHyc6sZny6cMRT8n8b`

## 字段结构

| 字段名 | Field ID | 类型 | 说明 |
|--------|----------|------|------|
| 状态 | `fldlb7BtiZ` | select | 需求执行状态 |
| 需求来源 | `fldymnWlrk` | select | 需求来源分类（功能/运营/UI；**不是 link 字段，不能回查来源池记录**）|
| 需求类型 | `fldUF6s1nQ` | select | 需求类型分类 |
| 风险归类 | `fldkQM4Mz6` | select | 风险等级 |
| 产品Owner | `fld8K6pMOg` | user | 产品负责人 |
| 研发Owner | `fldZMbDF8P` | user | 研发负责人 |
| 测试Owner | `fldv07SWgW` | user | 测试负责人 |
| SRE Owner | `fldkmmjFe7` | user | SRE负责人 |
| 开发人员 | `fld05KBpQ8` | user | 开发团队成员 |
| 需求描述 | `fldpGalbRG` | text | 需求描述 |
| 启动时间 | `fldzVCPQAA` | datetime | 开发启动日期 |
| 计划提测时间 | `fldRid6Upm` | datetime | 计划提测日期 |
| 高优保障需求 | `fldxRER2aa` | checkbox | 是否高优 |

## 状态选项

**状态** (`fldlb7BtiZ`)

| 选项 | 说明 |
|------|------|
| 评审中 | 需求评审阶段 |
| 研发中 | 开发进行中 |
| 测试中 | 测试阶段 |
| 完成 | 开发完成 |
| 风险 | 存在风险 |
| 暂停 | 开发暂停 |

**需求来源** (`fldymnWlrk`)

| 选项 | 说明 |
|------|------|
| 功能变更 | 功能调整需求 |
| 运营变更 | 运营相关需求 |
| UI 变更 | UI 调整需求 |

## 阶段进度字段

| 字段名 | Field ID | 类型 | 说明 |
|--------|----------|------|------|
| 需求评审 | `fldh5xqkWk` | select | 需求评审状态 |
| 技术评审 | `fldr2Nrt4T` | select | 技术评审状态 |
| UI/UE设计 | `fldbmgninU` | select | 设计状态 |
| 埋点设计 | `fldOdBdiNS` | select | 埋点状态 |
| 前端开发 | `fldDkUFaPh` | select | 前端开发状态 |
| 后端开发 | `fldulzM9At` | select | 后端开发状态 |
| 算法开发 | `fldOFIL2bB` | select | 算法开发状态 |
| 测试用例评审 | `fldfCMVS22` | select | 用例评审状态 |
| 功能测试 | `fldduXJg66` | select | 测试状态 |
| 国际化翻译 | `flddj8aPag` | select | 翻译状态 |

### 阶段进度通用选项值

各阶段进度字段（需求评审、技术评审、前端开发、后端开发等）共用：

| 选项 | 说明 |
|------|------|
| 未启动 | 尚未开始 |
| 不需要 | 无需此阶段 |
| 进行中 | 进行中 |
| 完成 | 已完成 |
| 风险 | 存在风险 |
