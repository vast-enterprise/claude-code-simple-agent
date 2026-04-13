# 集成测试验证报告

**需求**: REQ-recvgEMX94PBfc (CMS Access Control Cleanup)
**测试日期**: 2026-04-14
**测试文件**: `tests/int/access-control.int.spec.ts`

## 测试环境

- Payload CMS 3.69 + Next.js 15
- MongoDB: payload-tripo-cms-dev
- Vitest 4.0.16
- 方法: Payload Local API (`overrideAccess: false` + `user` 参数)

## 测试结果

```
Test Files  8 passed (8)
     Tests  73 passed (73)
  Duration  1.61s
```

### 场景 1: Users.create 权限 (adminOnly)

| # | 用例 | 状态 |
|---|------|------|
| 1.1 | super-admin 可以创建用户 | ✅ PASS |
| 1.2 | admin 可以创建用户 | ✅ PASS |
| 1.3 | editor 不能创建用户 → Forbidden | ✅ PASS |

### 场景 2: Posts 发布权限 (restrictEditorPublish)

| # | 用例 | 状态 |
|---|------|------|
| 2.1 | editor 可以保存草稿 | ✅ PASS |
| 2.2 | editor 发布 → 被 hook 拦截 | ✅ PASS |
| 2.3 | admin 发布 → 成功 | ✅ PASS |
| 2.4 | super-admin 发布 → 成功 | ✅ PASS |
| 2.5 | Local API 无 user (cron) → 不受限制 | ✅ PASS |

### 场景 3: GeoPosts 发布权限 (restrictEditorPublish)

| # | 用例 | 状态 |
|---|------|------|
| 3.1 | editor 可以保存 geo-post 草稿 | ✅ PASS |
| 3.2 | editor 发布 geo-post → 被 hook 拦截 | ✅ PASS |
| 3.3 | admin 发布 geo-post → 成功 | ✅ PASS |
| 3.4 | super-admin 发布 geo-post → 成功 | ✅ PASS |

### 场景 4: Pages 发布权限 (restrictEditorPublish)

| # | 用例 | 状态 | 备注 |
|---|------|------|------|
| 4.1 | editor 可以保存 page 草稿 | ✅ PASS | context.disableRevalidate 绕过 next/cache |
| 4.2 | editor 发布 page → 被 hook 拦截 | ✅ PASS | |
| 4.3 | admin 发布 page → 成功 | ✅ PASS | |
| 4.4 | super-admin 发布 page → 成功 | ✅ PASS | |

### 场景 5: 邮箱不再有特权 (回归验证)

| # | 用例 | 状态 |
|---|------|------|
| 5.1 | editor + 服务账号邮箱 → 不能创建用户 | ✅ PASS |
| 5.2 | super-admin + 服务账号邮箱 → 可以创建用户 | ✅ PASS |

### 场景 6: DataBackfill Global 权限 (superAdminOnly)

| # | 用例 | 状态 |
|---|------|------|
| 6.1 | super-admin 可以读取 | ✅ PASS |
| 6.2 | admin 不能读取 → Forbidden | ✅ PASS |
| 6.3 | editor 不能读取 → Forbidden | ✅ PASS |

## 修复的问题

| 时间 | 问题 | 修复 |
|------|------|------|
| 编码阶段 | C1: schedulePublishAt 不存在 | 删除该条件 |
| 编码阶段 | I1: checkAdminEndpoint unsafe assertion | 重写为内联 role check |
| 编码阶段 | I2: backfill 死逻辑 | 改为 `const role = 'editor' as const` |
| 测试阶段 | Posts 发布需要 Lexical content | 添加 MINIMAL_LEXICAL_CONTENT 常量 |
| 测试阶段 | GeoPosts 需要唯一 slug | 使用 Date.now() 生成 |
| 测试阶段 | Pages revalidatePath 无 Next.js 运行时 | 使用 context.disableRevalidate |
| 测试阶段 | migrate-post 错误消息变更 | 更新断言匹配新消息 |

## DEFERRED 项

无。所有测试计划场景均已执行并通过。

## 结论

21 个集成测试用例覆盖 6 个场景，全部通过。邮箱硬编码已彻底清除（`grep -r "tripo-cms@vastai3d.com" src/` 零结果）。三个集合 (Posts/GeoPosts/Pages) 的发布限制行为一致。
