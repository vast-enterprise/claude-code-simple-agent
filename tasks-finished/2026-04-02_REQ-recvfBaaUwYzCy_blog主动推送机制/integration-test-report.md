# 集成测试报告 - Blog 主动推送机制

## 测试环境

- tripo-cms worktree: `feature/REQ-recvfBaaUwYzCy-blog-import`
- CMS: localhost:3000 (Next.js 15 + Payload CMS 3.x + MongoDB)
- vitest v4.1.2

## 集成测试结果（API 实际调用）

| 场景 | 方法 | 状态 | 响应 |
|------|------|------|------|
| TC-1: 无认证 | curl POST /api/blog-import | ✅ PASS | 401 `{"success":false,"error":"UNAUTHORIZED"}` |
| TC-2: 缺少 locale | curl POST + JWT | ✅ PASS | 400 `{"error":"INVALID_LOCALE"}` |
| TC-3: 51 篇超限 | python urllib + JWT | ✅ PASS | 400 `{"error":"TOO_MANY_ARTICLES","message":"...当前 51 篇"}` |
| TC-4: 创建单篇文章 | curl POST + JWT | ✅ PASS | 200 `{"processed":1,"results":[{"status":"created","id":"69ce6e27..."}]}` |
| TC-5: 重复推送更新 | curl POST + JWT (同 slug) | ✅ PASS | 200 `{"processed":1,"results":[{"status":"updated","id":"69ce6e27..."}]}` |
| TC-6: 含图片文章 | curl POST + JWT | ⚠️ DEFERRED | 文章创建成功，但图片下载失败（CMS 服务器无外网代理），保留原始 markdown |
| TC-7: 前端渲染 | Playwright | ✅ PASS | 文章标题、段落、列表完整渲染，Console 0 errors |
| TC-8: SSR hydration | Playwright | ✅ PASS | 无 hydration mismatch，仅 NuxtLink 配置警告（非阻塞） |

## 集成测试发现并修复的 Bug

### BUG-1: req.body 未解析（CRITICAL）
- 现象: 所有带 body 的请求返回 `INVALID_LOCALE`，body 为空对象
- 根因: Payload CMS 3.x 自定义 endpoint 中 `req.body` 不是已解析的 JSON，需要用 `await req.json()`
- 修复: `index.ts` 改为 `const body = await req.json().catch(() => ({}))`
- 提交: 8d73149

### BUG-2: localized 字段写法错误（CRITICAL）
- 现象: TC-4 返回 `Cast to string failed for value "{ en: '...' }" (type Object)`
- 根因: Payload 3.x Local API 的 localized 字段应通过 `locale` 参数 + 直接传字符串，而非 `{ [locale]: value }` 对象
- 修复: `process-article.ts` 的 create/update 调用添加 `locale` 参数，data 中直接传字符串
- 提交: 8d73149

## DEFERRED 场景说明

| 场景 | 降级原因 | 补测计划 |
|------|---------|---------|
| TC-6 图片下载 | CMS 服务器无外网代理，fetch 外部图片超时 | 验收阶段配置代理后重测，或使用内网图片 URL |

## TC-7/TC-8 测试详情（2026-04-03 补测）

### 测试环境

| 组件 | 配置 |
|------|------|
| CMS | localhost:3000 (tripo-cms worktree) |
| 前端 | localhost:3020 (fe-tripo-homepage worktree) |
| 环境变量 | NUXT_CMS_INTERNAL_URL=http://localhost:3000 |
| Feature Flag | blogLegacy=false (app-config) |
| 测试文章 | MongoDB 直接插入 geo-posts collection |

### TC-7: media-image 组件渲染

**测试步骤**：
1. 在 MongoDB (tripo-cms) 中创建包含 `<media-image>` 标签的测试文章
2. 设置 srcSmall/medium/large/xlarge 四个尺寸
3. Playwright 打开 http://localhost:3020/zh/blog/media-image-test
4. 检查 DOM 结构

**测试结果**：
| 检查项 | 状态 |
|--------|------|
| `<figure class="media-image">` | ✅ 存在 |
| `<picture>` 元素 | ✅ 存在 |
| `<source media="(min-width: 1400px)">` | ✅ xlarge 断点正确 |
| `<source media="(min-width: 900px)">` | ✅ large 断点正确 |
| `<source media="(min-width: 600px)">` | ✅ medium 断点正确 |
| `<source>` 无 media (small 默认) | ✅ 正确 |
| `<img>` lazy loading | ✅ 正确 |
| `<figcaption>` 渲染 caption | ✅ PASS |

### TC-8: SSR Hydration

**测试结果**：
| 检查项 | 状态 |
|--------|------|
| Console errors | 0 |
| Hydration mismatch | ✅ 无 |
| 警告 | Firebase/NuxtLink 配置警告（非阻塞） |

### 测试证据

- Playwright Snapshot: `.playwright-cli/page-2026-04-03T02-52-28-559Z.yml`
- Console Log: `.playwright-cli/console-2026-04-03T02-52-26-381Z.log`

## 单元测试结果

| 测试文件 | 通过 | 失败 | 总计 |
|---------|------|------|------|
| process-images.spec.ts | 6 | 0 | 6 |
| validate.spec.ts | 13 | 0 | 13 |
| **合计** | **19** | **0** | **19** |

## Code Review 修复汇总

| 仓库 | 问题 | 级别 | 状态 |
|------|------|------|------|
| fe-tripo-homepage | mdxToAST 白名单缺失 MediaImage | CRITICAL | ✅ 已修复 |
| fe-tripo-homepage | figcaption 颜色对比度 | MEDIUM | ✅ 已修复 |
| fe-tripo-homepage | unused props 变量 | MEDIUM | ✅ 已修复 |
| tripo-cms | 重复图片 URL 替换 | CRITICAL | ✅ 已修复 |
| tripo-cms | 缓存重置函数缺失 | CRITICAL | ✅ 已修复 |
| tripo-cms | 角色权限检查 | HIGH | ✅ 已修复 |
| tripo-cms | 图片大小限制 | HIGH | ✅ 已修复 |
| tripo-cms | publishedAt 字段 | HIGH | ✅ 已修复 |
| tripo-cms | req.json() body 解析 | CRITICAL | ✅ 已修复（集成测试发现） |
| tripo-cms | locale 参数写法 | CRITICAL | ✅ 已修复（集成测试发现） |

## 结论

5/6 API 测试场景通过，1 个因网络环境降级。集成测试发现并修复了 2 个 CRITICAL bug（body 解析 + locale 写法），这两个 bug 在单元测试中无法发现（mock 绕过了真实 Payload API）。
