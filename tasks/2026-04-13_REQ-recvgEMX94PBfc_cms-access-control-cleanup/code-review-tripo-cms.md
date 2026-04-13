# Code Review: tripo-cms refactor/access-control-cleanup

**审查时间**: 2026-04-14
**分支**: refactor/access-control-cleanup (6 commits, 15 files, +462/-75)
**裁决**: APPROVE（附建议）

## 前次 Review 修复验证

| 编号 | 问题 | 状态 |
|------|------|------|
| C1: schedulePublishAt 不存在 | hook 中无此字段引用 | **已修复** |
| I1: checkAdminEndpoint unsafe type assertion | 改为直接读 req.user.role | **已修复** |
| I2: execute.ts 死逻辑 | 改为 `const role = 'editor' as const` | **已修复** |

## 新发现

### HIGH

**H1: hideFromEditor 对 null user 返回 true（隐藏）**
- 文件: `src/access/hide-from-editor.ts`
- 判定: 安全，未登录用户看不到后台导航项，行为正确
- 动作: **无需修改**

**H2: data-backfill endpoint 权限为 adminOnly，但 Global access 为 superAdminOnly**
- 文件: `src/endpoints/data-backfill/execute.ts`, `rollback.ts`
- 说明: endpoint 允许 admin 调用，但 Global UI 只有 super-admin 可见。这是重构前就存在的行为，非回归
- 动作: **确认是否需要提升 endpoint 权限到 superAdminOnly**

**H3: restrictEditorPublish 与 schedulePublish 兼容性**
- 文件: `src/hooks/restrict-editor-publish.ts`
- 判定: 定时发布由内部 cron 触发，req.user 为 null，不会被拦截。集成测试已验证
- 动作: **无需修改**

### MEDIUM

**M1: 4 个 endpoint 中 `user!` 非空断言**
- 文件: blog-import/index.ts, execute.ts, rollback.ts, migrate-post/index.ts
- 说明: checkAdminEndpoint 已验证 user 非空，但 TS 不知道。逻辑安全，建议后续迭代改为类型守卫
- 动作: **不阻塞合入**

**M2: 权限错误与业务错误 response 格式不一致**
- 说明: checkAdminEndpoint 返回 `{ success, error }`，validate.ts 返回 `{ success, error, message }`
- 动作: **不阻塞合入**

**M3: 集成测试缺 Pages 集合覆盖**
- 说明: Posts/GeoPosts 有测试，Pages 也挂了 hook 但无测试
- 动作: **8.3 中补充**

### LOW

- L1: checkAdminEndpoint 命名建议改为 requireAdminForEndpoint
- L2: execute.ts 注释编号缺步骤 1

## 硬编码邮箱验证

`src/` 目录搜索 `tripo-cms@vastai3d.com` 结果：**零命中**，清理彻底。

## 结论

安全相关变更逻辑正确，无 CRITICAL 问题，APPROVE。H2 需 owner 确认 data-backfill endpoint 权限级别。
