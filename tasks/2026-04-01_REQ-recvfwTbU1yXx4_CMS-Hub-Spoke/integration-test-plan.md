# Hub-Spoke 前端 CMS 接入 — 集成测试计划

> 需求ID: recvfwTbU1yXx4 | PR: #188 (fe-tripo-homepage)
> 测试日期: 2026-04-14

## 测试环境

| 项目 | 配置 |
|------|------|
| CMS | 本地 `http://localhost:3000`（tripo-cms main 分支） |
| 前端 | 本地 `http://localhost:3020`（worktree 分支） |
| 数据库 | payload-tripo-cms-dev |
| Feature Flag | `hubSpokeLegacy: false`（CMS app-config） |
| 环境变量 | `NUXT_CMS_INTERNAL_URL=http://localhost:3000` |

## 前置条件

- [ ] CMS dev server 启动成功 (port 3000)
- [ ] 前端 dev server 启动成功 (port 3020)
- [ ] 通过 sync API 推送至少 1 个 Hub + 1 个 Spoke 并发布
- [ ] app-config.featureFlags.hubSpokeLegacy = false

## 测试场景

### Scene 1: Hub 页面渲染

| ID | 操作 | 预期结果 | 验证方式 |
|----|------|---------|---------|
| 1.1 | 访问 `http://localhost:3020/{hubSlug}` | 页面正确渲染，标题可见 | DOM snapshot |
| 1.2 | 检查组件列表渲染 | 各组件类型正确渲染（hero/faq/ctaBanner 等） | DOM 检查 |
| 1.3 | 检查 API 请求 | `/api/crescendia/hub/{slug}` 返回 CMS 数据 | Network |

### Scene 2: Spoke 页面渲染

| ID | 操作 | 预期结果 | 验证方式 |
|----|------|---------|---------|
| 2.1 | 访问 `http://localhost:3020/{hubSlug}/{spokeSlug}` | 页面正确渲染 | DOM snapshot |
| 2.2 | 检查面包屑导航 | Hub → Spoke 路径正确 | DOM 检查 |
| 2.3 | 检查前后翻页导航 | previousSpoke/nextSpoke 链接正确 | DOM 检查 |

### Scene 3: 图片响应式渲染

| ID | 操作 | 预期结果 | 验证方式 |
|----|------|---------|---------|
| 3.1 | 检查含图片组件的 HTML | `<picture>` + `<source>` 结构 | DOM 检查 |
| 3.2 | source 的 media 属性 | 600px / 900px / 1400px 断点 | DOM 检查 |
| 3.3 | img.src（fallback） | CMS Media 原图 URL | DOM 检查 |

### Scene 4: SEO 验证

| ID | 操作 | 预期结果 | 验证方式 |
|----|------|---------|---------|
| 4.1 | 检查 `<title>` 标签 | 来自 CMS meta.title | DOM 检查 |
| 4.2 | 检查 `<meta name="description">` | 来自 CMS meta.description | DOM 检查 |
| 4.3 | 检查 `<meta property="og:image">` | 正确的图片 URL 字符串 | DOM 检查 |

### Scene 5: Sitemap

| ID | 操作 | 预期结果 | 验证方式 |
|----|------|---------|---------|
| 5.1 | curl `/sitemap-dynamic.xml` | 包含 `hub-spoke.xml` 条目 | curl |
| 5.2 | curl `/sitemaps/hub-spoke.xml` | 包含已发布 Hub/Spoke URL | curl |

### Scene 6: 404 场景

| ID | 操作 | 预期结果 | 验证方式 |
|----|------|---------|---------|
| 6.1 | 访问不存在的 slug | 404 错误页 | HTTP status |
| 6.2 | 访问未发布 (draft) 的页面 | 404 错误页 | HTTP status |

### Scene 7: Feature Flag 切换

| ID | 操作 | 预期结果 | 验证方式 |
|----|------|---------|---------|
| 7.1 | `hubSpokeLegacy: false` 访问页面 | 走 CMS 数据 | 页面渲染正确 |
| 7.2 | `hubSpokeLegacy: true` 访问页面 | 走 Crescendia（如可用） | 数据源切换 |

## 降级条件

| 场景 | 降级条件 | 补测时机 |
|------|---------|---------|
| Scene 7.2 | Crescendia API 不可用 | ⚠️ DEFERRED → staging |
| Scene 2.3 | 测试数据中无 previousSpoke/nextSpoke | ⚠️ DEFERRED → 全量推送后 |

## 执行顺序

1. 启动 CMS + 前端
2. 推送测试数据 + 发布
3. Scene 1 → Scene 2 → Scene 3 → Scene 4 → Scene 5 → Scene 6 → Scene 7
