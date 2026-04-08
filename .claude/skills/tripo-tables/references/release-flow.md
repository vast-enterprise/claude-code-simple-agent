# 发车流程全景

> 基于飞书多维表格 Tripo 需求一览表 + 技术需求一览表。

## 需求来源 → 执行中需求

```
产品需求池 ──[需求准入确认]──→ 执行中需求
技术需求管理 ──[需求准入确认]──→ 执行中需求
```

两个需求池都通过「需求准入确认」按钮将需求推入执行中需求表。

## 需求上线三条路径

### 路径 1：发车准入（搭公交）

- **workflow**: `wkfCTuzpHvY4FghE`（需求准出确认）
- **触发**: 执行中需求表 → 点击「发车准入」按钮
- **动作**: 搭上已有班车（查找班车状态=已启动、上线类型=跟车的版本）
- **结果**:
  - 发车中需求新增记录，状态=待上线（排队等统一发车）
  - 执行中需求状态 → 完成
  - 产品需求池状态 → 验收/提测中，关联版本
- **后续**: 等版本 Owner 点「启动发车」统一推进

### 路径 2：临时发车（打专车，SSS 紧急）

- **workflow**: `wkfufcEDGQeXQfTF`（临时发车确认）
- **触发**: 执行中需求表 → 点击「临时发车确认」按钮
- **动作**: 创建新版本（上线类型=sss），跳过排队
- **结果**:
  - Sprint 版本计划新增记录（上线类型=sss，班车状态=已启动）
  - 发车中需求新增记录，状态=上线中（直接进入部署）
  - 执行中需求状态 → 完成
  - 产品需求池状态 → 验收/提测中
- **后续**: 直接进入部署流程

### 路径 3：Hotfix（Bug 修复快车）

- **workflow**: `wkf1daTXkGSUjGLY`（创建发车hotfix）
- **触发**: 执行中需求表 → 点击「创建发车hotfix」按钮
- **动作**: 创建新版本（上线类型=hotfix）
- **适用**: Bug 修复

## 发车后的部署流程

### 启动发车

- **workflow**: `wkf9ICnGBZyU2G0R`
- **触发**: Sprint 版本计划 → 点击「启动发车」按钮
- **动作**: 该版本下所有"待上线"需求 → "上线中"，通知跟进群

### 接力式部署（自动监控）

- **workflow**: `wkfiXUddmigXTMvK`（发车流程监控）
- **触发**: SetRecordTrigger，监控 Sprint 版本计划的 3 个 checkbox
- **流程**:

```
算法部署完毕 ✓ → 通知群，附"后端部署完毕"按钮
  → 后端部署完毕 ✓ → 通知群，附"前端部署完毕"按钮
    → 前端部署完毕 ✓ → 通知群，附"提交 hotfix"按钮
```

### 发版完成确认

- **workflow**: `wkfv7lNEMo3XlRlR`
- **触发**: Sprint 版本计划 → 点击「发车完毕」按钮
- **动作**:
  - 发车中需求：上线中 → 完成
  - Hotfix管理：关联记录 → 完成
  - 产品需求池：→ 已完成
  - Sprint 版本计划：班车状态 → 已完成

## 前端开发视角的关键节点

1. **开发完成**: 执行中需求.`前端开发` → 完成
2. **自测闭环**: 开发者自测，不等同正式功能测试
3. **上线**:
   - 判断路径（跟车 / SSS / hotfix）
   - 执行需求准出（写入发车中需求）
   - 触发前端 GitHub Actions 部署
   - 勾选 Sprint 版本计划的「前端部署完毕」checkbox
   - 飞书通知

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
| `wkfEdyvotjKQHMr6` | 每周创建发车版本 | TimerTrigger（每周） | 自动创建本周班车 |
| `wkftpEooZBMc2AUa` | 需求准入确认 | ButtonTrigger | 产品需求池 → 执行中需求 |
| `wkfCTuzpHvY4FghE` | 需求准出确认 | ButtonTrigger | 执行中需求 → 发车中需求（跟车） |
| `wkfufcEDGQeXQfTF` | 临时发车确认 | ButtonTrigger | SSS 紧急通道 |
| `wkf1daTXkGSUjGLY` | 创建发车hotfix | ButtonTrigger | Hotfix 通道 |
| `wkf9ICnGBZyU2G0R` | 启动发车 | ButtonTrigger | 待上线 → 上线中 |
| `wkfiXUddmigXTMvK` | 发车流程监控 | SetRecordTrigger | 监控 3 个 checkbox 接力通知 |
| `wkfQpKcvFM3J7v10` | 发版信息同步 | ButtonTrigger | 添加群成员，通知发车信息 |
| `wkfv7lNEMo3XlRlR` | 发版完成确认 | ButtonTrigger | 上线中→完成，需求池→已完成 |
| `wkfDZswkBew4cDpN` | 每日执行中需求状态同步 | TimerTrigger | 每日同步状态 |
