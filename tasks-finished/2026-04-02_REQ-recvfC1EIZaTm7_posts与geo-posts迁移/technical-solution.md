# 技术方案

## 需求概述

在 Payload CMS 管理面板中，为 `posts` 和 `geo-posts` 集合的单文章编辑页添加"迁移到另一集合"按钮，实现单篇文章级别的跨集合迁移。迁移后原文 unpublish。

## 方案对比

### 方案一：自定义端点 + Admin 按钮组件（推荐）

**实现方式**：
1. 新建自定义 API 端点 `POST /api/migrate-post`，接收 `sourceCollection`、`sourceId`、`targetCollection`
2. 端点内通过 Payload Local API 读取源文档 → 转换字段 → 写入目标集合 → unpublish 源文档
3. 在 posts 和 geo-posts 的 `admin.components.edit` 中注入迁移按钮组件
4. 按钮组件调用自定义端点执行迁移

**优点**：
- 复用项目已有模式（`data-backfill` 端点 + `data-backfill-button` 组件）
- 逻辑集中在端点，易于测试和维护
- UI 组件轻薄，只负责调用和状态展示

**缺点**：
- 需新增 1 个端点文件 + 1 个 UI 组件 + 修改 2 个 collection 配置

### 方案二：Collection Hook afterRead + 前端路由

**实现方式**：
通过 afterChange hook 监听状态变化，在文档保存时检查特殊标记字段，触发迁移。

**优点**：
- 不需要自定义端点

**缺点**：
- 违反单一职责，hook 职责过重
- 无法提供即时反馈（需保存后才能触发）
- 难以处理错误和回滚
- 与现有架构模式不一致

### 推荐方案

**选择**：方案一

**理由**：
1. 项目已有成熟的 `data-backfill` 端点 + 按钮组件模式，直接对齐
2. 迁移是一次性操作，适合端点模式而非 hook 模式
3. 端点内可做完整的校验、错误处理和回滚
4. UI 交互清晰：点击按钮 → 确认 → 执行 → 反馈结果

## 详细设计

### 涉及模块

| 模块 | 变更内容 |
|------|---------|
| `src/endpoints/migrate-post/index.ts` | 新建迁移端点 |
| `src/components/migrate-post-button/index.tsx` | 新建迁移按钮组件 |
| `src/collections/posts/index.ts` | 添加 admin.components.edit 配置 |
| `src/collections/geo-posts/index.ts` | 添加 admin.components.edit 配置 |
| `src/payload.config.ts` | 注册新端点 |

### 接口设计

```
POST /api/migrate-post

Request:
{
  "sourceCollection": "posts" | "geo-posts",
  "sourceId": "文档ID",
  "targetCollection": "posts" | "geo-posts"
}

Response (成功):
{
  "success": true,
  "data": {
    "newRecordId": "新文档ID",
    "sourceUnpublished": true
  }
}

Response (失败 - slug 冲突):
{
  "success": false,
  "error": "目标集合已存在相同 slug 的文章",
  "code": "SLUG_CONFLICT"
}
```

### 迁移逻辑流程

```
1. 校验参数（sourceCollection ≠ targetCollection，ID 有效）
2. 读取源文档（payload.findByID，深度填充）
3. 检查目标集合 slug 是否冲突
4. 构造目标文档数据：
   - 复制共享字段（title, heroImage, content, markdown, externalUrl, description, categories, meta, isLegacy, contentType, publishedAt, authors）
   - slug：保持原值（不自动转换格式）
   - relatedPosts：统一指向 posts 集合
   - 清除 _id、createdAt、updatedAt、_status 等系统字段
   - populatedAuthors：由 afterRead hook 自动填充，不手动复制
5. 创建目标文档（payload.create，draft 状态）
6. Unpublish 源文档（payload.update，_status → 'draft'）
7. 返回结果
```

### UI 组件设计

按钮组件（`migrate-post-button`）：
- 位置：`admin.components.edit.editMenuItems`（放在「···」下拉菜单中）
- 使用 `useDocumentInfo()` 获取当前文档 ID 和集合名
- 使用 `useConfig()` 获取集合配置
- 点击后弹出确认对话框（确认迁移方向和目标集合）
- 调用 `/api/migrate-post` 端点
- 成功后刷新页面或跳转到新文档

### 数据模型

无新增/变更字段。迁移过程中：
- 目标文档 `slug` 保持源文档原值
- 目标文档初始 `_status` = `'draft'`（需手动发布）
- 源文档 `_status` 从 `'published'` → `'draft'`

## 工作量评估

| 模块 | 工作量 | 负责人 |
|------|--------|--------|
| 迁移端点 | 1 人日 | 待确认 |
| UI 按钮组件 | 0.5 人日 | 待确认 |
| Collection 配置修改 | 0.5 人日 | 待确认 |
| 集成测试 | 0.5 人日 | 待确认 |
| 手动验证 | 0.5 人日 | 待确认 |
| **合计** | **3 人日** | |

## 风险评估

| 风险 | 影响 | 应对措施 |
|------|------|---------|
| slug 冲突导致迁移失败 | 中 | 端点内预检，冲突时返回明确错误，提示用户修改 slug |
| 迁移过程中写入失败（部分成功） | 高 | 先创建目标，成功后再 unpublish 源；创建失败时不 unpublish |
| Lexical 富文本内联 Block 引用丢失 | 低 | Block 数据内联在文档中，不跨集合引用，无影响 |
| relatedPosts 指向不存在的文章 | 低 | 迁移时校验关联有效性，无效关联清除 |
| populatedAuthors 未重新计算 | 低 | 由 afterRead hook 自动处理，不手动干预 |

## 测试计划

- [ ] posts → geo-posts 迁移（lexical 内容）
- [ ] posts → geo-posts 迁移（markdown 内容）
- [ ] posts → geo-posts 迁移（external URL 内容）
- [ ] geo-posts → posts 迁移（反向）
- [ ] slug 冲突场景
- [ ] 迁移后原文状态为 draft
- [ ] 迁移后目标文档字段完整性（title、content、categories、authors、SEO）
- [ ] 源文档包含 relatedPosts 时的处理
