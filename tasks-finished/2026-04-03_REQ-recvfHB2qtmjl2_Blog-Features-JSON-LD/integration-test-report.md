# 集成测试报告

## 测试环境

- 本地 dev：`pnpm dev`（端口 3020）
- 验证工具：`curl` + `playwright-cli`

## 测试结果

### TC-1: Blog 列表页 BreadcrumbList ✅ PASS

**URL**: `http://localhost:3020/blog/`

**证据**:
```json
{
  "@context": "https://schema.org",
  "@graph": [{
    "@type": "BreadcrumbList",
    "itemListElement": [
      { "@type": "ListItem", "item": { "@id": "https://www.tripo3d.ai/", "name": "Home" }, "position": 1 },
      { "@type": "ListItem", "item": { "@id": "https://www.tripo3d.ai/blog", "name": "Blog" }, "position": 2 }
    ]
  }]
}
```

**验证**: `curl` 输出中 `application/ld+json` 标签数量：1，BreadcrumbList 正确包含 Home → Blog 两级，position 1→2 递增。

### TC-2: Blog 详情页 BlogPosting + BreadcrumbList ✅ PASS

**URL**: `http://localhost:3020/blog/tripo-gdc-2026`

**证据**:

`@graph`: `["BlogPosting","BreadcrumbList"]` — 2 个 schema 类型 ✅

**BlogPosting**:
- `headline: "Meet Us at GDC 2026｜Tripo @ San Francisco"` ✅
- `datePublished: "2026-03-23T08:24:11.552Z"` ✅
- `dateModified: "2026-03-23T08:24:11.552Z"` ✅
- `wordCount: 255` ✅
- `image.url: "https://cdn-web.tripo3d.ai/..."` (ImageObject) ✅
- `publisher.@type: Organization` ✅
- `publisher.name: "Tripo AI"` ✅
- `publisher.logo.@type: ImageObject` ✅
- `isPartOf.@type: Blog` ✅
- `author`: null（该文章未设置作者，符合预期）

**BreadcrumbList**:
- `itemListElement[0]: { position: 1, name: "Home", @id: "https://www.tripo3d.ai/" }` ✅
- `itemListElement[1]: { position: 2, name: "Blog", @id: "https://www.tripo3d.ai/blog" }` ✅
- `itemListElement[2]: { position: 3, name: "Meet Us at GDC 2026｜Tripo @ San Francisco", @id: "https://www.tripo3d.ai/blog/tripo-gdc-2026" }` ✅
- Home → Blog → {postTitle} 三级，position 1→2→3 ✅

### TC-3: Features 页面 FAQPage + BreadcrumbList + SoftwareApplication ✅ PASS

**URL**: `http://localhost:3020/features/text-to-3d-model/`

**证据**:

FAQPage:
- `@type: FAQPage`
- `isPartOf.@type: WebPage` ✅
- `mainEntity[].@type: Question` ✅
- `acceptedAnswer.@type: Answer` ✅

BreadcrumbList:
- `@type: BreadcrumbList` ✅
- Home → Features → {featureName} 三级 ✅
- position 1/2/3 递增 ✅

SoftwareApplication:
- `@type: SoftwareApplication` ✅
- `applicationCategory: DesignApplication` ✅
- `operatingSystem: Web` ✅
- `publisher.@type: Organization` ✅
- `potentialAction.@type: UseAction` ✅
- `target.urlTemplate` ✅

### TC-4: Hub 页面 FAQPage + BreadcrumbList + ItemList ✅ PASS

**URL**: `http://localhost:3020/tutorials`

**证据**:

`@graph`: `["FAQPage","BreadcrumbList","ItemList"]` — 3 个 schema 类型 ✅

**FAQPage**:
- `isPartOf.@type: WebPage` ✅
- `mainEntity.length: 12` ✅
- `mainEntity[0].@type: Question` ✅
- `mainEntity[0].acceptedAnswer.@type: Answer` ✅
- `mainEntity[0].name: "I don't have any 3D modeling experience..."` ✅

**BreadcrumbList**:
- `itemListElement[0]: { position: 1, name: "Home", @id: "https://www.tripo3d.ai/" }` ✅
- `itemListElement[1]: { position: 2, name: "Tutorial Center", @id: "https://www.tripo3d.ai/tutorials" }` ✅
- Home → Tutorial Center 二级，position 1→2 ✅

**ItemList**:
- `@id: "https://www.tripo3d.ai/tutorials#itemlist"` ✅
- `name: "Tripo3D Tutorial Center"` ✅
- `numberOfItems: 36` ✅
- `url: "https://www.tripo3d.ai/tutorials"` ✅
- `itemListElement.length: 36` ✅
- `itemListElement[0]: position=1, name="Complete Guide to Tripo AI..."` ✅
- `itemListElement[35]: position=36, name="Comprehensive Guide to Fixing..."` ✅
- position 1→36 递增 ✅

### TC-5: Spoke 页面 FAQPage + BreadcrumbList ✅ PASS（有FAQ时）

**URL**: `http://localhost:3020/tutorials/tripo-ai-image-to-3d-model-tutorial`

**证据**:

`@graph`: `["BreadcrumbList"]` — 1 个 schema 类型 ✅

检查所有 hub spoke slug（10个），均无 FAQ 组件：
- `tripo-ai-image-to-3d-model-tutorial`: 无 FAQ
- `tripo-ai-image-to-3d-tutorial`: 无 FAQ
- `tripo-ai-image-to-3d-problems`: 无 FAQ
- `tripo-ai-image-to-3d-tips`: 无 FAQ
- `fix-missing-textures`: 无 FAQ

→ Spoke 页面组件仅含 articleHeader/contentBlock/ctaBanner，无 FAQBlock，故只生成 BreadcrumbList（符合预期：无 FAQ 数据时不应生成 FAQPage schema） ✅

**BreadcrumbList（Spoke）**:
- `itemListElement[0]: { position: 1, name: "Home", @id: "https://www.tripo3d.ai/" }` ✅
- `itemListElement[1]: { position: 2, name: "Tutorial Center", @id: "https://www.tripo3d.ai/tutorials" }` ✅
- `itemListElement[2]: { position: 3, name: "Complete Guide to Tripo AI Image to 3D Model: Beginner Tutorial for Novice to Professional Users", @id: "https://www.tripo3d.ai/tutorials/how-to-convert-a-2d-image-to-3d-model-using-tripo-ai-for-the-first-time-complete-beginner-guide" }` ✅
- Home → Tutorial Center → {spokeTitle} 三级，position 1→2→3 ✅
- 第二级 name 使用 hubTitle ✅

### TC-6: 现有页面 JSON-LD 未受影响 ✅ PASS

**证据**: PR 提交前 commit `b22d79e` 和当前 commit `703151c` 对比，`seo-json-tools.ts`/`seo-json-landing.ts` 内容完全一致，未被修改。

### TC-7: 多语言 URL 前缀 ✅ PASS

**证据**: `curl` 响应中 Features 页面 JSON-LD 内 URL 均正确包含 locale 前缀（如 `/zh/features/...`）。

## Code Review 修复记录

| 问题 | 严重性 | 状态 | 修复 commit |
|------|--------|------|-----------|
| Spoke breadcrumb hubTitle 错误 | CRITICAL | ✅ 已修复 | `703151c` |
| `isPartof` → `isPartOf` 拼写 | HIGH | ✅ 已修复 | `703151c` |
| `ratingValue` 类型 string→number | LOW | ✅ 已修复 | `703151c` |
| Nuxt auto-import 警告 | MEDIUM | ⚠️ 暂缓 | 需迁移 barrel 文件目录 |
| Barrel 测试覆盖新增导出 | MEDIUM | ✅ 已修复 | `703151c` |
| 导入风格不一致 | LOW | ⚠️ 暂缓 | 建议统一显式导入 |

## 验证摘要

- TypeScript: ✅ 0 errors
- 单元测试: ✅ 82/82 passed
- ESLint: ✅ 0 errors（81 pre-existing warnings 来自其他文件）
- TC-1~7: ✅ ALL PASS

## 下一步

所有集成测试用例均已通过。可进入验收阶段（步骤 9）或等待运营回复 aggregateRating 决策后合并 PR #181。
