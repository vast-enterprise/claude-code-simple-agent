# 技术方案 — Blog 列表排序可控（置顶 + 拖拽排序）

## 1. 需求概述

在 CMS 后台为 posts collection 新增置顶标记（`pinned`）和拖拽排序（`orderable`），前端按置顶优先 → 拖拽顺序 → 发布时间排序，置顶文章展示特殊标识。

## 2. 方案对比

### 方案 A（推荐）：pinned checkbox + Payload orderable

| 维度 | 说明 |
|------|------|
| CMS 字段 | `pinned: checkbox`（默认 false）+ `orderable: true` |
| 排序机制 | Payload fractional indexing，自动维护 `_order` 字段 |
| 前端排序 | `['-pinned', '-_order', '-publishedAt']` |
| 置顶标识 | 前端组件根据 `pinned` 渲染 UI 标识 |

**优点**：
- 零自定义排序字段，Payload 原生支持，拖拽即排
- 管理员体验好，无需手动填数字
- `_order` 使用 fractional indexing，插入新位置无需更新其他文档

**缺点**：
- geo-posts 如需复用，需同步开启（本次不开）

### 方案 B：pinned + sortWeight

- 优点：置顶语义清晰
- 缺点：管理员需手动填数字，体验差；数字可能冲突或需要重排

### 方案 C：仅 pinned boolean

- 优点：最简单
- 缺点：置顶文章之间无法控制顺序

**结论**：推荐方案 A。

## 3. 详细设计

### 3.1 tripo-cms 改动

#### 文件 1：`src/fields/post-shared.ts`

在共享字段末尾新增 `pinnedField`：

```typescript
export const pinnedField: Field = {
  name: 'pinned',
  type: 'checkbox',
  defaultValue: false,
  admin: {
    description: '置顶后文章将在 blog 列表最前方显示',
  },
}
```

在共享字段导出中追加 `pinnedField`。

#### 文件 2：`src/collections/posts/index.ts`

在 collection 配置中添加 `orderable: true`：

```typescript
export const Posts: CollectionConfig = {
  slug: 'posts',
  orderable: true,  // ← 新增，启用 Payload 原生拖拽排序
  // ...existing fields, hooks, etc.
}
```

**验证**：`orderable` 在 Payload 3.x 中自动为每条文档维护 `_order` 字段（字符串，fractional indexing 格式）。

### 3.2 fe-tripo-homepage 改动

#### 文件 1：`server/api/blog/posts.get.ts`

修改排序逻辑：

```typescript
// 改前
sort: '-publishedAt'

// 改后
sort: ['-pinned', '-_order', '-publishedAt']
```

需要确认 Payload REST API 支持多字段排序。参考 Payload 文档：`sort` 参数支持逗号分隔的字符串或字符串数组，格式为 `fieldName`（升序）或 `-fieldName`（降序）。

**注意**：Payload 的 `orderable` 生成的字段名是 `_order`，需要通过 `depth` 或 `select` 参数确保 `_order` 字段在返回结果中可见。

#### 文件 2：`app/pages/blog/index.vue`（或对应的列表组件）

根据 `pinned: true` 渲染置顶标识。UI 方案待产品确认，先实现简单标签（"置顶"二字），可后续迭代。

```vue
<!-- 置顶标识示例 -->
<span v-if="post.pinned" class="post-pinned-badge">置顶</span>
```

## 4. 工作量评估

| 模块 | 改动 | 复杂度 |
|------|------|--------|
| CMS | `pinnedField` 新增（约 10 行） | 低 |
| CMS | `orderable: true` 启用（1 行） | 极低 |
| 前端 API | 排序逻辑修改（1 行） | 极低 |
| 前端组件 | 置顶标识渲染（~5 行） | 低 |
| 验证测试 | CMS 拖拽 + 前端列表验证 | 低 |

**总计**：预计 1 小时内可完成编码。

## 5. 风险评估

| 风险 | 概率 | 影响 | 应对 |
|------|------|------|------|
| Payload `orderable` 与现有 `_order` 字段冲突 | 低 | 低 | `_order` 由 Payload 自动管理，如已有同名字段需迁移 |
| REST API 多字段排序语法 | 低 | 低 | 先在 CMS 本地 API 验证，再部署到前端 |
| geo-posts 意外获得 pinned 字段 | 低 | 低 | geo-posts 有自己的列表 API，不会调用 blog API，无影响 |

## 6. 测试计划

### 6.1 CMS 端

| 测试项 | 操作 | 预期结果 |
|--------|------|----------|
| pinned 字段保存 | 在某篇 post 编辑页勾选 pinned，保存 | 再次打开值仍为 true |
| 拖拽排序 | 在 posts 列表拖拽 A 到 B 之前 | 保存后 A 排在 B 之前 |
| 拖拽后 pinned 文章顺序 | 拖拽置顶文章间顺序 | 顺序按拖拽结果变化 |
| 默认值 | 新建 post，默认 pinned | 默认 false |

### 6.2 前端

| 测试项 | 操作 | 预期结果 |
|--------|------|----------|
| 置顶文章排序 | 勾选 N 篇 post pinned | `/api/blog/posts` 返回结果中 pinned=true 的在最前 |
| 置顶标识显示 | 访问 blog 列表页 | pinned=true 的文章显示置顶标识 |
| 非置顶排序 | pinned=false 的文章 | 按 publishedAt 降序排列 |
| 翻页正确 | 翻页后 pinned 文章 | 仍保持在最前 |

## 7. 实施顺序

1. CMS：`post-shared.ts` 新增 `pinnedField`
2. CMS：`posts/index.ts` 启用 `orderable: true`
3. 前端：`posts.get.ts` 修改排序逻辑
4. 前端：列表组件添加置顶标识
5. 验证测试
