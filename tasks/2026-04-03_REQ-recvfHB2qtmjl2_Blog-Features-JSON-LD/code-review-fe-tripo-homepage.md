# Code Review Report: PR #181 - Blog & Features JSON-LD Structured Data

**审查分支**: `feature/REQ-recvfHB2qtmjl2-blog-features-json-ld`
**审查人**: Senior Code Reviewer
**审查日期**: 2026-04-03
**PR 内容**: 拆分 seo-json.ts (2045行) 为 6 个模块化 composable + 新增 Blog/Features/Hub-Spoke JSON-LD

---

## 执行摘要

本次 PR 完成了大量有价值的工作：成功将 2045 行的大文件拆分为 6 个职责单一的文件，新增了 3 类页面共 4 种 schema，新增了详尽的测试覆盖（5 个测试文件共 686 行测试代码）。整体架构设计合理，barrel re-export 保持了向后兼容。

发现 **1 个 CRITICAL 问题**（Spoke 页面面包屑逻辑错误，会导致 SEO 结构数据错误）、**1 个 HIGH 问题**（`isPartof` 拼写错误影响 schema.org 规范合规性）、**2 个 MEDIUM 问题** 和 **4 个 LOW 问题**。建议在合并前修复所有 HIGH 和 CRITICAL 问题。

---

## CRITICAL 问题

### 1. Spoke 页面面包屑使用错误的标题 (Spoke title 代替 Hub title)

**文件**: `app/composables/seo-json-hub-spoke.ts` 第 72-76 行

**问题描述**: 在 Spoke 页面的面包屑 fallback 逻辑中，Hub 层级的名称错误地使用了 Spoke 的 `page.title`：

```typescript
} else {
  graph.push(buildBreadcrumbSchema([
    { name: 'Home', url: buildLocalizedUrl('/', locale) },
    { name: page.title, url: buildLocalizedUrl(`/${page.hubSlug}`, locale) }, // BUG: page.title 是 Spoke 标题，不是 Hub 标题
    { name: page.title, url: canonicalUrl },
  ]));
}
```

`SpokeData` 接口没有 `hubTitle` 字段（只有 `hubSlug`），因此代码无法获取正确的 Hub 名称。虽然 API 提供了自定义 `breadcrumb` 数据，但当 `breadcrumb` 不存在时，fallback 逻辑会产生错误的面包屑：`Home → [SpokeTitle] → [SpokeTitle]`，而非正确的 `Home → [HubTitle] → [SpokeTitle]`。

**影响**: Google 富媒体结果测试将无法正确识别面包屑结构，SEO 效果受损。

**建议修复**: 如果 `SpokeData` 类型缺少 `hubTitle` 字段，需要在 `HubSpokeData` 接口或 API 层补充该字段：

```typescript
// 在 SpokeData 中添加 hubTitle
export interface SpokeData {
  hubTitle: string;  // 新增
  hubSlug: string;
  // ...
}
```

然后更新 fallback 逻辑：

```typescript
} else {
  graph.push(buildBreadcrumbSchema([
    { name: 'Home', url: buildLocalizedUrl('/', locale) },
    { name: page.hubTitle, url: buildLocalizedUrl(`/${page.hubSlug}`, locale) },
    { name: page.title, url: canonicalUrl },
  ]));
}
```

**严重性**: CRITICAL（影响 SEO 结构数据的正确性）

---

## HIGH 问题

### 2. `isPartof` 拼写错误（12处）—— 应为 `isPartOf`

**文件**: `app/composables/seo-json-tools.ts` 第 120, 148, 169, 321, 347, 423, 579, 842, 1111, 1380, 1649 行（共 11 处）

**问题描述**: `seo-json-tools.ts` 中的 FAQPage schema 使用了 `'isPartof'`（全小写 f），而 schema.org 规范要求为 camelCase 的 `isPartOf`。这些是迁移自原 `seo-json.ts` 的遗留问题。

同时，`app/composables/seo-json-shared.ts` 第 35 行已正确使用 `isPartOf`（camelCase）。

**对比**:
```typescript
// seo-json-tools.ts (错误)
'isPartof': { '@id': canonicalUrl, '@type': 'WebPage' }

// seo-json-shared.ts (正确)
'isPartOf': { '@id': pageWebPageId, '@type': 'WebPage' }
```

**影响**: 虽然 Google Search 对 FAQPage 的 `isPartOf` 引用宽松（FAQ 的可解析性主要依赖 `mainEntity`），但使用错误的属性名将导致 schema.org 验证器报错，不符合 schema.org 规范。

**建议修复**: 将 `seo-json-tools.ts` 中所有 11 处 `'isPartof'` 替换为 `'isPartOf'`。

**严重性**: HIGH（schema.org 规范合规性问题）

### 3. Barrel 导入测试未覆盖新增导出

**文件**: `app/composables/__tests__/seo-json-tools-barrel.test.ts`

**问题描述**: 技术方案要求验证新增的导出函数可通过 barrel 访问：
- `useBlogPostingSeoJson`
- `useFeaturesSeoJson`
- `useHubSpokeSeoJson`

但实际测试文件只验证了 6 个原有的 viewer/landing 函数（第 3-38 行），未包含新增的 3 个函数。

**建议修复**: 在测试文件中补充：
```typescript
it('exports useBlogPostingSeoJson from barrel', async () => {
  const mod = await import('../seo-json');
  expect(mod.useBlogPostingSeoJson).toBeTypeOf('function');
});

it('exports useFeaturesSeoJson from barrel', async () => {
  const mod = await import('../seo-json');
  expect(mod.useFeaturesSeoJson).toBeTypeOf('function');
});

it('exports useHubSpokeSeoJson from barrel', async () => {
  const mod = await import('../seo-json');
  expect(mod.useHubSpokeSeoJson).toBeTypeOf('function');
});
```

**严重性**: MEDIUM（测试覆盖不完整）

---

## MEDIUM 问题

### 4. Nuxt Auto-Import 重复警告

**文件**: `app/composables/seo-json.ts` 和 `app/composables/seo-json-tools.ts`

**问题描述**: 运行 `pnpm typecheck` 时出现 6 个 "Duplicated imports" 警告：

```
WARN  Duplicated imports "useConverterSeoJson", the one from "...seo-json-tools.ts" has been ignored and "...seo-json.ts" is used
WARN  Duplicated imports "useViewerFbxSeoJson", ...
...
```

这是因为 `seo-json.ts`（barrel）在 `app/composables/` 目录下，Nuxt 的 auto-import 机制会扫描该目录，而 `seo-json-tools.ts` 也在同一目录。Nuxt 同时检测到两个文件中的导出，导致重复警告。

**影响**: 不影响功能（Nuxt 自动选择 barrel 版本），但产生开发时的噪音信息，且长期来看可能导致不可预期的行为。

**建议修复**: 将 barrel 文件 `seo-json.ts` 移出 `app/composables/` 目录，或者在 `nuxt.config.ts` 中配置 `imports.dirs` 排除该目录。现有页面若要继续使用 `from '~/composables/seo-json'` 导入，需要显式引用绝对路径。

**严重性**: MEDIUM（产生警告，影响开发体验）

### 5. Blog API `wordCount` 对 `legacy-markdown` 类型逻辑不完整

**文件**: `server/api/blog/[...slug].get.ts`

**问题描述**: 当 `post.contentType === 'markdown'` 且 `post.isLegacy === true` 时，API 调用 `mdxToAST(ast)` 返回的结果包含 `content: { children: [...] }` 结构。但当前代码直接将 `...ast` 展开到返回对象，没有对 legacy markdown 内容独立计算 `wordCount`。

技术方案指出对 `legacy-markdown`/`markdown` 类型应使用 `countMarkdownWords(post.markdown)`，但 `markdown` 分支中 `isLegacy=true` 的 case（第 129-144 行）虽然添加了 `wordCount`，其值来自 `post.markdown`（正确），但返回的是 `...ast` 展开，其中可能不包含 `wordCount` 字段（`ast` 的内容来自 `mdxToAST`，结构是 `{ content, data }`）。

实际上，`mdxToAST` 返回的 `ast` 包含 `content: { children: [...] }` 结构，spread 后再加上 `wordCount`，所以 `wordCount` 会被覆盖。但语义上，这里应该直接基于 `post.markdown` 计算，而非依赖 `ast` 中可能不存在的字段。

更明确的做法：
```typescript
const mdxData = {
  content: post.markdown,
  data: { /* ... */ },
};
const ast = await mdxToAST(mdxData, `blog-${slug}`);
return {
  ...ast,
  type: 'legacy-markdown',
  wordCount: countMarkdownWords(post.markdown),  // 显式覆盖，确保值正确
} as BlogDetailResponse;
```

**严重性**: LOW（当前代码逻辑实际上是正确的，因为 `wordCount` 在 spread 后被显式赋值）

---

## LOW 问题

### 6. Features 页面导入风格不一致

**问题描述**: 13 个集成了 `useFeaturesSeoJson` 的页面中，导入风格不一致：
- 5 个页面显式 `import { useFeaturesSeoJson } from '~/composables/seo-json-features'`（`ai-texturing`, `image-gen-flux-kontext`, `image-gen-nano-banana`, `image-to-3d-model`, `text-to-3d-model`）
- 8 个页面依赖 Nuxt auto-import（`ai-auto-rigging`, `ai-model-segmentation`, `ai-model-stylization`, `image-gen-gpt-4o` 等）

由于 `seo-json-features.ts` 在 `app/composables/` 目录下，Nuxt 会自动导入，因此两种写法都能工作。但显式导入比 auto-import 更明确、可维护性更好。

**建议**: 统一为显式从具体文件导入，与 barrel `seo-json.ts` 保持一致的导入风格。

**严重性**: LOW（代码可读性一致性）

### 7. `aggregateRating.ratingValue` 类型不符合 schema.org 规范

**文件**: `app/composables/seo-json-blog.ts` 第 20 行

**问题描述**: `buildAggregateRating` 返回的 `ratingValue` 是字符串类型（`.toFixed(1)`），但 schema.org `AggregateRating` 要求 `ratingValue` 为 `Number` 类型：

```typescript
'ratingValue': (4.2 + (hash % 7) * 0.1).toFixed(1),  // 返回 string "4.2", "4.3", etc.
```

**建议修复**: 改为返回数字：
```typescript
'ratingValue': Number((4.2 + (hash % 7) * 0.1).toFixed(1)),
```
或：
```typescript
'ratingValue': parseFloat((4.2 + (hash % 7) * 0.1).toFixed(1)),
```

**严重性**: LOW（Google 对此相对宽松，但仍不符合 schema.org 规范）

### 8. `useBlogIndexSeoJson` 返回值类型标注不够精确

**文件**: `app/composables/seo-json-blog.ts` 第 117 行

**问题描述**:
```typescript
const schema = computed(() => {
  return {
    '@context': 'https://schema.org',
    '@graph': [
      buildBreadcrumbSchema([...]),
    ],
  };
});
```
返回类型没有显式标注为 `SchemaRoot`，而是依赖类型推断。相比之下，`useBlogPostingSeoJson` 标注了 `computed<SchemaRoot | null>`。

**建议**: 补充类型标注以保持一致性：
```typescript
const schema = computed<SchemaRoot>(() => ({
  '@context': 'https://schema.org',
  '@graph': [buildBreadcrumbSchema([...])],
}));
```

**严重性**: LOW（不影响功能，类型推断足够）

### 9. `seo-json-blog.ts` 顶部存在误导性注释

**文件**: `app/composables/seo-json-blog.ts` 第 1-2 行

```typescript
import type { BlogDetailResponse } from '~~/server/types/blog';
// server/api/blog/[...slug].get.ts
```

第 2 行的注释看起来像是误粘贴的，与文件内容无关。

**严重性**: LOW（代码清洁度）

---

## 测试覆盖评估

| 测试文件 | 行数 | 覆盖情况 |
|---------|------|---------|
| `seo-json-shared.test.ts` | 114 | 良好：覆盖了所有 shared 函数的基本用例 |
| `seo-json-blog.test.ts` | 179 | 良好：覆盖了 hash/rating/blog posting 的核心逻辑 |
| `seo-json-features.test.ts` | 82 | 中等：覆盖了 schema 生成但缺少 null/边界用例 |
| `seo-json-hub-spoke.test.ts` | 273 | 优秀：详细覆盖了 Hub/Spoke 两种场景 |
| `seo-json-tools-barrel.test.ts` | 38 | 不完整：缺少新增导出的验证 |

**测试亮点**:
- Hub-Spoke 测试中的 `tocNav` 跳过逻辑验证（确保页内锚点不被当作 spoke 链接）
- `aggregateRating` 哈希稳定性验证
- 多语言 URL 生成的验证

**测试缺口**:
- `useFeaturesSeoJson` 的 `page = null` 路径未测试
- `useHubSpokeSeoJson` 的 `page = null` 路径未测试
- Spoke 页面 breadcrumb 的 hub title 错误场景未被测试覆盖（这也说明 CRITICAL 问题 #1 未被测试发现）

---

## 计划对齐分析

| 计划内容 | 实现情况 | 偏差 |
|---------|---------|------|
| 拆分 6 个模块文件 | 完全符合 | 无偏差 |
| barrel re-export 向后兼容 | 符合，但产生 Nuxt 重复警告 | 轻微偏差（警告问题） |
| Blog API 补充 heroImage/publishedAt/wordCount | 符合 | 无偏差 |
| JSON-LD schema 结构 | 基本符合 | `isPartof` 拼写问题来自原文件 |
| Hub ItemList 提取逻辑 | 符合 | 无偏差 |
| FAQPage + BreadcrumbList + SoftwareApplication | 符合 | 无偏差 |
| TDD 开发顺序 | 测试先于实现 | 无偏差 |
| 13 个页面集成 | 全部完成 | 无偏差 |

---

## 架构与代码质量评估

**优点**:
1. 文件拆分合理，每个文件职责单一（60-1885 行）
2. `buildXxxSchema` 纯函数与 `useXxxSeoJson` composable 分离，便于测试
3. barrel re-export 模式有效保持了向后兼容
4. `MaybeRefOrGetter<T>` 类型的使用允许灵活传入 ref 或 getter
5. 所有 composable 统一使用 `__dangerouslyDisableSanitizersByTagID` 模式

**可改进之处**:
1. 应将 barrel 文件移出 auto-import 目录以避免重复警告
2. `SchemaRoot` 类型使用了 `Record<string, unknown>` 的宽泛类型，可考虑定义更精确的 schema 类型

---

## 总结

| 严重性 | 数量 | 必须修复 |
|--------|------|---------|
| CRITICAL | 1 | 是 |
| HIGH | 1 | 是 |
| MEDIUM | 2 | 建议修复 |
| LOW | 5 | 可选修复 |

**建议**: 在合并前必须修复 CRITICAL 问题 #1（Spoke breadcrumb hub title 错误）和 HIGH 问题 #2（`isPartof` 拼写错误）。MEDIUM 问题 #4（重复警告）和 #3（测试覆盖）建议一并修复。
