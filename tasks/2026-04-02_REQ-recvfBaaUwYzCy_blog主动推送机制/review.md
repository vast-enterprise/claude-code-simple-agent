# 需求评审

## 需求来源

- 需求ID: `recvfBaaUwYzCy`
- 需求描述: blog 主动推送机制
- 需求Owner: 黄傲磊
- 研发Owner: 郭凯南
- 来源文档: https://tripo3d.feishu.cn/base/HMvbbjDHOaHyc6sZny6cMRT8n8b?table=tblb9E9PQHP79JHE&view=vewMnpNgGD&record=recvfBaaUwYzCy

## 需求背景

外部 GEO 厂商具备批量生成 geo-blog 内容的能力，需要 CMS 提供接口，让厂商能够主动将生成的 blog 内容推送到 CMS 系统中。

## 现状分析

### 关键代码

| 组件 | 文件 | 职责 |
|------|------|------|
| Posts Collection | `src/collections/posts/index.ts` | Blog 数据模型 |
| 共享字段 | `src/fields/post-shared.ts` | Posts/GeoPosts 共享字段定义 |
| Users Collection | `src/collections/users/index.ts` | 用户认证（含 API Key 支持） |
| 认证中间件 | `src/access/authenticated.ts` | 已登录用户访问控制 |
| 自定义端点示例 | `src/endpoints/data-backfill/execute.ts` | 现有自定义端点参考 |
| 环境变量 | `src/constants/env.ts` | 配置中心 |

### Posts 字段模型

| 字段 | 类型 | 必填 | 本地化 | 说明 |
|------|------|------|--------|------|
| `title` | text | Yes | Yes | 标题 |
| `slug` | text | Yes | No | URL slug |
| `contentType` | select | Yes | No | lexical/markdown/external |
| `content` | richText | 条件 | Yes | contentType=lexical |
| `markdown` | textarea | 条件 | Yes | contentType=markdown |
| `heroImage` | upload | No | No | 关联 media |
| `description` | textarea | No | Yes | 描述 |
| `categories` | relationship | No | No | 关联 categories |
| `authors` | relationship | No | No | 关联 users |
| `publishedAt` | date | No | No | 发布时间 |
| `meta.*` | group | No | No | SEO 字段 |
| `_status` | select | No | No | draft/published |

### 现有认证机制

- **API Key**: Users 集合已启用 `useAPIKey: true`，可为厂商分配专用账号 + API Key
- **JWT**: 标准 Payload 登录认证
- 但厂商**不应直接调用 Payload API**，因为无法自动处理 markdown 中的图片到 media

## 需求范围

### 核心功能

1. **自定义 API Endpoint**: 提供 `POST /api/blog-import` 接口供厂商调用
2. **Markdown 内容处理**: 接收 Markdown 格式文章，处理为 CMS Posts 数据
3. **图片处理**: Markdown 中的图片需自动下载并上传到 CMS media collection（技术评审详论）
4. **批量推送**: 支持单次请求推送 100+ 篇文章
5. **多语言支持**: 通过 locale 参数支持多语言，厂商多次调用不同语言
6. **更新能力**: 支持更新已推送但未发布的文章
7. **草稿模式**: 推送后文章为 draft 状态，需人工审核后发布

### 边界条件

- 接口协议由我们定义，厂商按协议对接
- 认证使用 Payload API Key 机制
- 大批量推送需要考虑限流和性能
- 幂等性：相同内容重复推送应能识别

### 不包含

- 厂商直接调用 Payload CRUD API
- 文章发布流程（由人工在 CMS 后台操作）
- GeoPosts 推送（由独立需求覆盖）
- 文章删除能力

## 技术方案

### 方案：自定义 Endpoint

在 CMS 中新增自定义 endpoint，内部处理全流程：

```
厂商
  │  POST /api/blog-import
  │  Headers: Authorization: <user_id> API-Key <api_key>
  │  Body: { locale, articles: [{ title, markdown, ... }] }
  ▼
CMS 自定义 Endpoint
  │
  ├── 1. API Key 认证验证
  ├── 2. 请求参数校验
  ├── 3. Markdown 图片提取 → 下载 → 上传 media collection → 替换 URL
  ├── 4. 创建/更新 Posts（_status: draft）
  └── 5. 返回批量结果（成功/失败明细）
```

### 改动范围

| 仓库 | 文件 | 改动 |
|------|------|------|
| tripo-cms | `src/endpoints/blog-import/` | **新增** 自定义 endpoint（handler + validation） |
| tripo-cms | `src/utilities/markdown-image.ts` | **新增** Markdown 图片处理工具 |
| tripo-cms | `src/payload.config.ts` | **修改** 注册新 endpoint |
| tripo-cms | `src/constants/env.ts` | **修改** 新增配置（限流阈值等） |

### API 协议草案

```typescript
// POST /api/blog-import
// Content-Type: application/json
// Authorization: <user_id> API-Key <api_key>

// Request
{
  "locale": "en",                    // 语言代码
  "articles": [
    {
      "title": "文章标题",
      "slug": "article-slug",        // 可选，自动生成
      "markdown": "# 正文\n...![img](https://external.com/img.jpg)...",
      "description": "文章描述",      // 可选
      "categories": ["slug-1"],      // 可选，按 slug 匹配
      "publishedAt": "2026-04-02",   // 可选
    }
  ]
}

// Response
{
  "success": true,
  "results": [
    { "title": "文章标题", "id": "post_id", "status": "created" },
    { "title": "重复文章", "id": "existing_id", "status": "skipped", "reason": "duplicate slug" }
  ]
}
```

## 验收标准

1. 厂商可通过 API Key 认证调用 `POST /api/blog-import` 推送文章
2. 支持单次批量推送 100+ 篇 Markdown 文章
3. Markdown 中的图片自动下载并上传到 media collection，文章中 URL 已替换
4. 推送后文章为 draft 状态，不对外可见
5. 支持通过 locale 参数指定语言版本
6. 支持更新已推送的草稿文章
7. 无效请求返回清晰的错误信息
8. 接口有基本的限流保护

## 技术约束

- 接口协议由 CMS 侧定义，厂商按文档对接
- 图片处理逻辑在技术评审阶段详细讨论
- 批量操作需注意 MongoDB 写入性能
- Payload CMS 3.x + Next.js 15 技术栈

## 问题与风险

1. **图片处理复杂度**: Markdown 中图片可能是各种外部 URL，下载失败的处理策略需明确
2. **幂等性**: 同一篇文章重复推送时，如何判断是更新还是重复（slug 去重？）
3. **大批量性能**: 100+ 篇含图片的文章，单次请求处理时间可能较长，需考虑超时策略
4. **限流**: 需防止厂商恶意或错误的大量请求

## 评审结论

- [x] 需求范围明确
- [x] 验收标准清晰
- [x] 无阻塞性风险
