# 集成测试计划 - Blog 主动推送机制

## 测试环境

- tripo-cms: 本地开发环境 (localhost:3000)，MongoDB 本地实例
- fe-tripo-homepage: 本地开发环境 (localhost:3020)

## 前置条件

- CMS 已启动，MongoDB 已连接
- 存在 `Tripo Team` 用户
- 存在至少一个 category

## 测试场景

### CMS 端 - blog-import endpoint

#### TC-1: 认证失败
- 请求: `POST /api/blog-import`，不带 Authorization
- 预期: 401, `{ success: false, error: "UNAUTHORIZED" }`

#### TC-2: 请求校验 - 缺少 locale
- 请求: `POST /api/blog-import`，body: `{ articles: [...] }`
- 预期: 400, error: `INVALID_LOCALE`

#### TC-3: 请求校验 - 文章数超限
- 请求: 51 篇文章
- 预期: 400, error: `TOO_MANY_ARTICLES`

#### TC-4: 正常创建单篇文章（无图片）
- 请求: 1 篇纯文本 markdown 文章
- 预期: 200, status: `created`, geo-posts 中新增 draft 记录，isCrescendia=true

#### TC-5: 重复推送 - draft 更新
- 请求: 与 TC-4 相同 slug 的文章，修改 markdown
- 预期: 200, status: `updated`

#### TC-6: 含图片的文章
- 请求: markdown 中包含外部图片 URL
- 预期: 图片下载并上传到 media，markdown 中替换为 `<media-image>` 标签

### 前端 - media-image 组件

#### TC-7: media-image 组件渲染
- 访问含 `<media-image>` 标签的 geo-post 页面
- 预期: `<picture>` 元素正确渲染，`<source>` 断点正确

#### TC-8: SSR 无 hydration 错误
- 查看浏览器控制台
- 预期: 无 hydration mismatch 警告

## 测试方式

- TC-1 ~ TC-6: curl 命令直接调用 API
- TC-7 ~ TC-8: 浏览器访问页面验证（需要 TC-4 创建的文章发布后才能验证）

## 备注

TC-7/TC-8 依赖文章发布，当前文章为 draft 状态，前端集成测试需在验收阶段手动发布后验证。本轮重点验证 CMS API 端。
