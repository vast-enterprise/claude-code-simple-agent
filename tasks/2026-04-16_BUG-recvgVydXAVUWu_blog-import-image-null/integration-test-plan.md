# 集成测试计划：BUG-recvgVydXAVUWu blog-import 图片 src-xlarge 无效 URL 修复（v2）

> **v2 变更说明**：v1 版本违反 tripo-test 方法论（全部使用单元测试），本版本按验证对象分类选择正确的测试类型。

## 测试环境

- **本地 CMS**:
  - Worktree: `/Users/macbookair/Desktop/projects/tripo-cms/.worktrees/bugfix/BUG-recvgVydXAVUWu-blog-import-image-null`
  - 分支: `bugfix/BUG-recvgVydXAVUWu-blog-import-image-null`
  - Commit: `8c7b648`
  - 端口: 3000
  - 数据库: `payload-tripo-cms-dev`（开发库，非生产）

- **本地前端**:
  - 路径: `/Users/macbookair/Desktop/projects/fe-tripo-homepage`
  - 分支: main
  - 端口: 3020
  - 环境变量: `NUXT_CMS_INTERNAL_URL=http://localhost:3000`
  - Feature Flag: `blogLegacy=false`（CMS app-config global 配置）

## 测试范围

对应 bug-investigation.md 中列出的**受影响范围**：

| 源图宽度 | 受影响属性 | 修复后预期 |
|---------|----------|----------|
| < 300px | src-small, src-medium, src-large, src-xlarge | src-small fallback 到原图，其他不输出 |
| 300-599px | src-medium, src-large, src-xlarge | src-small 正常，其他不输出 |
| 600-899px | src-large, src-xlarge | src-small/medium 正常，其他不输出 |
| 900-1399px | src-xlarge | src-small/medium/large 正常，不输出 src-xlarge |
| >= 1400px | 无 | 全部 src-* 正常（回归） |

## 测试场景（按 tripo-test 分类）

### 场景 T1：API 测试 — blog-import 端点响应数据

**验证对象**: HTTP 接口响应数据

**验证什么**: 
- blog-import 端点接收含小尺寸图片的文章后，返回的 `content` 字段不含 `/null` URL
- 生成的 `:media-image{}` 指令中，缺失的断点属性不输出（而非输出 `src-xlarge="...null"`）

**用什么工具**: curl + jq

**测试数据准备**:
```json
{
  "title": "Test Small Image",
  "slug": "test-small-image-integration",
  "content": "![test](https://picsum.photos/1376/768)",
  "author": "Test Author",
  "publishedAt": "2026-04-16T00:00:00Z",
  "categories": ["test"]
}
```
- 图片 URL: `https://picsum.photos/1376/768`（1376px 宽，小于 large 阈值 1400px）
- 必填字段全部赋值
- 边界值：图片宽度刚好小于 large 阈值

**证据形式**: 
1. curl 请求命令（含完整 payload）
2. API 响应 body（JSON 格式化）
3. 提取 `content` 字段，grep 验证不含 `/null`
4. 提取 `:media-image{}` 指令，确认 `src-xlarge` 不存在

**预期结果**:
- HTTP 200
- `content` 包含 `:media-image{alt="test" src-small="..." src-medium="..." src-large="..." width="1376" height="768"}`
- 不含 `src-xlarge`
- 不含 `/null`

---

### 场景 T2：数据持久化验证 — MongoDB 存储

**验证对象**: 数据库存储的 content 字段

**验证什么**: blog-import 写入 DB 的 geo-posts 文档，content 字段与 API 响应一致

**用什么工具**: mongosh 查询

**测试数据**: 场景 T1 推送的文章（slug: `test-small-image-integration`）

**证据形式**:
```bash
mongosh "mongodb://localhost:27017/payload-tripo-cms-dev" \
  --eval 'db.getCollection("geo-posts").findOne({slug: "test-small-image-integration"}, {content: 1})'
```
输出 content 字段内容

**预期结果**: 与 T1 API 响应的 content 字段完全一致

---

### 场景 T3：UI 渲染测试 — 前端图片显示

**验证对象**: 页面元素存在性、样式、实际加载的图片 URL

**验证什么**: 
- 前端 blog 页面能正常渲染含小尺寸图片的文章
- `<picture>` 标签生成正确（缺失的 `<source>` 不渲染）
- 浏览器实际加载的图片 URL 不含 `/null`
- 图片显示效果正常（用户担忧：小图会不会显示不好）

**用什么工具**: playwright snapshot + screenshot

**测试数据**: 场景 T1 推送的文章，前端 URL: `http://localhost:3020/blog/test-small-image-integration`

**证据形式**:
1. playwright snapshot 输出 `<picture>` 标签的 DOM 结构
2. playwright screenshot 截图（全页面 + 图片特写）
3. playwright eval 获取 `img.currentSrc`（浏览器实际加载的图片）
4. Network 面板截图（确认无 `/null` 请求）

**预期结果**:
- `<picture>` 包含 3 个 `<source>`（small/medium/large），不含 xlarge
- `<img src="...">` fallback 正常
- `img.currentSrc` 指向有效图片 URL（根据窗口宽度选择断点）
- 图片正常显示，无破图、无 404
- Network 面板无 `/null` 请求

---

### 场景 T4：UI 交互测试 — 响应式断点切换

**验证对象**: 操作后 UI 状态变化

**验证什么**: 调整浏览器窗口宽度时，`<picture>` 能正确切换断点（即使缺少 xlarge）

**用什么工具**: playwright resize + screenshot

**测试数据**: 场景 T3 的页面

**证据形式**:
1. 窗口 1920px 宽时的截图 + `img.currentSrc`
2. 窗口 1200px 宽时的截图 + `img.currentSrc`
3. 窗口 800px 宽时的截图 + `img.currentSrc`
4. 窗口 400px 宽时的截图 + `img.currentSrc`

**预期结果**:
- 1920px: 使用 large 断点（因为 xlarge 不存在）
- 1200px: 使用 large 断点
- 800px: 使用 medium 断点
- 400px: 使用 small 断点
- 所有断点切换流畅，图片显示正常

---

### 场景 T5：极小图 Fallback — 仅 src-small

**验证对象**: HTTP 接口响应数据 + UI 渲染

**验证什么**: 源图 < 300px 时，只输出 src-small（fallback 到原图），前端能正常显示

**用什么工具**: curl + playwright

**测试数据**:
```json
{
  "title": "Test Tiny Image",
  "slug": "test-tiny-image-integration",
  "content": "![tiny](https://picsum.photos/200/100)",
  "author": "Test Author",
  "publishedAt": "2026-04-16T00:00:00Z",
  "categories": ["test"]
}
```
- 图片 URL: `https://picsum.photos/200/100`（200px 宽，小于 thumbnail 阈值 300px）

**证据形式**:
1. curl 响应 body（验证 `:media-image{}` 只有 src-small）
2. playwright snapshot（验证 `<picture>` 只有 1 个无 media 的 `<source>`）
3. playwright screenshot（验证图片显示正常）

**预期结果**:
- API 响应: `:media-image{alt="tiny" src-small="..." width="200" height="100"}`（无其他 src-*）
- 前端 DOM: `<picture>` 只有 1 个 `<source :srcset="...">`（无 media 属性）+ `<img>`
- 图片正常显示

---

### 场景 T6：回归 — 正常尺寸图片

**验证对象**: HTTP 接口响应数据

**验证什么**: 源图 >= 1400px 时，全部 src-* 正常输出（修复没有破坏正常场景）

**用什么工具**: curl

**测试数据**:
```json
{
  "title": "Test Large Image",
  "slug": "test-large-image-integration",
  "content": "![large](https://picsum.photos/2000/1000)",
  "author": "Test Author",
  "publishedAt": "2026-04-16T00:00:00Z",
  "categories": ["test"]
}
```
- 图片 URL: `https://picsum.photos/2000/1000`（2000px 宽，大于所有阈值）

**证据形式**: curl 响应 body

**预期结果**:
- `:media-image{alt="large" src-small="..." src-medium="..." src-large="..." src-xlarge="..." width="2000" height="1000"}`
- 全部 4 个 src-* 属性存在

---

## 测试前置条件

1. ✅ CMS worktree 依赖已安装（`pnpm install`）
2. ✅ 前端依赖已安装
3. ✅ 前端 `.env` 文件已复制到项目根目录，包含 `NUXT_CMS_INTERNAL_URL=http://localhost:3000`
4. ✅ CMS app-config global 中 `blogLegacy=false`
5. ⚠️ 本地不连接生产数据库（铁律禁止）

## 执行顺序

1. 启动 CMS 服务（端口 3000）
2. 启动前端服务（端口 3020，`pnpm dev --host localhost --port 3020 --no-https`）
3. 场景 T1 → T2 → T3 → T4（核心流程）
4. 场景 T5（边界场景）
5. 场景 T6（回归）
6. 停止服务

## 工具纪律

- 用户未指定工具 → 按 tripo-test 分类表选择
- playwright 遇到障碍 → 先排障，不私自替换为 curl
- 替代方案必须标注 `⚠️ 工具替代: <原因>`
