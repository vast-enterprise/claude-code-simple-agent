# 需求评审

## 需求来源

- 需求ID: `recvfC1EIZaTm7`
- 需求描述: CMS posts 与 geo-posts 集合支持单篇文章互相迁移
- 需求Owner: 郭凯南
- 来源文档: 用户直接提出

## 需求范围

### 核心功能

在 Payload CMS 管理面板中，为 `posts` 和 `geo-posts` 集合的单文章编辑页面添加"迁移到另一集合"操作按钮：

1. **posts → geo-posts 迁移**: 在 posts 文章编辑页，点击按钮将当前文章迁移到 geo-posts 集合
2. **geo-posts → posts 迁移**: 在 geo-posts 文章编辑页，点击按钮将当前文章迁移到 posts 集合
3. **原数据处理**: 迁移成功后，原集合中的文章自动 unpublish（保留为 draft）
4. **双向对等**: 两个方向的迁移逻辑对称

### 边界条件

- 迁移粒度：单篇文章（非批量）
- 触发方式：Admin Panel 编辑页 UI 按钮
- 内容类型：支持所有 contentType（lexical / markdown / external）
- 富文本内容：Lexical 编辑器内容完整迁移（两者共享相同的 Block 结构）
- 媒体文件：heroImage 和 meta.image 通过 upload 关联，迁移时保持引用不变
- slug 冲突：如果目标集合已存在同 slug 文章，需给出提示
- 关联数据：categories、authors 引用直接保留
- relatedPosts：迁移时需更新关联目标集合

### 不包含

- 批量迁移能力（后续可扩展）
- 版本历史迁移（版本数据不跟随）
- 定时发布配置迁移
- 前端路由自动切换（迁移后需手动调整前端 feature flag 或路由配置）
- slug 格式自动转换（posts slug 不含 `/`，迁移到 geo-posts 后保持原 slug）

## 验收标准

1. posts 编辑页有"迁移到 GEO 文章"按钮，点击后弹出确认对话框
2. geo-posts 编辑页有"迁移到博客"按钮，点击后弹出确认对话框
3. 迁移后目标集合出现新文章，字段数据完整（title、content/markdown/externalUrl、heroImage、categories、authors、meta SEO 等）
4. 迁移后原文章状态变为 draft（unpublish）
5. slug 冲突时给出明确错误提示，不覆盖已有文章
6. relatedPosts 关联在迁移后正确指向 posts 集合
7. 迁移操作有操作记录（可考虑在迁移后添加备注或日志）

## 技术约束

### 数据结构差异（调研结论）

| 差异点 | Posts | GeoPosts | 迁移影响 |
|--------|-------|----------|----------|
| slug 格式 | 不允许 `/` | 允许 `/` | **无影响**，迁移保持原 slug |
| relatedPosts | 自引用 posts | 跨引用 posts | **需处理**：迁移时统一指向 posts |
| relatedPosts filter | 排除自身 | 无 filter | **无影响** |
| schedulePublish | 支持 | 不支持 | **不迁移**，丢弃定时发布配置 |
| 版本历史 maxPerDoc | 50 | 1 | **不迁移**，版本不跟随 |

### 共享字段（10 个）

title、heroImage、content、markdown、externalUrl、description、categories、meta（SEO）、isLegacy、contentType、publishedAt、authors、populatedAuthors

### 技术方案方向

- Payload CMS 3.x 支持自定义 Admin Panel 组件（EditView）
- 可在编辑页注入自定义按钮组件
- 迁移逻辑通过 Payload Local API 实现（无需额外 REST 端点）
- 利用 `src/fields/post-shared.ts` 的共享字段定义确保字段对齐

## 问题与风险

| # | 问题 | 风险等级 | 应对方案 |
|---|------|----------|----------|
| 1 | slug 冲突：目标集合可能已有同 slug 文章 | 中 | 迁移前检查，冲突时提示用户修改 |
| 2 | relatedPosts 空引用：geo-posts 的 relatedPosts 指向 posts，迁移后关联文章可能已不存在 | 低 | 迁移时校验关联有效性，无效关联清除 |
| 3 | 前端路由：迁移后文章 URL 可能变化（如果前端对两个集合有不同路由策略） | 中 | 明确为 out of scope，迁移后需手动处理 |
| 4 | 数据一致性：迁移过程中写入失败可能导致数据丢失 | 高 | 使用事务或补偿机制，迁移失败时回滚 |
| 5 | populatedAuthors 计算字段：迁移后需重新触发 afterRead hook | 低 | Payload 自动处理 |

## 评审结论

- [x] 需求范围明确
- [x] 验收标准清晰
- [x] 无阻塞性风险（风险均有应对方案）

### 预估容量

- 后端：自定义 Admin 组件 + 迁移 API 逻辑（约 2-3 天）
- 测试：迁移正向/反向/异常场景（约 1 天）
