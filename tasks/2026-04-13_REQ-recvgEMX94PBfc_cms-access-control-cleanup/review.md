# 需求评审：CMS 系统权限规整

## 需求来源

| 项目 | 值 |
|------|-----|
| 需求 ID | recvgEMX94PBfc |
| 描述 | CMS 系统权限规整 |
| Owner | 郭凯南 |
| 来源 | 研发自提（代码审查中发现权限体系不一致） |
| 涉及仓库 | tripo-cms |

## 需求范围

### 核心功能（4 项）

**1. 修复已知 Bug**
- DataBackfill Global 的 `admin.hidden: !superAdminOnly` 恒为 `false`，所有角色都能看到入口
- Users Collection 的 `read` 权限是 `authenticated`，保持不变（Editor 需要能看到所有用户列表）；llmdoc 记录为 `adminOrSelf` 与实际不符，需更新文档对齐代码

**2. Endpoint 权限重构**
- 4 个自定义 Endpoint 内联了权限检查逻辑，与 `src/access/` 函数重复
- `blog-import` 仅检查 `authenticated`，任何登录用户可导入
- `migrate-post` 缺少硬编码邮箱判断，与 `adminOnly` 行为不一致
- `data-backfill/execute` 和 `rollback` 重复内联 admin + 邮箱检查

**3. 硬编码邮箱提取常量**
- `tripo-cms@vastai3d.com` 出现在 5 个文件 7 处
- 作用：CMS 系统服务账号，享有 super-admin 等价权限
- 提取为 `src/constants/auth.ts` 中的常量

**4. Editor 权限收紧**
- 当前 Posts/GeoPosts/Pages 的 create/update/delete 均为 `authenticated`
- Editor 可以发布文章（修改 `_status` 为 `published`）
- 目标：Editor 只能编辑和创建草稿，不能发布

### 边界条件

- `geo-posts-months` Endpoint 是公开接口，不加权限检查
- `app-config` Global 的 read 保持 `() => true`（前端需要读取 feature flag）
- 不改变 `super-admin` / `admin` 的现有权限

### 不包含

- 不新增角色
- 不修改 Admin Panel UI
- 不变更数据库 Schema

## 验收标准

| 子项 | 验收标准 |
|------|---------|
| Bug 修复 | DataBackfill 入口对 Editor 不可见；Users 列表 Editor 能看到所有用户但不能修改他人信息；llmdoc 文档与代码对齐 |
| Endpoint 重构 | 所有 Endpoint 复用 `src/access/` 函数，不再内联角色判断 |
| 常量提取 | `tripo-cms@vastai3d.com` 零硬编码，全部引用常量 |
| Editor 发布 | Editor 可创建/编辑草稿，点击「发布」无效或被拦截 |

## 技术约束

- Payload CMS 3.x 的访问控制机制（Collection access + Field access + Hook）
- `_status` 字段由 Payload 的 versions/drafts 系统自动管理，需要确认 Payload 是否支持字段级 access 控制 `_status`
- 如果 Payload 不支持直接控制 `_status` 字段的 access，需要用 `beforeChange` hook 拦截

## 合规风险

无外部平台政策冲突。纯内部权限系统变更。

## 问题与风险

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| Editor 发布拦截的技术实现不确定 | 可能需要 hook 而非字段级 access | 技术评审阶段验证 Payload API |
| 现有 Editor 用户是否有未发布的草稿 | 发布流程变更可能影响在途内容 | 上线前检查所有 Editor 的草稿状态 |
| 服务账号邮箱提取为常量后的兼容性 | 无功能变化，纯重构 | 全量 grep 确认替换完整 |

## 评审结论

需求明确，范围可控，建议定容。预计工作量 1-2 天（含测试）。
