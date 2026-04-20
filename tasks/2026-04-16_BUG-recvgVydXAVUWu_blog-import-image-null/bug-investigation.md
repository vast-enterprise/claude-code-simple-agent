# Bug 调查报告：blog-import 图片 src-xlarge 无效 URL

## Bug 现象

通过 `POST /api/blog-import` 推送的文章中，`:media-image` directive 的 `src-xlarge` 属性指向无效 URL：

```
src-xlarge="https://cdn-blog.holymolly.ai/media/staging/null"
```

完整示例（staging 环境，slug: `crescendia/ai-3d-for-animation-2026`）：

```
:media-image{alt="2D to 3D AI generation process"
  src-small="https://cdn-blog.holymolly.ai/media/staging/2304381677094a69ba587c786139fd1b-300x167.webp"
  src-medium="https://cdn-blog.holymolly.ai/media/staging/2304381677094a69ba587c786139fd1b-600x335.webp"
  src-large="https://cdn-blog.holymolly.ai/media/staging/2304381677094a69ba587c786139fd1b-900x502.webp"
  src-xlarge="https://cdn-blog.holymolly.ai/media/staging/null"
  width="1376" height="768"}
```

## 环境

- 环境：staging (`cms-staging.itripo3d.com`)
- 仓库：tripo-cms
- 端点：`POST /api/blog-import`

## 根因分析

### 1. Media 尺寸配置

`src/collections/media/index.ts:58-89` 定义了 7 个 imageSizes：

| 名称 | 目标宽度 |
|------|---------|
| thumbnail | 300 |
| square | 500x500 |
| small | 600 |
| medium | 900 |
| large | 1400 |
| xlarge | 1920 |
| og | 1200x630 |

### 2. Payload CMS 的 sizes 行为

当源图宽度 **小于** 目标尺寸时（如 1376px < large 的 1400px），Payload CMS：
- **不生成**实际的缩放文件
- 但**仍然创建** sizes 对象，其中 `filename: null`，`width: null`，`height: null`
- `url` 字段通过 `prefix + "/" + filename` 拼接，得到 `"https://cdn-blog.holymolly.ai/media/staging/null"`

已验证的数据证据（从同 staging 环境的 media 记录获取）：

```json
"large": {
    "width": null,
    "height": null,
    "mimeType": null,
    "filesize": null,
    "filename": null,
    "url": "https://cdn-blog.holymolly.ai/media/staging/null"
}
```

### 3. 代码缺陷位置

`src/endpoints/blog-import/process-images.ts:83-91`：

```typescript
const attrs = [
  `alt="${escapeAttr(altText || media.alt || '')}"`,
  `src-small="${escapeAttr(sizes.thumbnail?.url || media.url || '')}"`,
  sizes.small?.url ? `src-medium="${escapeAttr(sizes.small.url)}"` : '',
  sizes.medium?.url ? `src-large="${escapeAttr(sizes.medium.url)}"` : '',
  sizes.large?.url ? `src-xlarge="${escapeAttr(sizes.large.url)}"` : '',  // <-- BUG
  media.width ? `width="${media.width}"` : '',
  media.height ? `height="${media.height}"` : '',
].filter(Boolean).join(' ')
```

**缺陷**：用 `sizes.large?.url` 作为判断条件。但 `url` 为 `"https://cdn.../null"` —— 是非空字符串，条件判断为 truthy，导致写入了无效 URL。

### 4. 触发条件

源图宽度 < 对应 imageSize 目标宽度时触发：

| 源图宽度范围 | 受影响属性 |
|-------------|----------|
| < 600px | src-medium, src-large, src-xlarge |
| 600-899px | src-large, src-xlarge |
| 900-1399px | src-xlarge |
| >= 1400px | 无（全部正常） |

本案例：源图 1376px，仅 `src-xlarge`（对应 `sizes.large` 1400w）受影响。

## 受影响范围

1. **blog-import 端点**：所有通过此端点推送的、源图宽度 < 1400px 的文章
2. **已入库数据**：staging 环境已有数据可能包含同类问题
3. **hub-spoke-sync 端点**：不受影响（grep 确认不使用 sizes.*.url 模式）
4. **src-small 属性**：使用 `||` fallback 而非三元条件，当 thumbnail.url 为 ".../null" 时会 fallback 到 media.url，行为不同但也需审查

## 修复后的呈现效果

修复方案：将判断条件从 `sizes.*.url` 改为 `sizes.*.filename`。当某个 size 未生成实际文件时（filename=null），对应的 `src-*` 属性直接不输出，而不是输出无效 URL。

### 不同源图尺寸下的 :media-image 输出对比

**源图 1376x768（本案例）**：large(1400w) 和 xlarge(1920w) 未生成

```
:media-image{alt="..." src-small="...300x167.webp" src-medium="...600x335.webp" src-large="...900x502.webp" width="1376" height="768"}
```

src-xlarge 不再输出。前端 `<picture>` 组件在 >900px 视口时使用 src-large（900w），或直接 fallback 到原图。

**源图 800x500**：small(600w) 以下正常，medium(900w) 起不生成

```
:media-image{alt="..." src-small="...300x188.webp" src-medium="...600x375.webp" width="800" height="500"}
```

src-large 和 src-xlarge 都不输出。大视口使用 src-medium（600w）。

**源图 400x300**：只有 thumbnail(300w) 生成

```
:media-image{alt="..." src-small="...300x225.webp" width="400" height="300"}
```

仅 src-small 可用，所有视口都使用同一张 300w 图。

**源图 200x100**：所有 size 都未生成（200 < 300）

```
:media-image{alt="..." src-small="https://cdn.../original.webp" width="200" height="100"}
```

所有 size 的 filename 均为 null，src-small fallback 到 `media.url`（原图 URL），不会出现 `.../null`。

### 关键结论

修复后的行为是**渐进增强**——图越大，可用的响应式断点越多；图太小则自然降级到更少的断点。不会出现无效 URL，前端 `<picture>` 组件会自动选择可用的最大尺寸。

### 补充发现：src-small 行也需修复

原代码：
```typescript
`src-small="${escapeAttr(sizes.thumbnail?.url || media.url || '')}"`,
```

当源图 < 300px 时，`sizes.thumbnail.url` 是 `".../null"`（truthy 字符串），`||` 不会 fallback 到 `media.url`，导致 src-small 也指向无效 URL。需改为：

```typescript
`src-small="${escapeAttr(sizes.thumbnail?.filename ? sizes.thumbnail.url : (media.url || ''))}"`,
```

### 完整修复代码

```typescript
const attrs = [
  `alt="${escapeAttr(altText || media.alt || '')}"`,
  `src-small="${escapeAttr(sizes.thumbnail?.filename ? sizes.thumbnail.url : (media.url || ''))}"`,
  sizes.small?.filename ? `src-medium="${escapeAttr(sizes.small.url)}"` : '',
  sizes.medium?.filename ? `src-large="${escapeAttr(sizes.medium.url)}"` : '',
  sizes.large?.filename ? `src-xlarge="${escapeAttr(sizes.large.url)}"` : '',
  media.width ? `width="${media.width}"` : '',
  media.height ? `height="${media.height}"` : '',
].filter(Boolean).join(' ')
```

## 关联信息

- **所属需求**: REQ-recvfBaaUwYzCy (blog-import)
- **引入提交**: `bfb4138 feat: add blog-import endpoint for Crescendia GEO content`
- **PR**: #37 (`feature/REQ-recvfBaaUwYzCy-blog-import`)
