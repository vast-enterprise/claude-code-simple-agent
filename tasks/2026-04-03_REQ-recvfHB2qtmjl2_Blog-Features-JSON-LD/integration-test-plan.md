# 集成测试计划：Blog & Features JSON-LD 结构化数据

## 测试环境

- 本地 dev 环境：`pnpm dev`
- 浏览器：Chrome DevTools 检查 `<script type="application/ld+json">`
- 验证工具：Google 富媒体结果测试 https://search.google.com/test/rich-results

## 测试场景

### TC-1: Blog 列表页 BreadcrumbList

- **URL**: `/blog`
- **预期**: 页面 HTML 中包含 `<script type="application/ld+json">` 标签，内容为 BreadcrumbList schema，包含 Home → Blog 两级
- **验证方式**: 查看页面源码中的 JSON-LD 标签

### TC-2: Blog 详情页 BlogPosting + BreadcrumbList

- **URL**: `/blog/{any-slug}`（需要 CMS 模式开启，或使用 legacy 模式的文章）
- **预期**: 页面 HTML 中包含 JSON-LD，@graph 包含 BlogPosting 和 BreadcrumbList
- **验证点**:
  - BlogPosting.headline 与页面标题一致
  - BlogPosting.datePublished 存在
  - BlogPosting.aggregateRating.ratingValue 在 4.2~4.8 范围
  - BreadcrumbList 包含 Home → Blog → {title} 三级
- **降级条件**: 如果 CMS 服务不可用，标记 ⚠️ DEFERRED

### TC-3: Features 页面 FAQPage + BreadcrumbList + SoftwareApplication

- **URL**: `/features/text-to-3d-model`
- **预期**: JSON-LD @graph 包含 FAQPage、BreadcrumbList、SoftwareApplication
- **验证点**:
  - FAQPage.mainEntity 数组非空
  - BreadcrumbList 包含 Home → Features → {name} 三级
  - SoftwareApplication.applicationCategory = "DesignApplication"
  - SoftwareApplication.potentialAction.target.urlTemplate 指向 /app

### TC-4: Hub 页面 FAQPage + BreadcrumbList + ItemList

- **URL**: `/{hub-slug}`（需要 Crescendia API 可用）
- **预期**: JSON-LD @graph 包含 FAQPage、BreadcrumbList、ItemList
- **验证点**:
  - ItemList.itemListElement 数组非空
  - ItemList.itemListElement[0].position = 1
- **降级条件**: 如果 Crescendia API 不可用，标记 ⚠️ DEFERRED

### TC-5: Spoke 页面 FAQPage + BreadcrumbList

- **URL**: `/{hub-slug}/{spoke-slug}`（需要 Crescendia API 可用）
- **预期**: JSON-LD @graph 包含 FAQPage、BreadcrumbList（无 ItemList）
- **验证点**:
  - BreadcrumbList 包含 Home → {hubTitle} → {spokeTitle} 三级
  - hubTitle 不等于 spokeTitle（CRITICAL 修复验证）
- **降级条件**: 如果 Crescendia API 不可用，标记 ⚠️ DEFERRED

### TC-6: 现有页面 JSON-LD 未受影响

- **URL**: `/` (Landing), `/tools/viewer/fbx` (Viewer), `/tools/converter` (Converter)
- **预期**: 现有 JSON-LD 输出与修改前一致
- **验证方式**: 对比修改前后的 JSON-LD 输出

### TC-7: 多语言 URL 前缀

- **URL**: `/zh/features/text-to-3d-model`
- **预期**: JSON-LD 中所有 URL 包含 `/zh/` 前缀
