# 技术方案：Blog & Features 页面 JSON-LD 结构化数据

## 需求概述

为 fe-tripo-homepage 的 Blog Index、Blog 详情、Features、Hub-Spoke 页面添加 JSON-LD 结构化数据，同时拆分现有 seo-json.ts（2045行）为模块化文件。

## 方案对比

### 方案 A：在现有 seo-json.ts 中追加（不推荐）

- 优点：改动最小，一个文件
- 缺点：文件将膨胀到 2500+ 行，可维护性差
- 结论：❌ 不采用

### 方案 B：拆分 seo-json.ts + 新增模块化文件（推荐）

- 优点：每个文件职责单一，200-400 行，易维护
- 缺点：需要更新所有现有导入路径
- 结论：✅ 采用

### 方案 C：只新增文件不拆分（折中）

- 优点：不动现有代码，风险最低
- 缺点：seo-json.ts 仍然臃肿，不解决根本问题
- 结论：❌ 不采用

## 详细设计

### 文件拆分方案

```
app/composables/
├── seo-json-shared.ts          # 公共工具函数（从 seo-json.ts 提取）
├── seo-json-tools.ts           # Converter + Viewer schema（原 seo-json.ts 主体）
├── seo-json-landing.ts         # Landing page schema（从 seo-json.ts 提取）
├── seo-json-blog.ts            # 【新增】Blog JSON-LD
├── seo-json-features.ts        # 【新增】Features JSON-LD
├── seo-json-hub-spoke.ts       # 【新增】Hub-Spoke JSON-LD
└── seo-json.ts                 # 保留为 barrel 文件，re-export 所有公共 API
```

#### seo-json-shared.ts（~60行）

从 seo-json.ts 提取：
- `SchemaRoot` 类型
- `BASE_URL`、`LOGO_URL` 常量
- `buildLocalizedUrl(path, locale)` 函数
- `buildLogoObject(locale)` 函数
- `buildFaqSchema(pageWebPageId, faqItems)` 函数
- `buildBreadcrumbSchema(items)` 函数 【新增】

#### seo-json.ts（保留为 barrel）

```typescript
// 保持向后兼容，re-export 所有公共 API
export { useConverterSeoJson, useViewerGeneralSeoJson, ... } from './seo-json-tools';
export { useLandingPageSeoJson } from './seo-json-landing';
export { useBlogPostingSeoJson, useBlogIndexSeoJson } from './seo-json-blog';
export { useFeaturesSeoJson } from './seo-json-features';
export { useHubSpokeSeoJson } from './seo-json-hub-spoke';
```

这样现有页面的 `import { useConverterSeoJson } from '~/composables/seo-json'` 无需修改。

### 新增 JSON-LD 详细设计

#### 1. seo-json-blog.ts

**导出函数：**

##### `useBlogIndexSeoJson()`

无参数，注入 BreadcrumbList：

```json
{
  "@context": "https://schema.org",
  "@type": "BreadcrumbList",
  "itemListElement": [
    { "@type": "ListItem", "position": 1, "item": { "@id": "https://www.tripo3d.ai/", "name": "Home" } },
    { "@type": "ListItem", "position": 2, "item": { "@id": "https://www.tripo3d.ai/blog", "name": "Blog" } }
  ]
}
```

##### `useBlogPostingSeoJson(page)`

参数：`page: MaybeRefOrGetter<BlogDetailResponse | null>`

注入 BlogPosting + BreadcrumbList：

```json
{
  "@context": "https://schema.org/",
  "@type": "BlogPosting",
  "@id": "{canonicalUrl}#blogposting",
  "mainEntityOfPage": "{canonicalUrl}",
  "headline": "{title}",
  "name": "{title}",
  "description": "{description}",
  "datePublished": "{date}",
  "dateModified": "{date}",
  "publisher": {
    "@type": "Organization",
    "@id": "https://www.tripo3d.ai/#organization",
    "name": "Tripo AI",
    "logo": { "..." }
  },
  "image": { "@type": "ImageObject", "url": "{LOGO_URL}" },
  "url": "{canonicalUrl}",
  "isPartOf": {
    "@type": "Blog",
    "@id": "https://www.tripo3d.ai/blog",
    "name": "Tripo Blog",
    "publisher": { "@type": "Organization", "@id": "https://www.tripo3d.ai", "name": "Tripo" }
  },
  "keywords": ["{keywords}"],
  "aggregateRating": {
    "@type": "AggregateRating",
    "@id": "{canonicalUrl}/#aggregate",
    "url": "{canonicalUrl}",
    "ratingValue": "{hashBased 4.2~4.8}",
    "ratingCount": "{hashBased 10~100}"
  }
}
```

**关键实现细节：**

- `publishedAt`：Payload CMS 的 `PayloadPost.publishedAt` 字段存在但未被 `baseMeta` 消费。需在 `server/api/blog/[...slug].get.ts` 的 `baseMeta` 中补充 `publishedAt: post.publishedAt`，并在 `BlogBaseMeta` 接口中新增该字段。`datePublished` 使用 `publishedAt`，`dateModified` 使用 `date`（映射自 `createdAt`）
- `heroImage`：Payload CMS 返回的 JSON 中包含 `heroImage` 字段（`depth: 2` 展开），但 `PayloadPost` 类型未声明。需在 `PayloadPost` 中补充 `heroImage?: { url?: string }`，并在 `baseMeta` 中传递 `heroImage: post.heroImage?.url`，同时在 `BlogBaseMeta` 中新增该字段
- `wordCount`：按内容类型在 API 层估算：
  - `lexical`：递归遍历 `post.content.root` 收集所有 `text` 节点，拼接后 `.split(/\s+/).length`
  - `markdown`/`legacy-markdown`：`post.markdown.replace(/[#*\`\[\]()>_~]/g, '').split(/\s+/).length`
  - 在 `BlogBaseMeta` 中新增 `wordCount?: number` 字段
- `aggregateRating`：基于 slug 哈希生成稳定伪随机值

```typescript
function hashCode(str: string): number {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    hash = ((hash << 5) - hash) + str.charCodeAt(i);
    hash |= 0;
  }
  return Math.abs(hash);
}

function buildAggregateRating(slug: string, canonicalUrl: string) {
  const hash = hashCode(slug);
  return {
    '@type': 'AggregateRating',
    '@id': `${canonicalUrl}/#aggregate`,
    'url': canonicalUrl,
    'ratingValue': (4.2 + (hash % 7) * 0.1).toFixed(1),
    'ratingCount': 10 + (hash % 91),
  };
}
```

#### 2. seo-json-features.ts

**导出函数：**

##### `useFeaturesSeoJson(page)`

参数：`page: MaybeRefOrGetter<FeatureConfig | null | undefined>`

注入 FAQPage + BreadcrumbList + SoftwareApplication：

**FAQPage**：复用 `buildFaqSchema`，数据来自 `featureData.faq.items`

**BreadcrumbList**：
```json
{
  "itemListElement": [
    { "position": 1, "item": { "@id": "https://www.tripo3d.ai/", "name": "Home" } },
    { "position": 2, "item": { "@id": "https://www.tripo3d.ai/features", "name": "Features" } },
    { "position": 3, "item": { "@id": "{canonicalUrl}", "name": "{featureTitle}" } }
  ]
}
```

**SoftwareApplication**：
```json
{
  "@type": "SoftwareApplication",
  "@id": "{canonicalUrl}#softwareapplication",
  "name": "{hero.title}",
  "url": "{canonicalUrl}",
  "applicationCategory": "DesignApplication",
  "operatingSystem": "Web",
  "description": "{seo.description}",
  "publisher": { "@type": "Organization", "@id": "https://www.tripo3d.ai/#organization", "name": "Tripo AI" },
  "potentialAction": {
    "@type": "UseAction",
    "target": { "@type": "EntryPoint", "urlTemplate": "{hero.ctaLink}" }
  }
}
```

**数据来源**：
- FAQ：`page.faq.items`（`{ question, answer }[]`）
- Feature name：从路由 `useRoute().path` 提取，或从 `page.hero.title` 获取
- CTA URL：`page.hero.ctaLink`

#### 3. seo-json-hub-spoke.ts

**导出函数：**

##### `useHubSpokeSeoJson(page)`

参数：`page: MaybeRefOrGetter<HubSpokeData | undefined>`

根据 `page.type` 自动判断 Hub 或 Spoke，注入对应 schema：

**Hub 页面注入：** FAQPage + BreadcrumbList + ItemList
**Spoke 页面注入：** FAQPage + BreadcrumbList

**FAQ 提取逻辑**：
```typescript
const faqComponent = page.components.find(c => c.type === 'faq');
const faqItems = faqComponent?.props?.items ?? [];
```

**BreadcrumbList（Hub）**：Home → {hubTitle}
**BreadcrumbList（Spoke）**：Home → {hubTitle} → {spokeTitle}

Hub 的 breadcrumb 数据来自 `page.breadcrumb`（`HsBreadcrumb[]`），如果存在则直接使用。

**ItemList（仅 Hub）**：

从 Hub 的 `components` 数组中提取 spoke 链接，三种组件类型包含 spoke 跳转：

```typescript
function extractSpokeLinks(components: HubSpokeComponent[]): Array<{ url: string; name: string }> {
  const links: Array<{ url: string; name: string }> = [];

  for (const c of components) {
    if (c.type === 'categoryCards') {
      const props = c.props as HsCategoryCardsProps;
      for (const card of props.cards) {
        if (card.link) links.push({ url: card.link, name: card.title });
      }
    }
    else if (c.type === 'tutorialList') {
      const props = c.props as HsTutorialListProps;
      for (const item of props.items) {
        if (item.link) links.push({ url: item.link, name: item.title });
      }
    }
    else if (c.type === 'relatedLinks') {
      const props = c.props as HsRelatedLinksProps;
      for (const link of props.links) {
        if (link.url) links.push({ url: link.url, name: link.title });
      }
    }
  }

  return links;
}
```

注意：`tocNav` 组件的 `items[].url` 是页内锚点（如 `#section-1`），不是 spoke 链接，不纳入提取。

### useHead 注入模式（统一）

所有新增 composable 遵循现有模式：

```typescript
export function useXxxSeoJson(page: MaybeRefOrGetter<T | null | undefined>) {
  const { locale } = useI18n();

  const schema = computed<SchemaRoot | null>(() => {
    const pageValue = toValue(page);
    if (!pageValue) return null;
    return buildXxxSchema(pageValue, locale.value);
  });

  useHead(() => {
    if (!schema.value) return {};
    return {
      __dangerouslyDisableSanitizersByTagID: {
        'schema-xxx': ['innerHTML'],
      },
      script: [
        {
          id: 'schema-xxx',
          innerHTML: JSON.stringify(schema.value),
          type: 'application/ld+json',
        },
      ],
    };
  });
}
```

### 页面调用方式

#### Blog 列表页 `app/pages/blog/index.vue`

```typescript
import { useBlogIndexSeoJson } from '~/composables/seo-json-blog';
// 在 setup 中
useBlogIndexSeoJson();
```

#### Blog 详情页 `app/pages/blog/[...slug].vue`

```typescript
import { useBlogPostingSeoJson } from '~/composables/seo-json-blog';
// 在 setup 中
useBlogPostingSeoJson(page);
```

#### Features 页面 `app/pages/features/*.vue`

```typescript
import { useFeaturesSeoJson } from '~/composables/seo-json-features';
// 在 setup 中（featureData 已通过 queryCollection 获取）
useFeaturesSeoJson(() => featureData);
```

#### Hub-Spoke 页面 `app/pages/[...slug].vue`

```typescript
import { useHubSpokeSeoJson } from '~/composables/seo-json-hub-spoke';
// 在 setup 中
useHubSpokeSeoJson(page);
```

## 涉及模块

| 文件 | 操作 | 说明 |
|------|------|------|
| `server/types/blog.ts` | 修改 | BlogBaseMeta 补充 publishedAt/heroImage/wordCount 字段 |
| `server/api/blog/[...slug].get.ts` | 修改 | baseMeta 补充 publishedAt/heroImage/wordCount |
| `app/composables/seo-json-shared.ts` | 新建 | 公共工具函数 |
| `app/composables/seo-json-tools.ts` | 新建 | 从 seo-json.ts 迁移 Converter+Viewer |
| `app/composables/seo-json-landing.ts` | 新建 | 从 seo-json.ts 迁移 Landing |
| `app/composables/seo-json-blog.ts` | 新建 | Blog JSON-LD |
| `app/composables/seo-json-features.ts` | 新建 | Features JSON-LD |
| `app/composables/seo-json-hub-spoke.ts` | 新建 | Hub-Spoke JSON-LD |
| `app/composables/seo-json.ts` | 重写 | 改为 barrel re-export |
| `app/pages/blog/index.vue` | 修改 | 添加 useBlogIndexSeoJson() |
| `app/pages/blog/[...slug].vue` | 修改 | 添加 useBlogPostingSeoJson(page) |
| `app/pages/features/*.vue`（9个） | 修改 | 添加 useFeaturesSeoJson() |
| `app/pages/[...slug].vue` | 修改 | 添加 useHubSpokeSeoJson(page) |
| `app/composables/__tests__/seo-json-shared.test.ts` | 新建 | 公共工具函数测试 |
| `app/composables/__tests__/seo-json-blog.test.ts` | 新建 | Blog schema 测试 |
| `app/composables/__tests__/seo-json-features.test.ts` | 新建 | Features schema 测试 |
| `app/composables/__tests__/seo-json-hub-spoke.test.ts` | 新建 | Hub-Spoke schema 测试 |
| `app/composables/__tests__/seo-json-tools-barrel.test.ts` | 新建 | barrel re-export 兼容性测试 |

## 工作量评估

| 任务 | 预估 |
|------|------|
| 拆分 seo-json.ts | 中（代码迁移 + 验证导入） |
| seo-json-blog.ts | 小（~150行） |
| seo-json-features.ts | 小（~120行） |
| seo-json-hub-spoke.ts | 中（~180行，ItemList 逻辑复杂） |
| 页面调用集成 | 小（每个页面加 1-2 行） |
| TypeScript + ESLint 验证 | 小 |

总计：中等工作量

## 风险评估

| 风险 | 等级 | 应对 |
|------|------|------|
| seo-json.ts 拆分后导入路径断裂 | 中 | barrel re-export 保持向后兼容 + barrel 导入测试 |
| Blog API 层补充字段影响现有逻辑 | 低 | 新增可选字段，不改现有字段语义 |
| Hub ItemList 某些 Hub 页面无 spoke 链接组件 | 低 | extractSpokeLinks 返回空数组时跳过 ItemList |
| aggregateRating 被 Google 质疑 | 低 | slug 哈希保证稳定性 |

## 测试计划

### 测试基础设施

- 框架：vitest 4.1.0，分 `unit` 和 `nuxt` 两个 project
- seo-json 相关测试归属 `unit` project（纯函数，无 Nuxt runtime 依赖）
- 测试文件位置：`app/composables/__tests__/seo-json-*.test.ts`
- 运行命令：`pnpm test:unit`
- 参考范例：`app/composables/__tests__/use-hub-spoke-seo.test.ts`

### 测试文件清单

#### 1. `app/composables/__tests__/seo-json-shared.test.ts`

验证拆分后的公共工具函数行为不变：

| 用例 | 说明 |
|------|------|
| `buildLocalizedUrl` 英文路径不加前缀 | `buildLocalizedUrl('/blog', 'en')` → `https://www.tripo3d.ai/blog` |
| `buildLocalizedUrl` 非英文路径加前缀 | `buildLocalizedUrl('/blog', 'zh')` → `https://www.tripo3d.ai/zh/blog` |
| `buildLocalizedUrl` 路径无斜杠自动补齐 | `buildLocalizedUrl('blog', 'en')` → `https://www.tripo3d.ai/blog` |
| `buildLogoObject` 返回正确结构 | 包含 `@type: ImageObject`、`contentUrl`、`url` |
| `buildLogoObject` 英文 inLanguage 映射 | `locale='en'` → `inLanguage: 'en-us'` |
| `buildFaqSchema` 生成正确 FAQPage | 验证 `@type`、`mainEntity` 数组、`Question`/`Answer` 嵌套 |
| `buildFaqSchema` 空数组不报错 | `faqItems=[]` → `mainEntity: []` |
| `buildBreadcrumbSchema` 生成正确结构 | 验证 `@type: BreadcrumbList`、`itemListElement` position 递增 |

#### 2. `app/composables/__tests__/seo-json-blog.test.ts`

| 用例 | 说明 |
|------|------|
| `buildBlogPostingSchema` 基本字段映射 | title → headline/name，description → description，date → datePublished/dateModified |
| `buildBlogPostingSchema` 缺少 title 时使用空字符串 | `title: undefined` → `headline: ''` |
| `buildBlogPostingSchema` 缺少 date 时跳过日期字段 | 不输出 datePublished/dateModified |
| `buildBlogPostingSchema` publisher 结构正确 | 包含 Organization + logo ImageObject |
| `buildBlogPostingSchema` isPartOf 指向 Blog | `@type: Blog`，`@id` 包含 `/blog` |
| `buildBlogPostingSchema` keywords 数组正确传递 | `['ai', '3d']` → `keywords: ['ai', '3d']` |
| `buildAggregateRating` 哈希稳定性 | 同一 slug 多次调用返回相同值 |
| `buildAggregateRating` 值域范围 | ratingValue ∈ [4.2, 4.8]，ratingCount ∈ [10, 100] |
| `buildAggregateRating` 不同 slug 产生不同值 | `'post-a'` 和 `'post-b'` 的 rating 不完全相同 |
| `buildBlogIndexBreadcrumb` 结构正确 | Home → Blog，2 个 ListItem |
| `buildBlogPostingBreadcrumb` 结构正确 | Home → Blog → {title}，3 个 ListItem |
| `buildBlogPostingBreadcrumb` 多语言 URL | `locale='zh'` → URL 带 `/zh` 前缀 |

#### 3. `app/composables/__tests__/seo-json-features.test.ts`

| 用例 | 说明 |
|------|------|
| `buildFeaturesFaqSchema` 正确映射 FAQ items | 从 `page.faq.items` 生成 FAQPage |
| `buildFeaturesFaqSchema` 无 FAQ 数据时返回 null | `page.faq` 为空 → 不生成 FAQPage |
| `buildFeaturesBreadcrumb` 结构正确 | Home → Features → {name}，3 个 ListItem |
| `buildSoftwareApplicationSchema` 基本字段 | name、url、applicationCategory、operatingSystem |
| `buildSoftwareApplicationSchema` publisher 正确 | Organization + Tripo AI |
| `buildSoftwareApplicationSchema` potentialAction | UseAction + EntryPoint + ctaLink |
| `buildFeaturesSchema` 完整 @graph | 包含 FAQPage + BreadcrumbList + SoftwareApplication 三个节点 |

#### 4. `app/composables/__tests__/seo-json-hub-spoke.test.ts`

| 用例 | 说明 |
|------|------|
| `buildHubSpokeSchema` Hub 页面生成 3 种 schema | FAQPage + BreadcrumbList + ItemList |
| `buildHubSpokeSchema` Spoke 页面生成 2 种 schema | FAQPage + BreadcrumbList |
| Hub FAQ 从 components 中正确提取 | `components: [{ type: 'faq', props: { items: [...] } }]` |
| Hub FAQ 无 faq 组件时跳过 | `components: [{ type: 'hero' }]` → 不生成 FAQPage |
| Hub BreadcrumbList 使用 breadcrumb 数据 | 从 `page.breadcrumb` 生成 |
| Hub BreadcrumbList 无 breadcrumb 时 fallback | Home → {title} |
| Spoke BreadcrumbList 包含 hub 层级 | Home → {hubTitle} → {spokeTitle} |
| Hub ItemList 从 components 提取 spoke 链接 | 验证 position 递增、url 和 name 正确 |
| Hub ItemList 无可提取数据时跳过 | 不生成 ItemList |

#### 5. `app/composables/__tests__/seo-json-tools-barrel.test.ts`

验证拆分后 barrel re-export 的向后兼容性：

| 用例 | 说明 |
|------|------|
| 从 `seo-json.ts` 导入 `useConverterSeoJson` 成功 | barrel 导出正确 |
| 从 `seo-json.ts` 导入 `useViewerGeneralSeoJson` 成功 | barrel 导出正确 |
| 从 `seo-json.ts` 导入 `useLandingPageSeoJson` 成功 | barrel 导出正确 |
| 从 `seo-json.ts` 导入新增 `useBlogPostingSeoJson` 成功 | 新增导出可用 |
| 从 `seo-json.ts` 导入新增 `useFeaturesSeoJson` 成功 | 新增导出可用 |
| 从 `seo-json.ts` 导入新增 `useHubSpokeSeoJson` 成功 | 新增导出可用 |

### 静态验证

1. `pnpm typecheck` — TypeScript 类型检查通过
2. `pnpm lint` — ESLint 检查通过

### 手动验证

1. 本地启动 `pnpm dev`，访问各页面检查 JSON-LD 输出
2. 使用 Google 富媒体结果测试验证 JSON-LD 格式
3. 确认现有 Viewer/Converter/Landing 页面的 JSON-LD 未受影响

### 开发顺序

遵循 TDD：先写测试 → 红灯 → 实现 → 绿灯 → 重构

1. 先写 `seo-json-shared.test.ts` → 拆分 shared 函数 → 绿灯
2. 写 `seo-json-tools-barrel.test.ts` → 拆分 tools/landing + barrel → 绿灯
3. 写 `seo-json-blog.test.ts` → 实现 blog schema → 绿灯
4. 写 `seo-json-features.test.ts` → 实现 features schema → 绿灯
5. 写 `seo-json-hub-spoke.test.ts` → 实现 hub-spoke schema → 绿灯
6. 集成到页面文件 → typecheck + lint → 手动验证
