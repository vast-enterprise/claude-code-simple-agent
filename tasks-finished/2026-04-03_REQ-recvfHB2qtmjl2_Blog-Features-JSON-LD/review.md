# 需求评审：Blog & Features 页面 JSON-LD 结构化数据

## 需求来源

| 项目 | 值 |
|------|-----|
| 需求ID | recvfHB2qtmjl2 |
| 需求描述 | 为 Homepage 的 Blog Index、Blog 详情、Features、Hub-Spoke 页面添加 JSON-LD 结构化数据 |
| 需求Owner | 用户 |
| PRD 文档 | https://a9ihi0un9c.feishu.cn/wiki/Ru54wNpqgidn6SkOn4LcuduEnzb |
| 目标仓库 | fe-tripo-homepage |

## 需求范围

### 核心功能

为 5 类页面添加共 11 个 JSON-LD schema，提升 Google 富媒体搜索结果展示：

| 页面 | Schema 类型 | 数据来源 |
|------|------------|---------|
| Blog 列表页 `/blog` | BreadcrumbList | 固定：Home → Blog |
| Blog 详情页 `/blog/[slug]` | BlogPosting | post 字段：title, description, date, heroImage, keywords, wordCount |
| Blog 详情页 `/blog/[slug]` | BreadcrumbList | 固定：Home → Blog → {title} |
| Features 页 `/features/{name}` | FAQPage | `featureData.faq.items` |
| Features 页 `/features/{name}` | BreadcrumbList | 固定：Home → Features → {name} |
| Features 页 `/features/{name}` | SoftwareApplication | `featureData.hero` + `featureData.seo` |
| Hub 页 `/{hub}` | FAQPage | `components.find(type='faq')` |
| Hub 页 `/{hub}` | BreadcrumbList | 固定：Home → {hubName} |
| Hub 页 `/{hub}` | ItemList | spoke 列表（从 CMS 数据获取） |
| Spoke 页 `/{hub}/{spoke}` | FAQPage | `components.find(type='faq')` |
| Spoke 页 `/{hub}/{spoke}` | BreadcrumbList | 固定：Home → {hubName} → {spokeName} |

### 附带重构

现有 `seo-json.ts` 已 2045 行，需拆分为模块化文件：

| 文件 | 内容 | 说明 |
|------|------|------|
| `seo-json-shared.ts` | SchemaRoot 类型、buildLocalizedUrl、buildLogoObject、buildFaqSchema | 公共工具函数 |
| `seo-json-tools.ts` | Converter + Viewer 全部 schema | 原文件主体迁移 |
| `seo-json-landing.ts` | useLandingPageSeoJson | 首页 schema |
| `seo-json-blog.ts` | **新增** useBlogPostingSeoJson、useBlogIndexSeoJson | Blog JSON-LD |
| `seo-json-features.ts` | **新增** useFeaturesSeoJson | Features JSON-LD |
| `seo-json-hub-spoke.ts` | **新增** useHubSpokeSeoJson | Hub-Spoke JSON-LD |

### 边界条件

- Blog 详情页的 `aggregateRating` 使用 slug 哈希生成稳定伪随机值（ratingValue 4.2~4.8，ratingCount 10~100）
- Blog 详情页的 `wordCount` 需从内容中估算
- Hub-Spoke 的 FAQ 数据在 `components[]` 数组中，需从中提取 `type='faq'` 组件
- Hub 页的 `ItemList` 需要 spoke 列表数据，需确认数据来源
- 所有 JSON-LD 需支持多语言（通过 `buildLocalizedUrl` 构建 URL）

### 不包含

- 不修改现有 Viewer/Converter/Landing 页面的 JSON-LD
- 不修改 `useSEO()` meta 标签逻辑
- 不新增 sitemap 相关功能

## 验收标准

1. Blog 列表页包含 BreadcrumbList JSON-LD
2. Blog 详情页包含 BlogPosting + BreadcrumbList JSON-LD
3. 9 个 Features 页面包含 FAQPage + BreadcrumbList + SoftwareApplication JSON-LD
4. Hub 页面包含 FAQPage + BreadcrumbList + ItemList JSON-LD
5. Spoke 页面包含 FAQPage + BreadcrumbList JSON-LD
6. 所有 JSON-LD 通过 Google 富媒体结果测试验证
7. `seo-json.ts` 已拆分为模块化文件，原有功能不受影响
8. TypeScript 类型检查通过（`pnpm typecheck`）
9. ESLint 检查通过（`pnpm lint`）

## 技术约束

- 框架：Nuxt 4 + Vue 3 Composition API
- JSON-LD 注入方式：`useHead()` + `computed` + `__dangerouslyDisableSanitizersByTagID`（与现有模式一致）
- 字符串中不使用 `\'`，改用 Unicode `\u2019`（已有修复先例）
- 所有 composable 遵循现有模式：纯函数构建 schema → computed 包裹 → useHead 注入

## 问题与风险

| 问题 | 风险等级 | 应对 |
|------|---------|------|
| seo-json.ts 拆分可能影响现有页面 | 中 | 拆分后跑 typecheck + lint 验证，确保导入路径正确 |
| Hub 页 ItemList 需要 spoke 列表数据 | 低 | Hub-Spoke 数据已包含 components 和 relatedHubs，需确认 spoke 列表获取方式 |
| aggregateRating 可能被 Google 质疑 | 低 | 使用 slug 哈希保证稳定性，值域合理 |
| Blog 详情页有 3 种内容类型（legacy/lexical/mdc） | 低 | wordCount 估算需兼容三种类型 |

## 评审结论

需求明确，技术方案可行。核心工作量在于：
1. 拆分 seo-json.ts（重构，不改功能）
2. 新增 3 个 JSON-LD composable 文件
3. 在 5 类页面中调用对应 composable

预估工作量：中等（涉及 ~10 个文件修改/新增）
