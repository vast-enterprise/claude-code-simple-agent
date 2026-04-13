# 技术方案：CMS 系统权限规整

## 需求概述

| 项目 | 值 |
|------|-----|
| 需求 ID | recvgEMX94PBfc |
| 涉及仓库 | tripo-cms（Payload CMS 3.69+ / Next.js 15） |
| 子项数量 | 4 |

## 现状分析

### 权限体系架构

```
角色层级: super-admin > admin > editor
服务账号: tripo-cms@vastai3d.com（当前通过邮箱硬编码享有特权，应废除）

src/access/
├── anyone.ts              # () => true
├── authenticated.ts       # Boolean(user)
├── admin-only.ts          # super-admin || admin || 邮箱判断（待清理）
├── admin-or-self.ts       # admin 全部，普通用户仅自己
├── super-admin-only.ts    # super-admin || 邮箱判断（待清理）
├── authenticatedOrPublished.ts  # 登录=全部，匿名=仅 published
└── hide-from-editor.ts    # admin.hidden 专用，editor 返回 true（隐藏）
```

### 核心问题

权限判断中混入了邮箱硬编码，这是错误的设计——**权限应该且只应该基于角色（role）判断**。服务账号如需特权，应在数据库中将其 role 设为 `super-admin`，而非在代码中用邮箱做特殊通道。

## 子项 1：DataBackfill hidden Bug

### 根因

`src/globals/data-backfill.ts:13`：

```ts
hidden: !superAdminOnly  // Bug: superAdminOnly 是函数引用，truthy，!truthy = false
```

`superAdminOnly` 是函数，JS 中函数是 truthy 值，`!superAdminOnly` 恒为 `false`，即**永远不隐藏**。

### 方案

将 `hidden: !superAdminOnly` 改为 `hidden: hideFromEditor`。

- `hideFromEditor` 签名 `({ user }) => boolean`，与 `admin.hidden` 要求匹配
- editor → 隐藏（true），admin/super-admin → 显示（false）
- `access.read/update` 仍为 `superAdminOnly`，admin 能看到入口但操作受限

**改动量**：1 行 + 1 行 import

## 子项 2：Endpoint 权限重构

### 现状对比

| Endpoint | 当前逻辑 | 问题 |
|----------|---------|------|
| `blog-import` | `!user` → 401 | 任何已登录用户可调用，包括 editor |
| `migrate-post` | 内联 `role !== 'super-admin' && role !== 'admin'` | 内联硬编码，未复用 access 函数 |
| `data-backfill/execute` | 内联 role + 邮箱三元判断 | 与 `adminOnly` 逻辑重复 + 邮箱硬编码 |
| `data-backfill/rollback` | 同 execute | 同上 |

### 方案

创建通用的 endpoint 权限检查工具函数，复用已有的 `adminOnly`：

```ts
// src/access/check-endpoint-access.ts
import { adminOnly } from './admin-only'

export const checkAdminEndpoint = (req: PayloadRequest): Response | null => {
  if (!req.user) {
    return Response.json({ error: 'Unauthorized' }, { status: 401 })
  }
  if (!adminOnly({ req })) {
    return Response.json({ error: 'Forbidden' }, { status: 403 })
  }
  return null  // 通过
}
```

各 endpoint 统一改为：

```ts
const rejected = checkAdminEndpoint(req)
if (rejected) return rejected
```

| Endpoint | 改动 |
|----------|------|
| `blog-import` | 加 `checkAdminEndpoint`（收紧为仅 admin+） |
| `migrate-post` | 内联判断 → `checkAdminEndpoint` |
| `execute` | 内联判断 → `checkAdminEndpoint` |
| `rollback` | 内联判断 → `checkAdminEndpoint` |

**注意**：`geo-posts-months` 是公开接口，不加权限。

**改动量**：新建 1 文件 + 修改 4 文件

## 子项 3：删除邮箱硬编码，纯角色判断

### 设计原则

**权限判断只基于 `user.role`，不基于 `user.email`。** 这是正确的 RBAC 设计。

服务账号 `tripo-cms@vastai3d.com` 如需 super-admin 权限，应在数据库中将其 role 字段设为 `super-admin`（一次性数据修复），而非在代码中开后门。

### 分布（待删除的邮箱判断）

| 文件 | 行 | 当前逻辑 | 改动 |
|------|-----|---------|------|
| `src/access/admin-only.ts:11` | `user.email === 'tripo-cms@...'` | 删除，仅保留 role 判断 |
| `src/access/super-admin-only.ts:8` | `user.email === 'tripo-cms@...'` | 删除，仅保留 role 判断 |
| `src/access/hide-from-editor.ts:10` | `user.email === 'tripo-cms@...'` | 删除，仅保留 role 判断 |
| `src/endpoints/data-backfill/execute.ts:14` | 权限内联邮箱判断 | 子项 2 重构后自动消除 |
| `src/endpoints/data-backfill/execute.ts:95` | 角色赋值业务逻辑中的邮箱判断 | 改为判断 `user.role === 'super-admin'` |
| `src/endpoints/data-backfill/rollback.ts:14` | 权限内联邮箱判断 | 子项 2 重构后自动消除 |

### 前置数据修复

确认服务账号 `tripo-cms@vastai3d.com` 在 Users collection 中的 role 为 `super-admin`。如果不是，需先更新：

```bash
# 查询当前角色
curl -s http://localhost:3000/api/users?where[email][equals]=tripo-cms@vastai3d.com | jq '.docs[0].role'
```

### 改动后的 access 函数

```ts
// src/access/admin-only.ts（改动后）
export const adminOnly = ({ req: { user } }: { req: { user: User } }) => {
  return user?.role === 'super-admin' || user?.role === 'admin'
}

// src/access/super-admin-only.ts（改动后）
export const superAdminOnly = ({ req: { user } }: { req: { user: User } }) => {
  return user?.role === 'super-admin'
}

// src/access/hide-from-editor.ts（改动后）
export const hideFromEditor = ({ user }: { user: User }) => {
  return user?.role !== 'super-admin' && user?.role !== 'admin'
}
```

**改动量**：修改 3 个 access 文件 + execute.ts 1 处业务逻辑

## 子项 4：Editor 发布收紧（双层防护）

### 社区调研结论

| 方案 | 可行性 | 问题 |
|------|--------|------|
| A: `beforeChange` hook 拦截 | ✅ 推荐 | 后端安全保证，社区一致认可 |
| B: collection `access.update` 区分 _status | ⚠️ 有 Bug | Issue #15312：save 按钮消失（3.69 仍未修复） |
| C: field-level access on `_status` | ❌ 不可行 | `_status` 是 Payload 内部字段，无法声明 field access |
| D: 自定义 PublishButton RSC 组件 | ✅ UX 增强 | 仅 UI 层，需配合后端方案 |
| E: `access.update` 返回 where 条件 | ⚠️ 有副作用 | editor 无法修改已发布文档的新草稿版本 |

**参考来源**：
- [GitHub Issue #6580](https://github.com/payloadcms/payload/issues/6580) – Publish Button Visibility
- [GitHub Issue #15312](https://github.com/payloadcms/payload/issues/15312) – Cannot save after publish with access rules（open）
- [Community Help: Access Control for Unpublishing](https://payloadcms.com/community-help/github/access-control-for-unpublishing)
- [GitHub Discussion #1009](https://github.com/payloadcms/payload/discussions/1009) – Add publish access control

### 推荐方案：A + D 双层防护

| 层 | 方案 | 作用 |
|----|------|------|
| **后端（必须）** | beforeChange hook + `APIError` | 拦截发布请求，API 安全 |
| **前端（体验）** | 自定义 PublishButton RSC | 对 editor 隐藏发布按钮 |

### 后端：beforeChange hook

```ts
// src/hooks/restrict-editor-publish.ts
import { APIError } from 'payload'
import type { CollectionBeforeChangeHook } from 'payload'

export const restrictEditorPublish: CollectionBeforeChangeHook = ({ data, req }) => {
  const isEditor = req.user?.role === 'editor'
  if (isEditor && (data?._status === 'published' || data?.schedulePublishAt)) {
    throw new APIError('编辑角色无法发布内容，请联系管理员发布', 403)
  }
  return data
}
```

在 Posts、GeoPosts、Pages 三个 collection 的 `hooks.beforeChange` 中注册。

### 前端：自定义 PublishButton

```ts
// src/components/publish-button.tsx（RSC）
import { DefaultPublishButton } from '@payloadcms/ui'

export const AdminOnlyPublishButton = async (props) => {
  // RSC 组件中可直接访问 user
  const { user } = props
  if (user?.role === 'editor') return null  // editor 不显示发布按钮
  return <DefaultPublishButton {...props} />
}
```

在 Posts/GeoPosts/Pages 的 `admin.components.edit.PublishButton` 中注册。

### 定时发布兼容

- cron 任务通过 Local API（`overrideAccess: true`）触发，不受 hook 影响
- editor 提交定时发布请求时，hook 检查 `data?.schedulePublishAt` 并拦截

**改动量**：新建 2 文件（hook + component）+ 修改 3 个 collection

## 附加项：llmdoc 文档对齐

Users Collection 的 `read` 权限实际为 `authenticated`，llmdoc 记录为 `adminOrSelf`，需更新文档与代码对齐。

**改动量**：更新 llmdoc 1 处

## 工作量评估

| 子项 | 预估 | 说明 |
|------|------|------|
| Bug 修复（子项 1） | 0.5h | 1 行改动 + 测试 |
| Endpoint 重构（子项 2） | 2h | 新建工具函数 + 改 4 个 endpoint + 测试 |
| 删除邮箱硬编码（子项 3） | 1h | 改 3 个 access 函数 + 1 处业务逻辑 + 确认服务账号角色 |
| Editor 发布收紧（子项 4） | 3h | hook + RSC 组件 + 改 3 个 collection + 测试 |
| 测试 & 验证 | 1.5h | 各角色端到端权限验证 |
| **合计** | **8h（约 1 天）** | |

**计划提测时间**：2026-04-15（启动 + 2 工作日）

## 风险评估

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| 服务账号 role 不是 super-admin | 中 | 删除邮箱判断后服务账号失去权限 | 上线前确认并修复 DB 中的 role |
| Issue #15312 影响 editor 保存 | 低 | 我们用 hook 而非 access.update，不受此 bug 影响 | 已规避 |
| 定时发布绕过 | 低 | hook 同时检查 schedulePublishAt | 已覆盖 |
| 自定义 PublishButton 与 Payload 升级兼容 | 低 | RSC 组件 API 可能变更 | 遵循官方文档写法，升级时检查 |

## 测试计划

### 单元测试

| 测试项 | 验证内容 |
|--------|---------|
| `adminOnly` | super-admin ✓、admin ✓、editor ✗、未登录 ✗ |
| `superAdminOnly` | super-admin ✓、admin ✗、editor ✗ |
| `checkAdminEndpoint` | 复用 adminOnly，返回 Response 或 null |
| `restrictEditorPublish` | editor+published ✗、editor+draft ✓、admin+published ✓、editor+schedulePublishAt ✗ |
| 零硬编码邮箱 | `grep -r "tripo-cms@vastai3d.com" src/` 零结果 |

### 集成测试

| 角色 | DataBackfill | blog-import | 发布文章 | 定时发布 | Users 列表 |
|------|-------------|-------------|---------|---------|-----------|
| super-admin | 可见+可操作 | ✓ | ✓ | ✓ | 可见+可改 |
| admin | 可见+操作受限 | ✓ | ✓ | ✓ | 可见+可改 |
| editor | 不可见 | ✗ (403) | ✗ (仅草稿) | ✗ | 可见+不可改 |
| 服务账号 | 按 role 判断 | 按 role 判断 | 按 role 判断 | 按 role 判断 | 按 role 判断 |

## 执行顺序

```
子项 3（删除邮箱硬编码）→ 子项 1（Bug 修复）→ 子项 2（Endpoint 重构）→ 子项 4（发布收紧）
```

先清理 access 函数（子项 3），后续子项基于纯 role 判断；Bug 修复最简单先出；Endpoint 重构复用干净的 access 函数；发布收紧独立性最强放最后。
