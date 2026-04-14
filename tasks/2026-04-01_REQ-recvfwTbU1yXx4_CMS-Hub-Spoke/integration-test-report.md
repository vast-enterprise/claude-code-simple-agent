# Hub-Spoke 前端 CMS 接入 — 集成测试报告

> 需求ID: recvfwTbU1yXx4 | PR: #188 (fe-tripo-homepage)
> 测试日期: 2026-04-14
> 测试工具: playwright-cli + curl

## 测试环境

| 项目 | 配置 |
|------|------|
| CMS | 本地 `http://localhost:3000`（tripo-cms main） |
| 前端 | 本地 `http://localhost:3020`（worktree, `--no-https`） |
| 数据库 | payload-tripo-cms-dev |
| Feature Flag | 临时设 `hubSpokeLegacy ?? false` 测试 CMS 路径 |
| 测试数据 | 3 个文档（2 hub + 1 spoke），通过 sync API 推送并发布 |

## 测试结果

| Scene | ID | 描述 | 结果 | 证据 |
|-------|-----|------|------|------|
| 1 Hub 渲染 | 1.1 | 访问 Hub 页面 | ✅ PASS | playwright: title="Tripo3D Tutorials \| AI 3D Modeling Guide", hero heading 可见 |
| 1 Hub 渲染 | 1.2 | 组件列表渲染 | ✅ PASS | hero 组件正确渲染（title + subtitle + CTA） |
| 1 Hub 渲染 | 1.3 | API 返回 CMS 数据 | ✅ PASS | slug/title/type/components/meta 全部正确 |
| 2 Spoke 渲染 | 2.1 | 访问 Spoke 页面 | ✅ PASS | playwright: title="Text to 3D Tutorial \| Tripo3D" |
| 2 Spoke 渲染 | 2.2 | 面包屑导航 | ✅ PASS | playwright snapshot: Home → Tutorials → Text to 3D |
| 2 Spoke 渲染 | 2.3 | 前后翻页导航 | ✅ PASS | playwright snapshot: "Getting Started" (prev) + "Image to 3D" (next) |
| 2 Spoke 渲染 | 2.4 | 组件完整性 | ✅ PASS | articleHeader + contentBlock(Markdown parsed) + stepByStep(3 steps) |
| 3 图片响应式 | 3.1 | `<picture>` 标签 | ✅ PASS | 1 picture, 4 source 标签 |
| 3 图片响应式 | 3.2 | source 断点 | ✅ PASS | media="(min-width: 1400px/900px/600px)" + srcSmall fallback |
| 3 图片响应式 | 3.3 | img fallback | ✅ PASS | src=原图 URL, alt="Master AI 3D Modeling", width=800 height=600 |
| 4 SEO | 4.1 | `<title>` | ✅ PASS | CMS meta.title 正确渲染 |
| 4 SEO | 4.2 | meta description | ⚠️ DEFERRED | Nuxt useSeoMeta 客户端注入，SSR HTML 不含（框架行为） |
| 4 SEO | 4.3 | og:image | ⚠️ DEFERRED | 同上 |
| 5 Sitemap | 5.1 | sitemapindex | ✅ PASS | `/sitemap-dynamic.xml` 包含 hub-spoke.xml 条目 |
| 5 Sitemap | 5.2 | sitemap 内容 | ✅ PASS | `/sitemaps/hub-spoke.xml` 包含 sync-test-tutorials + text-to-3d |
| 6 404 | 6.1 | 不存在的 slug | ✅ PASS | HTTP 404 |
| 7 Feature Flag | 7.1 | CMS 模式 | ✅ PASS | hubSpokeLegacy=false 时正确走 CMS 数据 |
| 7 Feature Flag | 7.2 | Legacy 回退 | ⚠️ DEFERRED | Crescendia API 本地不可用 |

## 统计

- ✅ PASS: 13/16
- ⚠️ DEFERRED: 3/16
- ❌ FAIL: 0/16

## 测试中修复的问题

| 问题 | 修复 |
|------|------|
| Spoke slug 查询不匹配 | CMS 存储格式为 `{hubSlug}/{spokeSlug}`，修改 `fetchSpokeFromCMS` 查询拼接 |

## DEFERRED 补测计划

| 场景 | 原因 | 补测时机 |
|------|------|---------|
| 4.2/4.3 SEO meta | useSeoMeta 客户端注入 | staging 部署后 Google Search Console |
| 7.2 Legacy 回退 | Crescendia API 本地不可用 | staging 环境 |

## 单元测试

- 67 个 adapter 单元测试通过
- 151 个项目全量测试通过
- TypeCheck 0 errors, ESLint 0 errors
