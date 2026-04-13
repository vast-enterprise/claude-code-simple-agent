# 集成测试计划: CMS Access Control Cleanup

**需求**: REQ-recvgEMX94PBfc
**测试日期**: 2026-04-14

## 测试环境

- **方法**: Payload Local API (`overrideAccess: false` + `user` 参数模拟角色)
- **数据库**: MongoDB (payload-tripo-cms-dev)
- **框架**: Vitest
- **文件**: `tests/int/access-control.int.spec.ts`

## 测试用户

| 角色 | 邮箱 | 用途 |
|------|------|------|
| super-admin | test-super-admin@int-test.local | 最高权限验证 |
| admin | test-admin@int-test.local | 管理员权限验证 |
| editor | test-editor@int-test.local | 编辑受限验证 |

## 测试场景

### 场景 1: Users.create 权限 (adminOnly)

对齐子项 2+3：endpoint 权限重构 + 邮箱移除后，Users 创建仍按角色判断。

| # | 操作 | 角色 | 预期 |
|---|------|------|------|
| 1.1 | create user | super-admin | 成功 |
| 1.2 | create user | admin | 成功 |
| 1.3 | create user | editor | Forbidden |

### 场景 2: Posts 发布权限 (restrictEditorPublish)

对齐子项 4：editor 只能保存草稿，不能发布。

| # | 操作 | 角色 | 预期 |
|---|------|------|------|
| 2.1 | update draft | editor | 成功 |
| 2.2 | publish (_status=published) | editor | 抛出 '编辑角色无法发布内容' |
| 2.3 | publish | admin | 成功，_status=published |
| 2.4 | publish | super-admin | 成功 |
| 2.5 | publish | 无 user (Local API/cron) | 成功，不受限制 |

**注意**: 创建 post 需要 `content` (Lexical richText) + `contentType` 字段。

### 场景 3: GeoPosts 发布权限 (restrictEditorPublish)

与 Posts 相同的 hook，验证行为一致。

| # | 操作 | 角色 | 预期 |
|---|------|------|------|
| 3.1 | update draft | editor | 成功 |
| 3.2 | publish | editor | 抛出 '编辑角色无法发布内容' |
| 3.3 | publish | admin | 成功 |
| 3.4 | publish | super-admin | 成功 |

**注意**: geo-posts 需要唯一 `slug`，用 `int-test-geo-${Date.now()}` 避免冲突。

### 场景 4: Pages 发布权限 (restrictEditorPublish)

Pages 也注册了同一 hook，验证三个集合行为一致。

| # | 操作 | 角色 | 预期 |
|---|------|------|------|
| 4.1 | update draft | editor | 成功 |
| 4.2 | publish | editor | 抛出 '编辑角色无法发布内容' |
| 4.3 | publish | admin | 成功 |
| 4.4 | publish | super-admin | 成功 |

**注意**: Pages 需要 `title` (required) + `layout` (required blocks)。`layout` 最小数据为 Content block:
```json
[{ "blockType": "content", "columns": [{ "size": "full", "richText": MINIMAL_LEXICAL_CONTENT }] }]
```

**已知风险**: Pages 的 `afterChange` hook (`revalidatePage`) 调用 Next.js `revalidatePath`，在纯 Local API 环境中无 static generation store 会抛 Invariant Error。需要 vi.mock 该 hook 或整个 `next/cache` 模块。

### 场景 5: 邮箱不再有特权 (回归验证)

对齐子项 3：删除邮箱硬编码后，权限完全取决于角色。

| # | 操作 | 角色+邮箱 | 预期 |
|---|------|-----------|------|
| 5.1 | create user | editor + tripo-cms@vastai3d.com | Forbidden（按角色） |
| 5.2 | create user | super-admin + tripo-cms@vastai3d.com | 成功（按角色） |

### 场景 6: DataBackfill Global 权限 (superAdminOnly)

对齐子项 1：修复 hidden bug 后，仅 super-admin 可访问。

| # | 操作 | 角色 | 预期 |
|---|------|------|------|
| 6.1 | findGlobal | super-admin | 成功 |
| 6.2 | findGlobal | admin | Forbidden |
| 6.3 | findGlobal | editor | Forbidden |

## 验证指标

- 每个场景通过 = Vitest assert 通过
- 测试产物 = `pnpm vitest run` 全量输出
- 覆盖完整 = technical-solution.md 矩阵中所有单元格均有对应用例

## 降级说明

- 场景 4 (Pages) 如因 `revalidatePath` Invariant Error 无法直接测试，需 mock `next/cache`。若 mock 后仍失败，标记 DEFERRED 并说明原因。
- 定时发布场景：Payload Jobs 系统内部触发，场景 2.5 (无 user) 已间接覆盖。
