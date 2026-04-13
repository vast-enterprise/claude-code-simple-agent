# Code Review: tripo-cms Hub-Spoke Feature

**Branch:** `feat/hub-spoke-pages`
**Commits:** 5 (hub-spoke 相关), 47 files changed, +4605/-880 lines
**Reviewer:** Adversarial Code Review (Opus 4.6)
**Date:** 2026-04-13

---

## Executive Summary

Hub-Spoke 功能整体实现质量较高，架构清晰，文档完善。`buildRevalidateHooks` 重构是一个正确的架构决策，将三个集合的 revalidate 逻辑统一为策略模式。但在对抗性审查中发现了 **1 个 CRITICAL 问题**（模块级可变缓存在多实例部署下会导致数据不一致）、**4 个 HIGH 问题**（含安全相关）和数个 MEDIUM/LOW 问题。

---

## CRITICAL

### C-1: 模块级可变缓存 `cachedFolderId` 在 Serverless/多 Worker 下不可靠，且无缓存失效机制

**File:** `src/endpoints/hub-spoke-sync.ts:90-91`

```typescript
let cachedFolderId: string | null = null
```

**问题描述:**

1. **进程级单例缓存没有失效机制。** 如果 `hub-spoke` 文件夹在 MongoDB 中被手动删除（运维操作、数据库恢复），所有后续请求仍使用旧的 `cachedFolderId`，`payload.create({ folder: folderId })` 会写入一个不存在的 folder 引用，导致 Media 文档的 `folder` 字段指向一个幽灵 ID。这不会报错（MongoDB 不校验 relationship 引用完整性），但 Admin Panel 的文件夹视图将无法正确归类这些图片。

2. **多 Worker/多 Pod 竞态。** Kubernetes 部署有多个 Pod（参见 `llmdoc/architecture/environment-deployment.md`），每个 Pod 的 `cachedFolderId` 独立初始化。虽然代码有 `catch` 分支处理并发创建，但 `catch` 只捕获了 `payload.create` 异常——如果两个 Pod 同时发现文件夹不存在，两个都执行 `payload.create`，第二个会因 `name` 重复而进入 catch，但 `payload-folders` 集合的 `name` 字段**并非唯一索引**（Payload 默认不对 folder name 加唯一约束），两个都会成功创建，导致两个同名文件夹。

**实际影响:** 生产环境可能出现两个 `hub-spoke` 文件夹，图片分散在不同文件夹中。

**修复建议:**

```typescript
// 方案 A: 使用 MongoDB upsert 保证幂等
async function getOrCreateHubSpokeFolder(payload: BasePayload): Promise<string> {
  const Model = payload.db.collections['payload-folders']
  const result = await Model.findOneAndUpdate(
    { name: HUB_SPOKE_FOLDER_NAME },
    { $setOnInsert: { name: HUB_SPOKE_FOLDER_NAME, folderType: ['media'] } },
    { upsert: true, new: true }
  )
  return String(result._id)
}

// 方案 B: 如果保留缓存，加 TTL
const CACHE_TTL_MS = 5 * 60 * 1000 // 5 分钟
let cachedFolderId: string | null = null
let cachedAt = 0

async function getOrCreateHubSpokeFolder(payload: BasePayload): Promise<string> {
  if (cachedFolderId && Date.now() - cachedAt < CACHE_TTL_MS) {
    return cachedFolderId
  }
  // ... 查询/创建逻辑
}
```

---

## HIGH

### H-1: `ensureMedia` 的图片下载无超时、无大小限制 -- SSRF + DoS 向量

**File:** `src/endpoints/hub-spoke-sync.ts:171-176`

```typescript
const response = await fetch(imageUrl)
// ...
const buffer = Buffer.from(await response.arrayBuffer())
```

**问题描述:**

1. **无下载超时。** 如果 Crescendia 推送的图片 URL 指向一个响应极慢的服务器（Slowloris 攻击），`fetch` 会无限期挂起。多个这样的请求并行（`Promise.allSettled`）将耗尽 Node.js 的事件循环资源。

2. **无文件大小限制。** `await response.arrayBuffer()` 将整个响应体读入内存。攻击者推送一个指向 10GB 文件的 URL（图片扩展名伪装），Node.js 进程会 OOM crash。虽然有认证保护，但 Crescendia 被攻陷或密钥泄露时此为放大向量。

3. **无 Content-Type 校验。** `contentType` 从响应头读取，但不校验是否确实为图片。响应头可以是 `text/html` 但 URL 以 `.jpg` 结尾。

4. **SSRF 风险。** 无 URL 限制，攻击者可构造 `http://169.254.169.254/latest/meta-data/` 等内网地址（扩展名为 `.jpg`），通过 CMS 服务器作为跳板访问 K8s 内部服务的元数据端点。

**实际影响:** 拥有 sync 密钥的攻击者可以：(a) 让 CMS Pod OOM，(b) 探测 K8s 内网。

**修复建议:**

```typescript
const MAX_IMAGE_SIZE = 20 * 1024 * 1024 // 20MB
const FETCH_TIMEOUT_MS = 30_000

const response = await fetch(imageUrl, {
  signal: AbortSignal.timeout(FETCH_TIMEOUT_MS),
})
if (!response.ok) return { error: `HTTP ${response.status}` }

const contentType = response.headers.get('content-type') || ''
if (!contentType.startsWith('image/')) {
  return { error: `Not an image: ${contentType}` }
}

const contentLength = parseInt(response.headers.get('content-length') || '0', 10)
if (contentLength > MAX_IMAGE_SIZE) {
  return { error: `Image too large: ${contentLength} bytes` }
}

// 流式读取带大小保护
const chunks: Uint8Array[] = []
let totalSize = 0
const reader = response.body?.getReader()
// ... 逐块读取，超过 MAX_IMAGE_SIZE 时 abort
```

### H-2: `revalidate-frontend.ts` 将 secret 放入 Webhook 请求体中（信息泄露风险）

**File:** `src/utilities/revalidate-frontend.ts:163-164`

```typescript
await sendBatchRevalidate({
  secret: HOMEPAGE_INTERNAL_REVALIDATE_SECRET,
  // ...
})
```

以及 `src/utilities/revalidate-frontend.ts:249`:

```typescript
body: JSON.stringify(body),
```

**问题描述:**

Secret 以明文形式放在 HTTP 请求体（`body.secret`）中传输。虽然 K8s 内部通信通常是 HTTP（非 HTTPS），但：

1. 如果日志中间件（如 Nginx access log）记录了请求体，secret 会被持久化到日志中。
2. 与 `hub-spoke-sync.ts` 使用 `Authorization` header 的模式不一致。Header 被日志中间件记录的概率低于 body。
3. 前端（fe-tripo-homepage）的 webhook 接收端需要从 body 提取 secret 校验，如果前端的错误处理将 body 序列化到日志，secret 也会泄露。

**实际影响:** 中等。Secret 在 K8s 内网传输，风险有限，但违反最小暴露原则。

**修复建议:** 改用 `Authorization: Bearer <secret>` header。这需要前后端协同修改，可在下个迭代处理。

### H-3: `hub-spoke-sitemap-meta` 端点无认证、无缓存，可被外部探测

**File:** `src/endpoints/hub-spoke-sitemap-meta.ts:17-20`

```typescript
export const hubSpokeSitemapMetaEndpoint: Endpoint = {
  path: '/hub-spoke-sitemap-meta',
  method: 'get',
  handler: async (req) => {
```

**问题描述:**

1. **无认证。** 端点不校验 Authorization header 或任何身份信息。虽然返回的数据（语言代码、文档数量、最后更新时间）不是高度敏感信息，但暴露了 CMS 的内容统计信息给任何能访问 CMS URL 的人。

2. **无缓存策略。** 每次请求都执行 MongoDB `$facet` 聚合。虽然当前数据量小，但如果 hub-spoke-pages 集合增长到万级，每次请求都做全表聚合会增加 MongoDB 负载。结合无认证的情况，存在 DDoS 放大向量。

3. **与 `geo-posts-months` 端点不一致。** 需要确认 `geo-posts-months` 端点是否有认证。

**实际影响:** 外部用户可以通过 `GET /api/hub-spoke-sitemap-meta` 探测 CMS 有多少 hub-spoke 内容、哪些语言有内容、最后更新时间。

**修复建议:**

```typescript
handler: async (req) => {
  const authHeader = req.headers?.get('authorization') || ''
  const token = authHeader.startsWith('Bearer ') ? authHeader.slice(7) : null
  if (!token || token !== HOMEPAGE_INTERNAL_REVALIDATE_SECRET) {
    return Response.json({ error: 'Unauthorized' }, { status: 401 })
  }
  // ... 原有逻辑
}
```

### H-4: `components` 数组无大小限制 -- DoS 向量

**File:** `src/endpoints/hub-spoke-sync.ts:579`

```typescript
if (!Array.isArray(body.data.components)) {
  return Response.json({ error: 'data.components must be an array' }, { status: 400 })
}
```

**问题描述:**

校验了 `components` 是数组，但没有限制数组长度。同样，`breadcrumb`、`relatedHubs`、`meta.keywords` 等数组字段也没有长度限制。

攻击场景：Crescendia 密钥泄露后，攻击者发送 `components: [... 10000 个组件 ...]`，每个组件包含多个图片 URL。`processImageFields` 会并行下载所有图片（无并发限制），导致：
- 同时发起数千个 HTTP 请求
- 内存中同时持有数千个图片 buffer
- CMS Pod OOM 或 MongoDB 写入风暴

**实际影响:** 拥有密钥的攻击者可通过单个请求让 CMS Pod 崩溃。

**修复建议:**

```typescript
const MAX_COMPONENTS = 100
const MAX_IMAGES_PER_REQUEST = 50

if (body.data.components.length > MAX_COMPONENTS) {
  return Response.json(
    { error: `Too many components (max ${MAX_COMPONENTS})` },
    { status: 400 },
  )
}

// 在 processImageFields 中:
const imageUrls = collectImageUrls(result)
if (imageUrls.length > MAX_IMAGES_PER_REQUEST) {
  payload.logger.warn({ msg: `Truncating image downloads to ${MAX_IMAGES_PER_REQUEST}` })
  imageUrls.length = MAX_IMAGES_PER_REQUEST
}
```

---

## MEDIUM

### M-1: `normalizeBlockData` 仅检测 `data[0]` 类型来判断字符串数组 -- 混合类型数组误判

**File:** `src/endpoints/hub-spoke-sync.ts:345`

```typescript
if (data.length > 0 && typeof data[0] === 'string') {
  return data.map((s) => ({ name: s }))
}
```

**问题描述:**

只检查数组第一个元素的类型。如果 Crescendia 推送了混合数组 `["tag1", { name: "tag2" }]`（数据质量问题），第一个元素是 string，所有元素都会被包装，导致 `{ name: { name: "tag2" } }`。

更严重的是，如果数组第一个元素是 `null` 或 `number`，检测跳过，后续的字符串元素不会被规范化。

**修复建议:**

```typescript
if (Array.isArray(data)) {
  if (data.every((item) => typeof item === 'string')) {
    return data.map((s) => ({ name: s }))
  }
  return data.map((item) => normalizeBlockData(item))
}
```

### M-2: `slug` 字段无 unique 索引约束

**File:** `src/collections/hub-spoke-pages/index.ts:64-75`

**问题描述:**

`slug` 字段通过 `slugField()` 辅助函数配置，但没有显式 `unique: true`。`hub-spoke-sync.ts:445-452` 的 upsert 逻辑完全依赖 `slug` 做查询来判断文档是否已存在。如果没有唯一约束，并发的 upsert 请求（同一 slug）可能导致两个 Pod 同时 `find` 返回空，然后各自 `create`，产生重复文档。

后续的 upsert 操作会 `find` 到两个文档，取第一个更新，第二个成为孤儿文档永远不会被更新也不会被删除。

**修复建议:**

在 `payload.config.ts` 的 `onInit` 中为 `hub-spoke-pages` 的 `slug` 字段创建唯一索引：

```typescript
const hspModel = payload.db.collections['hub-spoke-pages']
if (hspModel) {
  await hspModel.collection.createIndex(
    { slug: 1 },
    { unique: true, background: true },
  )
}
```

### M-3: `draft: false` 与设计文档不一致

**File:** `src/endpoints/hub-spoke-sync.ts:472, 488`

```typescript
const doc = await payload.update({
  // ...
  draft: false,
})
```

**问题描述:**

llmdoc 和设计文档多处明确声明："sync 端点写入后保持 `_status: draft`，需人工审查后发布"。但代码中使用 `draft: false`。

在 Payload CMS 中，`draft: false` 表示"不将此次写入视为草稿保存"，即直接写入主文档而非草稿版本。但由于没有显式设置 `_status: 'published'`（`docData` 中没有 `_status` 字段），实际行为取决于 Payload 的默认逻辑。如果文档之前已经是 `published` 状态，`draft: false` 会保持已发布状态，Crescendia 的更新内容会直接上线而不经过人工审查。

**实际场景:** 运营人员首次审查后将文档发布（`_status: published`），后续 Crescendia 推送更新时 `draft: false` 会在已发布文档上直接更新内容，跳过人工审查。

**修复建议:**

如果确实希望每次 sync 后都需要人工审查，应显式写入：

```typescript
docData._status = 'draft'
// 并使用 draft: true
```

或者，如果设计意图是"首次创建为 draft，后续更新直接生效"，则应更新文档描述以避免混淆。

### M-4: `toBlockSlug` 对非 ASCII 字符输入不安全

**File:** `src/endpoints/hub-spoke-sync.ts:57-59`

```typescript
export function toBlockSlug(crescendiaType: string): string | undefined {
  if (!crescendiaType) return undefined
  const slug = `hs${crescendiaType[0].toUpperCase()}${crescendiaType.slice(1)}`
  return VALID_BLOCK_SLUGS.has(slug) ? slug : undefined
}
```

**问题描述:**

虽然 `VALID_BLOCK_SLUGS` 做了兜底校验（不在集合中返回 undefined），但 `crescendiaType[0].toUpperCase()` 在特殊输入下行为不确定。例如 emoji 或多字节 Unicode 字符的 `toUpperCase()` 可能产生意外结果。这不会导致安全问题（因为 VALID_BLOCK_SLUGS 兜底），但可能产生误导性的 info 日志。

**影响等级:** Low，因为有 VALID_BLOCK_SLUGS 兜底。

### M-5: `sendBatchRevalidate` 只在网络异常时重试，HTTP 错误码不重试

**File:** `src/utilities/revalidate-frontend.ts:244-268`

```typescript
for (let i = 0; i < retries; i++) {
  try {
    const res = await fetch(...)
    if (res.ok) {
      // 成功
      return
    }
    log('error', ...) // 仅记录日志，不重试
  } catch (err) {
    // 仅 catch 分支有 sleep + 重试
    await new Promise((r) => setTimeout(r, 1000 * (i + 1)))
  }
}
```

**问题描述:**

循环结构有逻辑缺陷：`if (res.ok) return` 之后的 `log('error', ...)` 没有 `continue` 或 `throw`，代码直接进入下一次循环的 `fetch`。虽然效果上确实重试了（因为没有 return），但：

1. HTTP 503 等可恢复错误没有 backoff delay（只有 catch 分支有 delay）。
2. HTTP 400/401 等不可恢复错误也会重试，浪费资源。

**修复建议:**

```typescript
if (res.ok) {
  log('info', ...)
  return
}

if (res.status >= 400 && res.status < 500) {
  log('error', `Non-retryable error ${res.status}`)
  return // 4xx 不重试
}

// 5xx 重试，加 delay
await new Promise((r) => setTimeout(r, 1000 * (i + 1)))
```

---

## LOW

### L-1: `isImageUrl` 正则无法匹配带路径片段的 CDN URL

**File:** `src/endpoints/hub-spoke-sync.ts:65`

```typescript
const IMAGE_URL_RE = /\.(jpe?g|png|gif|webp|svg|avif|ico|bmp|tiff?)(\?.*)?$/i
```

`https://cdn.example.com/image.jpg/w=800` 这种 URL 重写模式（Cloudflare Images、Imgix 等）不会匹配。不过根据 llmdoc，Crescendia 使用标准 URL 格式，这是已知的设计取舍。

### L-2: 测试文件中 `mockPayload.find` 的 mock 覆盖范围不完整

**File:** `src/endpoints/__tests__/hub-spoke-sync.spec.ts:371-398`

`upsert 新文档调用 payload.create` 测试中，`mockPayload.find.mockResolvedValue({ docs: [] })` 覆盖了所有 `find` 调用（包括 `payload-folders` 查询），导致 `getOrCreateHubSpokeFolder` 在此测试中会尝试创建文件夹而非复用，但 `mockPayload.create` 同时 mock 了 folder 和 document 的创建。这使得测试无法区分是 folder 创建还是 document 创建。

**影响:** 测试通过但 assertion 不精确。如果 `getOrCreateHubSpokeFolder` 的 `payload.create` 失败，测试不会捕获到。

### L-3: 重复的 `sortUnique` 函数定义

**File:** `src/utilities/revalidate-frontend.ts:133-135` 和 `src/hooks/build-revalidate-hooks.ts:111-115`

两个文件各自定义了 `sortUnique` 函数，逻辑完全相同。应该提取到共享工具模块。

### L-4: `HsDownloadSection` 的 `downloadUrl` 字段可能被 `isImageUrl` 误识别

**File:** `src/collections/hub-spoke-pages/blocks/hs-download-section.ts:15`

```typescript
{ name: 'downloadUrl', type: 'text', required: true },
```

如果 Crescendia 推送了 `downloadUrl: "https://example.com/plugin.jpg"`（一个实际是压缩包但以 .jpg 结尾的文件），`processImageFields` 会尝试下载并上传到 Media，将 `downloadUrl` 替换为 Media ID，破坏了原始下载链接。

不过 `downloadUrl` 在 schema 中是 `text` 类型而非 `upload`，Payload 不会校验值格式，只是用户看到的是 Media ID 而非原始 URL。

---

## Positive Observations

1. **`buildRevalidateHooks` 策略模式重构** -- 将三个集合的 revalidate 逻辑从复制粘贴改为策略注入，消除了 540 行的 `create-revalidate-hooks.ts`，显著降低了维护成本。类型设计清晰，`RevalidateHooksConfig` 接口的 4 个方法精确描述了集合间的差异点。

2. **图片处理的 `Promise.allSettled` + 失败隔离** -- 单张图片失败不阻塞整体同步，失败记录在 `failedImages` 数组供运营审查。设 `null` 而非保留 URL 避免 BSONError，是一个正确的防御性设计。

3. **命名约定 + Schema 校验的 block 映射** -- 新增 block 只需遵循 `hs` + PascalCase 命名约定并注册到 `blocks/index.ts`，sync 端点无需修改。开放-封闭原则的良好实践。

4. **`normalizeBlockData` 的字符串数组自动包装** -- 优雅地处理了 Crescendia 推送格式与 Payload schema 之间的差异，减少了外部系统的集成负担。

5. **测试覆盖度** -- 73 个单元测试覆盖了主要路径和边界情况，包括 E11000 回退、hubSlug 解析、图片失败场景等。

6. **文档同步** -- llmdoc 文档与代码实现保持同步，架构文档准确反映了实际代码行为。

---

## Summary by Severity

| Severity | Count | Must Fix Before Merge |
|----------|-------|-----------------------|
| CRITICAL | 1     | Yes                   |
| HIGH     | 4     | Yes (H-1, H-3, H-4); H-2 可后续迭代 |
| MEDIUM   | 5     | Recommended           |
| LOW      | 4     | Nice to have          |

---

## Recommended Action

建议 **修复 C-1、H-1、H-3、H-4 后再合并**。这 4 个问题涉及生产环境的数据一致性和安全防护，是真实的风险点而非理论风险。H-2（secret in body）和 M-3（draft 语义）可以作为 follow-up issue 追踪。
