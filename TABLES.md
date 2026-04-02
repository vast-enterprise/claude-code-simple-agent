# Tripo 研发流程表格

> 本文档记录 Tripo 需求管理的多维表格结构和流程状态映射。

## 表格总览

| 表格名称 | 链接 | Base Token | 说明 |
|---------|------|------------|------|
| Tripo 需求一览表 | [链接](https://a9ihi0un9c.feishu.cn/wiki/VUsowxr0FicXlSktlxncRZsAnAu) | `HMvbbjDHOaHyc6sZny6cMRT8n8b` | 产品需求池 + 执行中需求等 |
| 技术需求一览表 | [链接](https://a9ihi0un9c.feishu.cn/wiki/SpxCwqWVeiYQvhkXW6FcJwB6nwc) | `OCNcbuwpta7qc7sxAPOcSpngnbg` | 技术需求管理 |

---

## 一、Tripo 需求一览表

| 属性 | 信息 |
|------|------|
| **名称** | Tripo 需求一览表 |
| **链接** | https://a9ihi0un9c.feishu.cn/wiki/VUsowxr0FicXlSktlxncRZsAnAu |
| **Base Token** | `HMvbbjDHOaHyc6sZny6cMRT8n8b` |
| **数据表数量** | 8 个 |

## 数据表列表

| 表名 | Table ID | 说明 |
|------|----------|------|
| 产品需求池 | `tblb9E9PQHP79JHE` | 需求收集和初筛阶段 |
| 执行中需求 | `tblxLMQ8Ih5Gs5oM` | 正在开发的需求 |
| 发车中需求 | `tblPlaxVsLBvKMRl` | 已发布/上线中的需求 |
| Hotfix管理 | `tblzLyiFJtsYZRsN` | 紧急修复管理 |
| 需求Bug管理 | `tblkGH8uvmXS80CB` | 需求相关的Bug跟踪 |
| Sprint 版本计划 | `tblm2FGJjiK4frzt` | 版本迭代计划 |
| SSS级需求管理 | `tblvLgFVpQJDWXpp` | 待废弃 |
| 数据表 | `tblo2UCnfgHYb0aT` | 辅助数据 |

## 核心流程

```
┌─────────────────────────────────────────────────────────────────┐
│                    Tripo 需求管理流程                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   正常流程：                                                      │
│   产品需求池 ──→ 执行中需求 ──→ Sprint版本计划 ──→ 发车中需求     │
│       ↓           ↓              ↓               ↓              │
│     初筛       开发测试        部署发车        上线跟踪           │
│                                                                  │
│   问题流程：                                                      │
│   需求Bug管理 ──→ Hotfix管理 ──→ 独立发版/跟车发版                │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 1. 产品需求池

**Table ID**: `tblb9E9PQHP79JHE`

### 字段结构

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

### 状态字段说明

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

---

## 2. 执行中需求

**Table ID**: `tblxLMQ8Ih5Gs5oM`

### 字段结构

| 字段名 | Field ID | 类型 | 说明 |
|--------|----------|------|------|
| 状态 | `fldlb7BtiZ` | select | 需求执行状态 |
| 需求来源 | `fldymnWlrk` | select | 需求来源分类 |
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

### 状态字段说明

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

### 阶段进度字段

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

### 阶段进度选项值

各阶段进度字段（需求评审、技术评审、前端开发、后端开发等）通用选项：

| 选项 | 说明 |
|------|------|
| 未启动 | 尚未开始 |
| 不需要 | 无需此阶段 |
| 进行中 | 进行中 |
| 完成 | 已完成 |
| 风险 | 存在风险 |

---

## 3. Sprint 版本计划

**Table ID**: `tblm2FGJjiK4frzt`

### 字段结构

| 字段名 | Field ID | 类型 | 说明 |
|--------|----------|------|------|
| 版本计划 | `fldSJQfqQD` | text | 版本描述 |
| 班车状态 | `fldrcs9dZA` | select | 发车状态 |
| 上线类型 | `fldsqiHgP9` | select | 上线类型 |
| 版本Owner | `fld2eddfWB` | user | 版本负责人 |
| 前端发车owner | `fldsZ3XVVM` | user | 前端发车负责人 |
| 后端发车owner | `fld6iV4WQn` | user | 后端发车负责人 |
| 算法发车owner | `fld1E66DVA` | user | 算法发车负责人 |
| 预计发布日期 | `fldrnlaVAx` | datetime | 计划发布日期 |
| 实际发布日期 | `fldCaHckyx` | datetime | 实际发布日期 |
| 涉及项目 | `fld22nLpq1` | text | 涉及的项目 |
| 关联需求 | `fldM9DrUxr` | text | 关联的需求 |

### 状态字段说明

**班车状态** (`fldrcs9dZA`)

| 选项 | 说明 |
|------|------|
| 未启动 | 发车未开始 |
| 已启动 | 发车进行中 |
| 已完成 | 发车完成 |

**上线类型** (`fldsqiHgP9`)

| 选项 | 说明 |
|------|------|
| 跟车 | 常规发车 |
| hotfix | 紧急修复 |
| sss | SSS级紧急需求 |

### 部署状态字段

| 字段名 | Field ID | 类型 | 说明 |
|--------|----------|------|------|
| 前端部署完毕 | `fldy6ym5PN` | checkbox | 前端部署完成标记 |
| 后端部署完毕 | `fldWGA6C5g` | checkbox | 后端部署完成标记 |
| 算法部署完毕 | `fldDgrQRTd` | checkbox | 算法部署完成标记 |

---

## 4. Hotfix管理

**Table ID**: `tblzLyiFJtsYZRsN`

### 字段结构

| 字段名 | Field ID | 类型 | 说明 |
|--------|----------|------|------|
| 状态 | `fldlb7BtiZ` | select | Hotfix状态 |
| 需求类型 | `fldUF6s1nQ` | select | 类型分类 |
| 产品Owner | `fld8K6pMOg` | user | 产品负责人 |
| 研发Owner | `fldZMbDF8P` | user | 研发负责人 |
| 测试Owner | `fldv07SWgW` | user | 测试负责人 |
| SRE Owner | `fldkmmjFe7` | user | SRE负责人 |
| 开发人员 | `fld05KBpQ8` | user | 开发人员 |
| 问题描述 | `fldpGalbRG` | text | 问题描述 |
| 问题详情 | `fldXri4rgS` | text | 详细说明 |
| 附件 | `fldqbPzj9a` | attachment | 相关附件 |
| 需求引用 | `fldP6F6foD` | link | 关联需求 |
| 跟车版本 | `fldwf9csR1` | link | 关联版本 |

---

## 5. 需求Bug管理

**Table ID**: `tblkGH8uvmXS80CB`

### 字段结构

| 字段名 | Field ID | 类型 | 说明 |
|--------|----------|------|------|
| bugID | `fldeY0sN5p` | auto_number | 自动编号 |
| taskID/traceID | `fldEm1JpCR` | text | 任务/追踪ID |
| bug 描述 | `fld4JONHiA` | text | Bug描述 |
| 复现步骤 | `fld1A4hos0` | text | 复现步骤 |
| 进度 | `fldXOSCtZt` | select | Bug处理进度 |
| 优先级 | `fldkViwpfm` | select | 优先级 |
| 类型 | `fldvhQ0Hob` | select | Bug类型 |
| 发现阶段 | `fldb7fTV6H` | select | 发现阶段 |
| 指派人 | `fldVS07aUP` | user | 指派人员 |
| 创建人 | `fld1mMy65N` | created_by | 系统字段 |
| 创建日期 | `fldOKDPLYr` | created_at | 系统字段 |
| 关联需求 | `fldFVCn91G` | link | 关联需求 |
| 备注 | `fldemHmVhH` | text | 备注 |
| 附件 | `fldoROWfIe` | attachment | 附件 |

### 状态字段说明

**进度** (`fldXOSCtZt`)

| 选项 | 说明 |
|------|------|
| Open | 待处理 |
| In progress | 处理中 |
| Resolved | 已解决 |
| Closed | 已关闭 |
| Not bug | 非Bug |
| Delay | 延期处理 |
| Crash | 崩溃问题 |
| Reopened | 重新打开 |

**优先级** (`fldkViwpfm`)

| 选项 | 说明 |
|------|------|
| P0 | 最高优先级 |
| P1 | 高优先级 |
| P2 | 普通优先级 |

---

## 二、技术需求一览表

| 属性 | 信息 |
|------|------|
| **名称** | 技术需求一览表 |
| **链接** | https://a9ihi0un9c.feishu.cn/wiki/SpxCwqWVeiYQvhkXW6FcJwB6nwc |
| **Base Token** | `OCNcbuwpta7qc7sxAPOcSpngnbg` |
| **数据表数量** | 1 个 |

### 数据表列表

| 表名 | Table ID | 说明 |
|------|----------|------|
| 技术需求管理 | `tblkb1Saexm0njaE` | 技术需求管理 |

### 技术需求管理

**Table ID**: `tblkb1Saexm0njaE`

#### 字段结构

| 字段名 | Field ID | 类型 | 说明 |
|--------|----------|------|------|
| 一句话描述需求 | `fldSJQfqQD` | text | 简要描述 |
| 需求详细描述 | `fldQ2spTUo` | text | 详细描述（可附文档） |
| 技术文档 | `fldjaF5fXE` | text | 技术文档链接 |
| 需求提出日期 | `fldl4EsNYi` | datetime | 提出日期 |
| 预期交付时间 | `fldahODYXi` | datetime | 预期交付 |
| 实际交付时间 | `fldDJCyFl7` | datetime | 实际交付 |
| 需求状态 | `fldrcs9dZA` | select | 当前状态 |
| 绝对优先级 | `fldEoiYN2X` | select | 优先级 |
| 需求池 | `fldboFiGvi` | select | 分类 |
| 是否发版 | `fldeSFpLSJ` | select | 是否需要发版 |
| 需求Owner | `fldeFXWrBP` | user | 需求负责人 |
| 研发Owner | `fldcrC0dNU` | user | 研发负责人 |
| Member | `fldsr1pwhD` | user | 团队成员 |
| 创建人 | `fldWRUzUPb` | created_by | 系统字段 |
| 跟进群 | `fldsHHxR8i` | not_support | - |

#### 状态字段说明

**需求状态**、**绝对优先级**、**需求池** 字段选项与产品需求池一致。