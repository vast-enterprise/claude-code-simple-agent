# 技术方案

## 需求概述

外部 GEO 厂商（Crescendia）具备批量生成 geo-blog 内容的能力，需要在 tripo-cms 中提供自定义 API endpoint，让厂商通过 REST API 推送 Markdown 格式的 blog 文章到 CMS 的 **geo-posts** collection。推送后文章为 draft 状态，需人工审核后发布。Markdown 中的图片需自动下载并上传到 CMS media collection。文章标记 `isCrescendia: true` 以标识来源。

## 方案对比

### 方案一: 同步批量处理（推荐）

单个 endpoint 接收全部文章，同步处理每篇文章（解析 markdown、下载图片、创建 media、创建 post），逐篇返回结果。

**实现方式**: `POST /api/blog-import` handler 内循环处理每篇文章

**优点**:
- 实现简单，一个 endpoint 完成
- 每篇文章结果实时返回
- 容易追踪每篇文章的处理状态

**缺点**:
- 100+ 篇含图片时请求可能超时（Next.js 默认 60s）
- 需要合理设置超时时间

### 方案二: 异步队列处理

接收请求后返回 task ID，后台异步处理，厂商轮询结果。

**实现方式**: Payload CMS jobs task + 轮询 endpoint

**优点**:
- 不受超时限制
- 适合超大批量场景

**缺点**:
- 实现复杂度高（需要 jobs task + 状态管理 + 轮询接口）
- 厂商需要改造对接逻辑
- 当前项目 jobs 基础设施有限

### 推荐方案

**选择**: 方案一（同步批量处理）

**理由**:
- 100+ 篇 blog 通常以纯文本为主，图片数量可控
- 同步方式实现简单，厂商对接成本低
- 超时问题可通过分批（每批 50 篇）规避
- 后续如需异步可平滑升级

## 详细设计

### 涉及模块

| 模块 | 变更内容 |
|------|---------|
| tripo-cms / endpoints | **新增** `src/endpoints/blog-import/` 目录 |
| tripo-cms / collections/geo-posts | **修改** 新增 `isCrescendia` checkbox 字段 |
| tripo-cms / collections/media | **修改** 新增 `sourceUrl` text 字段（indexed，用于去重） |
| tripo-cms / collections/media | **修改** 新增 `sourceUrl` text 字段 |
| tripo-cms / payload.config.ts | **修改** 注册新 endpoint |
| tripo-cms / constants/env.ts | **修改** 新增 `BLOG_IMPORT_MAX_ARTICLES`、`MEDIA_FOLDER_ID` 配置 |
| fe-tripo-homepage / app/components/mdx | **新增** `media-image.vue` 组件 |
| fe-tripo-homepage / app/components/mdx | **修改** `index.ts` 注册组件到 mdxComponents |
| fe-tripo-homepage / server/utils | **修改** `mdxToAST.ts` MDX_COMPONENTS 白名单添加 media-image |

### 接口设计

```
POST /api/blog-import
Content-Type: application/json
Authorization: <user_id> API-Key <api_key>
```

**Request:**

```typescript
interface BlogImportRequest {
  locale: string           // 语言代码: en | zh | ja | ko | de | fr | es
  slugPrefix?: string     // 可选，slug 前缀，默认 "crescendia"
  articles: ArticleInput[]
}

interface ArticleInput {
  title: string            // 必填，文章标题
  slug?: string            // 可选，默认从 title 自动生成
  markdown: string         // 必填，Markdown 正文（可能含图片 URL）
  description?: string     // 可选，文章描述
  categorySlugs?: string[] // 可选，按 slug 匹配分类
  publishedAt?: string     // 可选，发布日期 (ISO 8601)
  keywords?: string[]     // 可选，SEO 关键词
}
```

**Response (成功):**

```typescript
interface BlogImportResponse {
  success: true
  processed: number
  results: ArticleResult[]
}

interface ArticleResult {
  title: string
  id: string              // Post record ID
  status: 'created' | 'updated' | 'skipped' | 'failed'
  reason?: string         // 失败/跳过原因
}
```

**Response (失败):**

```typescript
interface BlogImportErrorResponse {
  success: false
  error: string
  message: string
}
```

### 处理流程

```
POST /api/blog-import
  │
  ├── 1. 认证检查（req.user 存在 + API Key 有效）
  │
  ├── 2. 请求校验
  │     ├── locale 是否合法
  │     ├── articles 数量 ≤ MAX_ARTICLES (默认 50)
  │     └── 每篇文章 title + markdown 必填
  │
  └── 3. 逐篇处理 articles[]
        │
        ├── 3a. 提取 markdown 中的图片 URL
        │     regex: /!\[.*?\]\((https?:\/\/[^\s)]+)\)/g
        │
        ├── 3b. 下载外部图片 → 上传到 media collection
        │     ├── fetch(imageUrl) → buffer
        │     ├── payload.create({ collection: 'media', data, file })
        │     └── 替换 markdown 中的 URL → CMS URL
        │
        ├── 3c. 查询或匹配 categories（按 slug）
        │     payload.find({ collection: 'categories', where: { slug: { equals: xxx } } })
        │
        ├── 3d. 创建或更新 GeoPost
        │     ├── 去重: 按 slug + locale 查询现有记录
        │     ├── 已存在且 draft → update
        │     ├── 已存在且 published → skip
        │     └── 不存在 → create (contentType: 'markdown', _status: 'draft', isCrescendia: true)
        │
        └── 3e. 记录结果（created/updated/skipped/failed）
```

### 图片处理详细设计

**核心设计**: Markdown 中的图片上传到 media 后，替换为自定义组件标签 `<media-image>`，前端渲染时利用 media 多尺寸能力。

#### CMS 侧处理流程

```
原始 markdown:  ![AI 生成的 3D 模型](https://cdn.crescendia.com/img/abc123.jpg)
                                          │
                                          ├── 1. fetch 下载图片
                                          ├── 2. payload.create({ collection: 'media' })
                                          ├── 3. 获得 media record (id, sizes, url)
                                          │
处理后的 markdown:  <media-image media-id="6601a2b3..." alt="AI 生成的 3D 模型" />
```

#### CMS 侧代码

```typescript
// src/endpoints/blog-import/process-images.ts

const IMAGE_REGEX = /!\[([^\]]*)\]\((https?:\/\/[^\s)]+)\)/g

// 缓存 posts-media folder ID
let cachedFolderId: string | null = null

async function ensurePostsMediaFolder(payload: Payload): Promise<string> {
  if (cachedFolderId) return cachedFolderId
  const existing = await payload.find({
    collection: 'payload-folders',
    where: { name: { equals: 'posts-media' } },
    limit: 1,
    overrideAccess: true,
  })
  if (existing.docs.length > 0) {
    cachedFolderId = existing.docs[0].id
    return cachedFolderId
  }
  const folder = await payload.create({
    collection: 'payload-folders',
    data: { name: 'posts-media', folderType: 'media' },
    overrideAccess: true,
  })
  cachedFolderId = folder.id
  return cachedFolderId
}

async function processMarkdownImages(
  markdown: string,
  payload: Payload
): Promise<{ markdown: string; uploadedCount: number; reusedCount: number; failedCount: number }> {
  const matches = [...markdown.matchAll(IMAGE_REGEX)]
  let uploadedCount = 0
  let reusedCount = 0
  let failedCount = 0
  const folderId = await ensurePostsMediaFolder(payload)

  for (const match of matches) {
    const [fullMatch, altText, imageUrl] = match
    try {
      // 1. 去重：按 sourceUrl 查询是否已上传过
      const existing = await payload.find({
        collection: 'media',
        where: { sourceUrl: { equals: imageUrl } },
        limit: 1,
        overrideAccess: true,
      })

      let media: any
      if (existing.docs.length > 0) {
        media = existing.docs[0]
        reusedCount++
      } else {
        // 2. 下载图片
        const response = await fetch(imageUrl, { signal: AbortSignal.timeout(10_000) })
        if (!response.ok) throw new Error(`HTTP ${response.status}`)
        const buffer = Buffer.from(await response.arrayBuffer())

        const filename = getFilenameFromUrl(imageUrl, altText)
        const mimeType = response.headers.get('content-type') || 'image/jpeg'

        // 3. 上传到 media collection（归档到 posts-media folder，记录来源 URL）
        media = await payload.create({
          collection: 'media',
          data: {
            alt: altText || filename,
            sourceUrl: imageUrl,
            folder: folderId,
          },
          file: {
            data: buffer,
            mimetype: mimeType,
            name: filename,
            size: buffer.length,
          },
          overrideAccess: true,
        })
        uploadedCount++
      }

      // 4. 替换为自包含组件标签（含 caption，所有尺寸 URL 内联）
      const sizes = media.sizes || {}
      const caption = extractCaption(media.caption) || altText
      const attrs = [
        `alt="${escapeAttr(altText || media.alt || '')}"`,
        caption ? `caption="${escapeAttr(caption)}"` : '',
        `src-small="${sizes.thumbnail?.url || media.url}"`,
        sizes.small?.url ? `src-medium="${sizes.small.url}"` : '',
        sizes.medium?.url ? `src-large="${sizes.medium.url}"` : '',
        sizes.large?.url ? `src-xlarge="${sizes.large.url}"` : '',
        `width="${media.width || ''}"`,
        `height="${media.height || ''}"`,
      ].filter(Boolean).join(' ')

      markdown = markdown.replace(fullMatch, `<media-image ${attrs} />`)
    } catch (error) {
      failedCount++
    }
  }

  return { markdown, uploadedCount, reusedCount, failedCount }
}
```

#### 前端渲染（fe-tripo-homepage）

前端已有完整的 MDX 自定义组件体系：`app/components/mdx/` 目录注册组件，`mdxToAST.ts` 维护白名单。新增 `<media-image>` 组件接入此体系即可。

**1. 新增组件 `app/components/mdx/media-image.vue`**

```vue
<script setup lang="ts">
// 所有图片 URL 已由 CMS import 时内联，前端零 API 调用
const props = defineProps<{
  alt?: string
  caption?: string
  srcSmall: string
  srcMedium?: string
  srcLarge?: string
  srcXlarge?: string
  width?: string
  height?: string
}>()
</script>

<template>
  <figure class="media-image">
    <picture>
      <source v-if="srcXlarge" :srcset="srcXlarge" media="(min-width: 1400px)" />
      <source v-if="srcLarge" :srcset="srcLarge" media="(min-width: 900px)" />
      <source v-if="srcMedium" :srcset="srcMedium" media="(min-width: 600px)" />
      <source :srcset="srcSmall" />
      <img
        :src="srcSmall"
        :alt="alt || ''"
        :width="width"
        :height="height"
        loading="lazy"
        decoding="async"
      />
    </picture>
    <figcaption v-if="caption">{{ caption }}</figcaption>
  </figure>
</template>

<style scoped>
.media-image { margin: 1.5rem 0; }
.media-image img { width: 100%; height: auto; border-radius: 8px; }
.media-image figcaption { margin-top: 0.5rem; font-size: 0.875rem; color: #666; text-align: center; }
</style>
```

**性能对比**:

| 指标 | 旧方案 (media-id + useFetch) | 新方案 (内联 URL) |
|------|-----|-----|
| 页面加载 API 请求数 | N (每张图 1 次) | **0** |
| 首屏渲染阻塞 | 等待所有 useFetch 返回 | **无阻塞，纯 HTML** |
| SSR/SSG 友好度 | 需 async setup | **纯同步组件** |
| 缓存依赖 | media 记录变更需失效 | **markdown 自包含** |

**2. 注册组件 `app/components/mdx/index.ts`**

```typescript
// 在 mdxComponents 对象中新增
export const mdxComponents = {
  // ... 现有组件 ...
  'media-image': defineAsyncComponent(() => import('./media-image.vue')),
}
```

**3. 白名单 `server/utils/mdxToAST.ts`**

```typescript
// 在 MDX_COMPONENTS 数组中新增
'media-image'
```

**数据流**（前端零额外请求）:
```
CMS import 时:
  ![alt](external-url) → 下载 → 上传 media → 获得 sizes
     → 替换为 <media-image src-small="..." src-medium="..." ... />

前端渲染时:
  <media-image src-small="..." src-medium="..." ... />
     → mdxToAST() 白名单放行
     → mdxComponents 映射 → media-image.vue
     → 纯同步渲染 <picture> + srcset（零 API 调用）
```

**参考**: 现有 `BigCard` 组件的注册方式完全一致。

### 数据模型

无新增 collection，复用现有 geo-posts 和 media，新增 2 个字段 + 1 个 folder：

- **geo-posts**: 通过 Local API 创建，`contentType: 'markdown'`，`_status: 'draft'`，`isCrescendia: true`
- **media**: 图片上传到此 collection，归档到 `posts-media` folder
- **categories**: 按 slug 查询匹配

**新增字段 1**: `isCrescendia`（geo-posts）

```typescript
// src/collections/geo-posts/index.ts 新增字段
{
  name: 'isCrescendia',
  type: 'checkbox',
  label: 'Crescendia 供稿',
  defaultValue: false,
  admin: {
    position: 'sidebar',
    description: '标记此文章由外部 GEO 厂商 Crescendia 提供',
    readOnly: true,
  },
}
```

**新增字段 2**: `sourceUrl`（media）

```typescript
// src/collections/media/index.ts 新增字段
{
  name: 'sourceUrl',
  type: 'text',
  label: '来源 URL',
  index: true,  // 建立索引，加速去重查询
  admin: {
    position: 'sidebar',
    description: '图片来源 URL，用于去重判断',
    readOnly: true,
  },
}
```

**新增 Folder**: `posts-media`

- 利用 Payload 3.x 内置 Folders 功能（media collection 已启用 `folders: true`）
- 所有通过 blog-import 上传的图片归档到 `posts-media` folder
- 首次 import 时自动创建，后续复用
- CMS 后台可按 folder 筛选管理这些图片

### geo-posts 字段映射表

创建 geo-post 时 `payload.create()` 的完整 data 对象：

| 字段 | 值来源 | 示例 |
|------|--------|------|
| `title` | `{locale}: ArticleInput.title` | `{ en: "AI 3D Model Guide" }` |
| `slug` | `slugPrefix + "/" + slugify(title)` | `"crescendia/ai-3d-model-guide"` |
| `contentType` | 硬编码 `"markdown"` | - |
| `markdown` | `{locale}: 处理后的 markdown` | `{ en: "# Title\n...\n<media-image ...>" }` |
| `heroImage` | markdown 中第一张图片的 media ID | `"6601a2b3..."` |
| `description` | `{locale}: ArticleInput.description` | `{ en: "A guide to..." }` |
| `categories` | 按 `categorySlugs` 匹配的 category IDs | `["cat-id-1"]` |
| `authors` | 知询 `Tripo Team` 用户的 ID（缓存） | `["tripo-team-user-id"]` |
| `publishedAt` | `ArticleInput.publishedAt` 或留空 | `"2026-04-02T10:00:00.000Z"` |
| `isLegacy` | `false` | - |
| `isCrescendia` | `true` | - |
| `meta.title` | `ArticleInput.title`（取对应 locale） | `"AI 3D Model Guide"` |
| `meta.description` | `ArticleInput.description`（取对应 locale）| `"A guide to..."` |
| `meta.image` | 复用 heroImage 的 media ID | `"6601a2b3..."` |
| `meta.keywords` | `{locale}: ArticleInput.keywords` | `{ en: ["ai", "3d"] }` |
| `relatedPosts` | 留空 | `[]` |
| `_status` | `"draft"` | - |

**slugPrefix 逻辑**:

```typescript
// API 请求中新增 slugPrefix 参数
interface BlogImportRequest {
  locale: string
  slugPrefix?: string  // 可选，默认 "crescendia"
  articles: ArticleInput[]
}

// slug 生成
const prefix = req.body.slugPrefix || 'crescendia'
const slug = `${prefix}/${slugify(article.title)}`
// 示例: crescendia/ai-3d-model-guide
```

**Tripo Team 用户查找**:

```typescript
// 首次调用时查找并缓存
let cachedTripoTeamUserId: string | null = null

async function getTripoTeamUser(payload: Payload): Promise<string> {
  if (cachedTripoTeamUserId) return cachedTripoTeamUserId
  const users = await payload.find({
    collection: 'users',
    where: { name: { equals: 'Tripo Team' } },
    limit: 1,
    overrideAccess: true,
  })
  if (users.docs.length === 0) throw new Error('Tripo Team user not found')
  cachedTripoTeamUserId = users.docs[0].id
  return cachedTripoTeamUserId
}
```

**heroImage 提取逻辑**:

```typescript
// 从处理后的 markdown 中提取第一个 media-image 的 srcSmall 作为 heroImage
// heroImage 使用 media ID，需要 process-images 中返回 media 对象
// 第一张成功上传/复用的图片自动设为 heroImage
function extractHeroImageId(processedMediaMap: Map<string, any>): string | null {
  const firstImage = processedMediaMap.values().next().value
  return firstImage?.id || null
}
```

### 环境变量

```
BLOG_IMPORT_MAX_ARTICLES=50    # 单次最大文章数
BLOG_IMPORT_IMAGE_TIMEOUT=10000 # 图片下载超时(ms)
```

### 文件结构

```
src/endpoints/blog-import/
├── index.ts              # Endpoint 注册 + handler
├── validate.ts           # 请求校验逻辑
├── process-images.ts     # Markdown 图片处理
├── process-article.ts    # 单篇文章处理（图片 + 创建 Post）
└── types.ts              # TypeScript 类型定义
```

### 去重策略

通过 `slug` + `locale` 在 **geo-posts** collection 中判断：
1. 查询 `geo-posts` 中 `slug === articleSlug` 的记录
2. 如果存在且 `_status === 'draft'` → 更新（覆盖 markdown、图片等）
3. 如果存在且 `_status === 'published'` → 跳过（不允许覆盖已发布文章）
4. 如果不存在 → 创建新记录，`isCrescendia: true`

### 错误处理

| 场景 | 处理方式 |
|------|---------|
| 认证失败 | 返回 401 |
| 请求参数非法 | 返回 400 + 详细错误信息 |
| 文章数超限 | 返回 400 |
| 单篇文章处理失败 | 记录到 results，不阻塞其他文章 |
| 图片下载失败 | 保留原始 URL，继续处理 |
| 图片下载超时 | 10s 超时，跳过该图片 |

## 工作量评估

| 模块 | 工作量 | 负责人 |
|------|--------|--------|
| Endpoint 框架 + 认证 | 0.5 人日 | 郭凯南 |
| geo-posts 新增 isCrescendia 字段 | 0.5 人日 | 郭凯南 |
| media 新增 sourceUrl 字段 + 0.25 人日 | 郭凯南 |
| Markdown 图片处理（去重 + folder + heroImage 提取） | 1 人日 | 郭凯南 |
| 文章创建/更新 + 字段映射 | 0.5 人日 | 郭凯南 |
| 请求校验 + 错误处理 | 0.5 人日 | 郭凯南 |
| 前端 media-image 组件 + 注册 + 白名单 | 0.5 人日 | 郭凯南 |
| 测试 | 0.5 人日 | 郭凯南 |
| **合计** | **4.25 人日** | |

## 风险评估

| 风险 | 影响 | 应对措施 |
|------|------|---------|
| 图片下载失败率高 | 中 | 保留原始 markdown 图片语法不阻塞，日志记录失败图片供后续手动处理 |
| 大批量请求超时 | 中 | 限制单批 50 篇，厂商分批调用 |
| Media 创建性能（OSS 上传） | 中 | 图片串行处理避免并发压力，每张 10s 超时 |
| `<media-image>` 格式与前端渲染约定不一致 | 中 | 复用现有 mdxToAST + mdxComponents 体系，与 BigCard 等组件注册方式完全一致 |
| Markdown 图片正则遗漏 | 低 | 处理标准 markdown 语法 `![alt](url)`，非标准格式保留原样 |
| 去重冲突（slug 碰撞） | 低 | slug 从 title 自动生成，碰撞时加后缀 |

## 测试计划

- [ ] 单元测试: `processMarkdownImages()` 各种 markdown 格式
- [ ] 单元测试: 去重逻辑（draft 更新 / published 跳过 / 新建）
- [ ] 集成测试: 完整 endpoint 调用（含图片 mock）
- [ ] 集成测试: 认证失败场景
- [ ] 集成测试: 多语言文章推送
- [ ] 手动测试: 使用 curl 模拟厂商批量推送 10+ 篇文章
