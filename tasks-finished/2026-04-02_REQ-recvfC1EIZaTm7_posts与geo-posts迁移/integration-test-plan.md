# 集成测试方案 - Posts ↔ Geo-Posts 迁移

## 前置条件

| 条件 | 要求 | 状态 |
|------|------|------|
| MongoDB | 本地 27017 可连接 | 待确认 |
| CMS Dev Server | `pnpm dev` 在 worktree 内启动，localhost:3000 | 待确认 |
| 管理员账号 | super-admin 角色用户，可登录 /admin | 待确认 |
| 测试数据 | posts 集合至少 2 篇已发布文章，geo-posts 集合至少 1 篇 | 待确认 |
| 分支 | `feature/REQ-recvfC1EIZaTm7-posts-geo-posts-migrate` 已 checkout | 已确认 |

## 测试场景

### T1: 登录验证
- **步骤**：打开 `/admin/login`，输入管理员凭据登录
- **预期**：成功跳转到管理面板首页

### T2: 迁移按钮可见性
- **步骤**：进入 posts 某篇文章编辑页，点击「···」更多菜单
- **预期**：菜单中显示「迁移到 GEO 文章」按钮

### T3: posts → geo-posts 正常迁移
- **步骤**：
  1. 记录源文章的 slug、title、categories
  2. 点击「迁移到 GEO 文章」
  3. 确认弹窗
  4. 等待迁移完成
- **预期**：
  - 页面跳转到 geo-posts 集合中新创建的文章编辑页
  - 新文章 slug 与源文章一致
  - 新文章状态为 draft
  - 新文章 title、content、categories、authors 字段与源文章一致

### T4: 源文档 unpublish 验证
- **步骤**：回到源文章编辑页（posts 集合）
- **预期**：源文章状态变为 draft

### T5: geo-posts → posts 反向迁移
- **步骤**：在 geo-posts 编辑页点击「迁移到博客」
- **预期**：
  - 成功创建 posts 集合新文章
  - 跳转到新文章编辑页
  - 字段完整迁移

### T6: slug 冲突检测
- **前提**：geo-posts 集合中已存在 slug 为 `test-post` 的文章
- **步骤**：尝试迁移另一篇同名 slug 的 posts 文章到 geo-posts
- **预期**：显示错误信息，提示 slug 冲突，迁移不执行

### T7: 非管理员权限拦截
- **前提**：使用非管理员账号（editor 角色）登录
- **步骤**：进入文章编辑页，点击迁移按钮
- **预期**：返回 403 权限不足错误

### T8: 未登录拦截
- **步骤**：未登录状态下直接调用 `POST /api/migrate-post`
- **预期**：返回 401

### T9: 内容类型覆盖
- **场景 A - Lexical 内容**：迁移 contentType=lexical 的文章，验证 content 字段完整
- **场景 B - Markdown 内容**：迁移 contentType=markdown 的文章，验证 markdown 字段完整
- **场景 C - External URL**：迁移 contentType=externalUrl 的文章，验证 externalUrl 字段完整

## 测试执行方式

使用 Playwright CLI 自动化执行 T1-T8（T9 需要特定测试数据，视情况手动验证）。

## 通过标准

- T1-T8 全部通过
- 单元测试 12/12 通过
- 无 console error（网络请求错误除外）
