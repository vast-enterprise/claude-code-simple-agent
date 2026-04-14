# Hub-Spoke 前端 CMS 接入 — 技术方案

> 需求ID: recvfwTbU1yXx4 | 仓库: fe-tripo-homepage | 日期: 2026-04-14

## 1. 需求概述

将 Hub-Spoke 页面的数据源从 Crescendia 外部 API 切换到 Payload CMS，实现内容自主管控。

### 迁移节奏（三步闭环）

```
Step 1: 单篇推送验证 ──→ 验证 CMS sync API 端到端可用
Step 2: 全量推送联调 ──→ 所有现有数据灌入 CMS，排除数据问题
Step 3: 前端切换渲染 ──→ 从 Crescendia API → CMS 数据源
```

- Step 1-2 不涉及前端代码修改，仅验证 CMS 后端（staging 已部署）
- Step 3 是本技术方案的核心，涉及前端代码变更
- **切换后不能急于合并**，需完成端到端验证

## 2. 现状分析

### 当前数据流

```
浏览器 → [...slug].vue
  → $fetch('/api/crescendia/hub/{slug}?lang=en')
    → server/api/crescendia/hub/[slug].get.ts
      → crescendia.ts: fetchHub()
        → Crescendia API (MD5 签名鉴权, 5min 内存缓存)
          → 返回 HubData { slug, title, type, components[], meta, ... }
            → parseContentBlocks() 解析 Markdown
              → 前端组件渲染
```

### Crescendia vs Payload CMS API 数据差异

| 维度 | Crescendia API | Payload CMS API (depth=2) |
|------|---------------|--------------------------|
| 响应信封 | `{ code, data, msg }` | 列表: `{ docs[], totalDocs }`, 单条: 直接对象 |
| 组件结构 | `{ id, type, props: {...} }` | 平铺: `{ blockType, id, blockName, title, ... }` |
| 类型标识 | `type: "hero"` | `blockType: "hsHero"` |
| 图片字段 | URL 字符串 `"https://..."` | Media 对象 `{ id, url, sizes, alt, width, height }` |
| tags 等数组 | 字符串数组 `["tag1"]` | 对象数组 `[{ name: "tag1", id: "..." }]` |
| hubSlug 关联 | 字符串 `"tutorials"` | 关联文档对象 `{ id, slug, title, ... }` 或字符串 ID |
| SEO 图片 | `meta.ogImage: "url"` | `meta.image: Media` 对象 |
| SEO keywords | `meta.keywords: ["k1"]` | `meta.keywords: [{ keyword: "k1" }]` |

## 3. 方案对比

### 方案 A: 服务端适配层（推荐）

**思路**: 在 Nitro 服务端 API handler 中完成 Payload → HubData/SpokeData 转换，前端组件零改动。

```
浏览器 → [...slug].vue（不变）
  → $fetch('/api/crescendia/hub/{slug}?lang=en')（路由不变）
    → server handler（改造）
      → payload-client.ts: usePayloadSDK().find()
        → CMS API → Payload 响应
          → hub-spoke-adapter.ts: transformPayloadToHub()
            → 输出 HubData（与 Crescendia 格式完全一致）
              → parseContentBlocks()（不变）
                → 前端组件渲染（不变）
```

| 优点 | 缺点 |
|------|------|
| 前端组件零改动，风险最低 | 图片只取 `url`，未利用 `sizes` 响应式 |
| 类型定义不变，无类型蔓延 | 转换逻辑集中在一处，该模块会有一定复杂度 |
| 回滚只需切换数据源函数 | — |
| 改动文件少（~4 文件） | — |

### 方案 B: 前端全链路适配

**思路**: 修改类型定义支持 `string | PayloadMedia`，改造 12 个组件使用 `resolveImageUrl()`。

| 优点 | 缺点 |
|------|------|
| 可利用 Media 响应式图片 sizes | 改动 12+ 组件，回归风险高 |
| 类型更精确 | 类型蔓延到所有组件 |
| — | 回滚需撤销大量组件修改 |
| — | 工期更长 |

### 方案 C: 混合（先 A 后 B）

先用方案 A 快速上线，后续单独优化响应式图片能力。

### 最终方案: A+（服务端适配层 + Media sizes 响应式图片）

方案 A 基础上增加图片 sizes 适配，复用现有 `mdx/media-image.vue` 组件。

理由:
1. **服务端做主转换**: 降低组件改动复杂度
2. **图片 sizes 必须用上**: 利用 CMS Media 7 种尺寸（thumbnail~xlarge），提升 LCP
3. **复用已有组件**: `mdx/media-image.vue` 已实现 `<picture>` + `<source>` 响应式渲染
4. **风险可控**: Feature Flag 秒切回滚

## 4. 详细设计（方案 A+）

### 4.1 新增: `server/utils/hub-spoke-adapter.ts`

核心转换模块，职责：Payload HubSpokePage → HubData/SpokeData。

```typescript
// 关键函数签名

/** blockType "hsHero" → type "hero" */
function fromBlockSlug(blockType: string): HubSpokeComponentType

/** Payload block 平铺字段 → { id, type, props } */
function transformBlock(block: PayloadBlock): HubSpokeComponent

/** Media 对象 → ResolvedImage（含 sizes URL） */
function resolveMedia(val: unknown): ResolvedImage | string | null

/** 递归处理 props: Media→ResolvedImage, {name}[]→string[], 关联对象→slug */
function transformProps(obj: unknown): unknown

/** Payload 文档 → HubData */
function toHubData(doc: HubSpokePage): HubData

/** Payload 文档 → SpokeData */
function toSpokeData(doc: HubSpokePage): SpokeData
```

#### 图片模型: ResolvedImage

```typescript
/** 从 Payload Media 解析出的响应式图片数据，对齐 mdx/media-image.vue props */
interface ResolvedImage {
  url: string           // 原图 URL (fallback)
  srcSmall?: string     // sizes.small.url (600px)
  srcMedium?: string    // sizes.medium.url (900px)
  srcLarge?: string     // sizes.large.url (1400px)
  srcXlarge?: string    // sizes.xlarge.url (1920px)
  alt?: string
  width?: number
  height?: number
}
```

CMS Media 7 种 sizes → 前端取 4 种断点（small/medium/large/xlarge），对齐 `media-image.vue` 的 props 接口。

#### 转换规则（逐项）

**1. blockType → type**
```
"hsHero"          → "hero"
"hsArticleHeader" → "articleHeader"
"hsCategoryCards" → "categoryCards"
规则: 去掉 "hs" 前缀，首字母小写
```

**2. 平铺字段 → props 封装**
```
Payload: { blockType: "hsHero", id: "x", blockName: null, title: "...", backgroundImage: {...} }
输出:    { id: "x", type: "hero", props: { title: "...", backgroundImage: ResolvedImage } }
排除字段: blockType, blockName (Payload 元字段)
保留字段: id → 提升到顶层
```

**3. Media 对象 → ResolvedImage**
```typescript
function resolveMedia(val: unknown): ResolvedImage | string | null {
  if (!val || typeof val === 'string') return val as string | null
  if (typeof val === 'object' && 'url' in val && 'mimeType' in val) {
    const media = val as PayloadMedia
    return {
      url: media.url,
      srcSmall: media.sizes?.small?.url,
      srcMedium: media.sizes?.medium?.url,
      srcLarge: media.sizes?.large?.url,
      srcXlarge: media.sizes?.xlarge?.url,
      alt: media.alt,
      width: media.width,
      height: media.height,
    }
  }
  return null
}
```

**4. 对象数组 → 字符串数组（单字段 array）**
```
CMS:  tags: [{ name: "AI", id: "abc" }, { name: "3D", id: "def" }]
输出: tags: ["AI", "3D"]
```
检测标准: 数组中每个元素都是 `{ name: string, id?: string }` 且只有这两个键

**5. hubSlug 关联解析**
```
CMS:  hubSlug: { id: "abc", slug: "tutorials", title: "..." }  // depth=2 展开
输出: hubSlug: "tutorials"
```

**6. SEO meta 映射**
```
CMS:  meta: { title, description, image: Media, keywords: [{ keyword: "k1" }] }
输出: meta: { title, description, ogImage: ResolvedImage, keywords: ["k1"] }
```

**7. Navigation group 处理**
```
CMS:  previousSpoke: { title: "...", url: "...", thumbnail: Media }
输出: previousSpoke: { title: "...", url: "...", thumbnail: ResolvedImage }
注意: CMS group 有 defaultValue: {}，空对象需处理为 undefined
```

### 4.2 新增: `server/utils/hub-spoke-cms.ts`

CMS 数据获取层，复用 `usePayloadSDK()`。

```typescript
export async function fetchHubFromCMS(slug: string, locale: string): Promise<HubData>
export async function fetchSpokeFromCMS(hubSlug: string, spokeSlug: string, locale: string): Promise<SpokeData>
```

查询模式:
```
GET {CMS_URL}/api/hub-spoke-pages
  ?where[slug][equals]={slug}
  &where[type][equals]=hub|spoke
  &locale={locale}
  &depth=2
  &draft=false
```

注意:
- `depth=2` 确保 Media 和关联文档完整展开
- `draft=false` 只取已发布文档
- 查询结果可能为空（该 locale 下无内容），返回 404

### 4.3 改造: `server/api/crescendia/hub/[slug].get.ts`

```typescript
// Before: fetchHub(slug, refresh, lang) from crescendia.ts
// After:  fetchHubFromCMS(slug, lang) from hub-spoke-cms.ts

export default defineEventHandler(async (event) => {
  const slug = getRouterParam(event, 'slug')
  if (!slug) throw createError({ message: 'Missing hub slug', statusCode: 400 })

  const query = getQuery(event)
  const lang = /* 现有 locale 解析逻辑不变 */

  // 数据源切换（feature flag 可选）
  const data = await fetchHubFromCMS(slug, lang)

  if (data?.components?.length) {
    data.components = await parseContentBlocks(data.components)
  }

  return data
})
```

### 4.4 改造: `server/api/crescendia/spoke/[...path].get.ts`

同理，`fetchSpoke()` → `fetchSpokeFromCMS()`。

hubTitle 注入逻辑调整：CMS 中 spoke 如果 hubSlug 关联了 Hub 文档（depth=2），可直接从关联对象取 title，不再单独请求。

### 4.5 类型变更: `shared/types/pages/hub-spoke.ts`

图片字段从 `string` 扩展为 `string | ResolvedImage`:

```typescript
// 新增 ResolvedImage 类型（从 adapter 导出）
import type { ResolvedImage } from '~~/server/utils/hub-spoke-adapter'

// 受影响的接口字段:
HsHeroProps.backgroundImage:       string → string | ResolvedImage
HsArticleHeaderProps.coverImage:   string → string | ResolvedImage
HsAuthor.avatar:                   string → string | ResolvedImage
HsCategoryCard.icon:               string → string | ResolvedImage
HsTutorialItem.thumbnail:          string → string | ResolvedImage
HsVideoItem.thumbnail:             string → string | ResolvedImage
HsTipBoxProps.icon:                string → string | ResolvedImage
HsCtaBannerProps.backgroundImage:  string → string | ResolvedImage
HsGalleryImage.src:                string → string | ResolvedImage
HsVideoEmbedProps.thumbnail:       string → string | ResolvedImage
HsStepItem.image:                  string → string | ResolvedImage
HsDownloadCard.imageUrl:           string → string | ResolvedImage
SpokeNavigation.thumbnail:         string → string | ResolvedImage
HsPageMeta.ogImage:                string → string | ResolvedImage
HsRelatedHub.thumbnail:            string → string | ResolvedImage
HsSubItem.icon:                    string → string | ResolvedImage
```

### 4.6 组件适配: 改造 `hub-spoke/image.vue` 内部集成

**核心思路**: 在 `HubSpokeImage` 内部集成 `<picture>` + `<source>` 响应式渲染，12 个上游组件零改动。

```vue
<!-- 改造后的 hub-spoke/image.vue -->
<template>
  <!-- ResolvedImage: 响应式 picture + source（复用 media-image.vue 的断点逻辑） -->
  <picture v-if="isResolved">
    <source v-if="resolved.srcXlarge" :srcset="resolved.srcXlarge" media="(min-width: 1400px)" />
    <source v-if="resolved.srcLarge" :srcset="resolved.srcLarge" media="(min-width: 900px)" />
    <source v-if="resolved.srcMedium" :srcset="resolved.srcMedium" media="(min-width: 600px)" />
    <img ref="imgRef" :src="resolved.url" :alt="resolved.alt || alt"
         :width="resolved.width" :height="resolved.height"
         loading="lazy" decoding="async" v-bind="$attrs" />
  </picture>
  <!-- string: 原有行为（Crescendia 回退 + 错误处理） -->
  <img v-else ref="imgRef" :src="currentSrc" :alt="alt" @error="onError" v-bind="$attrs" />
</template>

<script setup lang="ts">
import type { ResolvedImage } from '~~/server/utils/hub-spoke-adapter'

const props = withDefaults(defineProps<{
  alt?: string
  fallback?: string
  src: string | ResolvedImage  // 扩展支持 ResolvedImage
}>(), { alt: '', fallback: '' })

const isResolved = computed(() => typeof props.src === 'object' && props.src !== null)
const resolved = computed(() => isResolved.value ? props.src as ResolvedImage : null)
// ... 原有 string 模式逻辑不变
</script>
```

**关键收益**:
- 12 个上游组件调用方式完全不变: `<HubSpokeImage :src="props.backgroundImage" />`
- `src` 是 string → 走原有 `<img>` + 错误处理
- `src` 是 ResolvedImage → 走 `<picture>` + `<source>` 响应式渲染
- 断点规则对齐 `mdx/media-image.vue`: 600px/900px/1400px

### 4.7 Feature Flag（可选但推荐）

参考 Blog 系统的 `blogLegacy` 模式，在 `app-config` global 中新增 `hubSpokeLegacy` flag：
- `true`（默认）：走 Crescendia API（现有逻辑）
- `false`：走 CMS API

优点：灰度切换，出问题秒回滚，不需要回滚代码。

### 4.6 Sitemap 集成

新增 `server/routes/sitemaps/hub-spoke/[slug].get.ts`:
- 查询 CMS `GET /api/hub-spoke-sitemap-meta` 获取各语言页面计数
- 按语言生成 sitemap 条目（slug + updatedAt）

注册到 `sitemap-dynamic.xml.get.ts` 的 sitemapindex。

### 4.9 文件改动清单

| 操作 | 文件 | 说明 |
|------|------|------|
| 新增 | `server/utils/hub-spoke-adapter.ts` | Payload → HubData/SpokeData 转换 + ResolvedImage 类型 |
| 新增 | `server/utils/hub-spoke-cms.ts` | CMS 数据获取层 |
| 改造 | `server/api/crescendia/hub/[slug].get.ts` | 数据源切换 |
| 改造 | `server/api/crescendia/spoke/[...path].get.ts` | 数据源切换 |
| 改造 | `shared/types/pages/hub-spoke.ts` | 图片字段 string → string \| ResolvedImage |
| 改造 | `app/components/hub-spoke/image.vue` | 内部集成 `<picture>` + `<source>` 响应式 |
| 新增 | `server/routes/sitemaps/hub-spoke/[slug].get.ts` | Hub-spoke sitemap |
| 改造 | `server/routes/sitemap-dynamic.xml.get.ts` | 注册 hub-spoke sitemap |
| 不变 | `app/components/hub-spoke/*.vue` (除 image.vue) | **12 个组件零改动** |
| 不变 | `app/pages/[...slug].vue` | 页面不变 |
| 不变 | `app/composables/*.ts` | composable 不变 |

**核心改动: 2 新增 + 4 改造 + 2 sitemap = 8 文件**
**零改动: 12 个图片组件 + 页面 + composable**

## 5. 工作量评估

| 阶段 | 工作内容 | 估时 |
|------|---------|------|
| Step 1 | 单篇推送验证（脚本调用 staging CMS） | 0.5h |
| Step 2 | 全量推送联调（推送所有 Crescendia 数据） | 1h |
| Step 3a | hub-spoke-adapter.ts 转换模块（含 ResolvedImage）+ 单元测试 | 3h |
| Step 3b | hub-spoke-cms.ts 数据获取层 | 1h |
| Step 3c | API handler 改造 + Feature Flag | 1h |
| Step 3d | 类型变更 + hub-spoke/image.vue 改造 | 1.5h |
| Step 3e | Sitemap 集成 | 1.5h |
| Step 3f | 端到端联调验证（本地 CMS + 前端） | 2h |
| **总计** | | **~11.5h（~1.5 工作日）** |

预计完成时间: 2026-04-15 提测，04-16 deadline 前完成。

## 6. 风险评估

| 风险 | 等级 | 影响 | 缓解措施 |
|------|------|------|---------|
| Crescendia 数据 → CMS 推送有字段丢失 | 中 | 页面渲染不完整 | Step 2 全量联调排查 |
| CMS 发布流程不畅（draft→publish） | 低 | 页面 404 | staging 上提前走通发布流程 |
| 图片 Media 对象未正确展开（depth 不够） | 低 | 图片显示异常 | 固定 depth=2，测试验证 |
| contentBlock Markdown 解析差异 | 中 | 内容样式异常 | CMS 存储原文与 Crescendia 一致，parseContentBlocks 不变 |
| 性能：CMS API 响应时间 > Crescendia | 低 | 页面加载变慢 | staging 上对比测试响应时间 |
| 多语言：locale 字段缺失 | 低 | 非英语页面 404 | Step 2 推送时覆盖多语言数据 |

## 7. 测试计划

### 单元测试
- `hub-spoke-adapter.ts` 所有转换函数
  - blockType → type 映射（17 种）
  - Media 对象 → URL 提取
  - 对象数组 → 字符串数组
  - hubSlug 关联解析
  - SEO meta 映射
  - 空值/undefined 边界处理

### 集成测试
- API handler 返回的 HubData/SpokeData 结构与现有 Crescendia 输出一致
- 多语言切换（en/zh/ja）数据正确
- 404 场景（不存在的 slug、未发布的 draft）

### 端到端验证
- 本地 CMS + 前端联调
- 5 个 Hub 页面渲染正确（tutorials, 3d-print, game-development, media-production, ai-3d-home-design）
- Spoke 页面渲染正确
- 图片加载正确（OSS CDN URL）
- Markdown 内容解析正确
- SEO meta 正确
- 面包屑导航正确
- 前后翻页导航正确

## 8. 回滚方案

- **Feature Flag 秒切**: `hubSpokeLegacy: true` 即刻恢复 Crescendia 数据源
- **代码回滚**: API handler 恢复 `fetchHub()`/`fetchSpoke()` 调用，无组件改动需要回滚
