# 需求评审 — Blog 列表排序可控（置顶 + 拖拽排序）

## 1. 需求来源

| 字段 | 值 |
|------|-----|
| 需求ID | recvfIeCwDLyRP |
| 需求描述 | Blog 列表排序可控（置顶 + 拖拽排序） |
| 需求Owner | 郭凯南 |
| 研发Owner | 郭凯南 |
| 提出日期 | 2026-04-03 |
| 来源 | 用户口头描述 |

## 2. 需求范围

### 核心功能

1. **CMS 端字段**：posts collection 新增 `pinned: checkbox` 字段（默认 false），管理员勾选即置顶
2. **CMS 端排序**：posts collection 启用 `orderable: true`，管理员可在列表页拖拽文档调整顺序（Payload 原生 fractional indexing）
3. **前端排序**：blog 列表 API 排序逻辑调整为 `[-pinned, -_order, -publishedAt]`
4. **前端标识**：置顶文章（`pinned: true`）在列表中显示特殊标识（角标/标签）

### 边界条件

- **不包含**：geo-posts 集合的排序控制（本次只做 posts）
- **不包含**：首页精选文章（`blogFeaturedPost` block）的改动
- **不包含**：CMS 后台列表页置顶文章的视觉区分（如打标签）

### 不包含

- 其他 collection 的排序功能
- SEO meta 字段改动
- 多语言差异处理

## 3. 验收标准

1. CMS 后台 posts 列表每条记录可见 `pinned` 勾选框，勾选后值保存成功
2. CMS 后台 posts 列表支持拖拽排序，拖拽后顺序持久化
3. 前端 `/api/blog/posts` 返回顺序为：pinned=true 的文章在前，按 `_order` 排序；其余按 `publishedAt` 降序
4. 前端 blog 列表页中，`pinned=true` 的文章显示置顶标识
5. 存量 posts 数据 `pinned` 默认为 `false`，无需人工迁移

## 4. 技术约束

| 约束项 | 说明 |
|--------|------|
| Payload CMS | 3.x，`orderable` 使用 fractional indexing，`_order` 字段由 Payload 自动维护 |
| 前端 | fe-tripo-homepage，Nuxt 4，API 路由在 `server/api/blog/posts.get.ts` |
| 数据库 | MongoDB，新增 `pinned` 字段，存量数据无影响 |
| 涉及仓库 | tripo-cms（CMS 改动）、fe-tripo-homepage（前端改动） |

## 5. 合规风险审查

- ✅ **无外部平台政策冲突**：本功能仅涉及内部 CMS 管理和自有前端展示
- ✅ **无数据真实性风险**：排序字段由管理员手动控制，无自动生成或伪造数据

**结论：无合规风险。**

## 6. 问题与风险

| # | 问题/风险 | 影响 | 建议 |
|---|----------|------|------|
| 1 | `pinned` 字段需要加到 post-shared.ts 还是单独在 posts/index.ts？ | 低：不影响功能 | 建议加在 post-shared.ts，便于 geo-posts 未来复用 |
| 2 | `_order` 字段是 Payload 自动注入，前端 API 查询时需显式指定 `depth` 或 `pinned` populate？ | 低：pinned 是简单 checkbox，`_order` 也是 scalar，不需 populate | 注意：`_order` 需要在查询时显式包含在返回字段中 |
| 3 | 置顶标识的 UI 形式未确定（角标 vs 标签 vs 图标） | 低：UI 细节，可迭代 | 评审后与产品确认，或先做最简单的标签方案 |
| 4 | geo-posts 暂不开放排序能力，但加了 post-shared 后会同步有 pinned 字段 | 低：geo-posts 不会调用 blog posts API，无影响 | 注意：geo-posts 的列表 API 需单独处理排序逻辑（不在本次范围） |

## 7. 评审结论

✅ **评审通过，建议定容。**

- 需求范围清晰，技术方案可行，无合规风险
- 核心功能点明确（pinned 字段 + orderable + 前端排序 + 置顶标识）
- 风险点已在表中标注，有应对方案
- 建议评审后先与产品确认置顶标识的 UI 形式

---

**下一步**：提议需求状态变更为"定容确认"，等待用户确认。
