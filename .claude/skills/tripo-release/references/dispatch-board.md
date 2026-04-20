# 发车班车业务流程

> **定位**：发车编排视角的业务流程全景。数据字典（option_id、workflow_id、checkbox 字段 ID、lark-cli 业务参数）见 `tripo-tables/references/release-flow.md`。

## 需求来源 → 可发车

```
产品需求池 ──[需求准入确认]──→ 执行中需求 ──(开发/测试完成、staging 验收通过)──→ 发车候选
技术需求管理 ──[需求准入确认]──→ 执行中需求 ──(同上)──────────────────────→ 发车候选
```

一个需求在 staging 验收通过后成为「发车候选」,但**不立即发车**。发车是独立触发的动作,由用户或 scrum-master 在合适的时机统一汇总、统一发车。

## 三条发车路径

### 路径 1:跟车(搭班车)

- **场景**:常规 Sprint 需求,搭已启动的每周班车
- **触发 workflow**:`wkfCTuzpHvY4FghE`(需求准出确认)—— 执行中需求表「发车准入」按钮
- **动作**:
  - 查找班车状态=已启动、上线类型=跟车的 Sprint 版本
  - 发车中需求新增记录,状态=待上线(排队等统一发车)
  - 执行中需求状态 → 完成
  - 产品需求池状态 → 验收/提测中,关联版本
- **后续**:等版本 Owner 点「启动发车」统一推进

### 路径 2:临时发车(SSS 紧急)

- **场景**:SSS 级需求,跳过排队
- **触发 workflow**:`wkfufcEDGQeXQfTF`(临时发车确认)—— 执行中需求表「临时发车确认」按钮
- **动作**:
  - Sprint 版本计划新增记录(上线类型=sss,班车状态=已启动)
  - 发车中需求新增记录,状态=上线中(直接进入部署)
  - 执行中需求 + 产品需求池同跟车后半段
- **后续**:直接进入部署流程

### 路径 3:Hotfix(Bug 修复专车)

- **场景**:Bug 修复需紧急上线
- **触发 workflow**:`wkf1daTXkGSUjGLY`(创建发车hotfix)—— 执行中需求表「创建发车hotfix」按钮
- **动作**:创建新版本(上线类型=hotfix)
- **适用**:bugfix 流程走到发车候选后走此路径

## 启动发车 → 接力部署 → 完成确认

### 启动发车

- **workflow**:`wkf9ICnGBZyU2G0R`
- **触发**:Sprint 版本计划「启动发车」按钮
- **动作**:该版本下所有「待上线」需求 → 「上线中」,通知跟进群

### 接力式部署(自动监控)

- **workflow**:`wkfiXUddmigXTMvK`(发车流程监控)
- **触发**:SetRecordTrigger,监控 Sprint 版本计划的 3 个 checkbox

```
算法部署完毕 ✓ → 通知群,附「后端部署完毕」按钮
  → 后端部署完毕 ✓ → 通知群,附「前端部署完毕」按钮
    → 前端部署完毕 ✓ → 通知群,附「提交 hotfix」按钮
```

### 发版完成确认

- **workflow**:`wkfv7lNEMo3XlRlR`
- **触发**:Sprint 版本计划「发车完毕」按钮
- **动作**:
  - 发车中需求:上线中 → 完成
  - Hotfix 管理:关联记录 → 完成
  - 产品需求池:→ 已完成
  - Sprint 版本计划:班车状态 → 已完成

## 前端开发视角的关键节点

1. **staging 验收通过** —— 成为发车候选,但**不自己发车**;等用户/scrum-master 统一汇总
2. **用户决定发车** —— scrum-master 查当前班车状态,汇总上车需求
3. **判断路径**:跟车 / SSS / hotfix
4. **执行需求准出**:写入发车中需求(lark-cli 参数见 tripo-tables/references/release-flow.md)
5. **触发前端 GitHub Actions 部署**(→ tripo-repos 查 workflow 名、域名)
6. **curl 验证部署成功**
7. **勾 Sprint 版本计划的「前端部署完毕」checkbox**(→ scrum-master 执行,字段 ID 见 tripo-tables/references/release-flow.md)
8. **飞书通知**(→ tripo-notify R3/R4 节点)

## lark-cli 操作参数

所有记录的增改查 → 调用 **lark-base skill**(`+record-list` / `+record-upsert` / `+record-update`)。
本文件只描述业务流程和触发时机;具体 option_id / Workflow ID / 字段 ID 见 **tripo-tables/references/release-flow.md**。
