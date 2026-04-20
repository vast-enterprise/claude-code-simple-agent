# 集成测试报告：BUG-recvgVydXAVUWu blog-import 图片 src-xlarge 无效 URL 修复（v2）

> **v2 变更说明**：v1 版本仅使用单元测试，违反 tripo-test 方法论。本版本按验证对象分类选择工具（curl API + MongoDB 查询 + playwright UI 渲染），执行了真正的集成测试。

## 测试环境

- **CMS**: Worktree `bugfix/BUG-recvgVydXAVUWu-blog-import-image-null`，commit `8c7b648`，端口 3000
- **前端**: `fe-tripo-homepage` main 分支，端口 3020，`NUXT_CMS_INTERNAL_URL=http://localhost:3000`
- **数据库**: `mongodb://localhost:27017/tripo-cms`
- **测试时间**: 2026-04-16 15:39-16:10

---

## T1: API 测试 — 源图 1376x768（小于 large 阈值 1400px）

**工具**: curl + JWT 认证

**请求**:
```bash
curl -s -X POST http://localhost:3000/api/blog-import \
  -H "Content-Type: application/json" \
  -H "Authorization: JWT <token>" \
  -d '{"locale":"en","slugPrefix":"test-integration","articles":[{"title":"Test 1376w Image","slug":"test-small-image-1376w","markdown":"![test hero](https://picsum.photos/1376/768)\n\n1376px test article.","publishedAt":"2026-04-16T00:00:00Z"}]}'
```

**响应**: HTTP 200, `{"success": true, "processed": 1}`

**结果**: ✅ PASS

---

## T2: 数据持久化验证 — MongoDB

**工具**: mongosh

**查询**:
```bash
mongosh "mongodb://localhost:27017/tripo-cms" --eval 'db["geo-posts"].findOne({_id: ObjectId("69e093e5e5db2d0ded52aa75")}).markdown;'
```

**实际输出**:
```
:media-image{alt="test hero" src-small="https://cdn-blog.holymolly.ai/media/staging/image-300x167.webp" src-medium="https://cdn-blog.holymolly.ai/media/staging/image-600x335.webp" src-large="https://cdn-blog.holymolly.ai/media/staging/image-900x502.webp" width="1376" height="768"}
```

**验证**:
- ✅ 不含 `src-xlarge`（因为源图 1376px < large 阈值 1400px）
- ✅ 不含 `/null`
- ✅ src-small/medium/large 正常输出，URL 有效

**结果**: ✅ PASS

---

## T3: UI 渲染测试 — 前端图片显示

**工具**: playwright-cli snapshot + screenshot + eval

**`<picture>` DOM 结构**（`playwright-cli eval`）:
```html
<source srcset="...image-900x502.webp" media="(min-width: 900px)">
<source srcset="...image-600x335.webp" media="(min-width: 600px)">
<source srcset="...image-300x167.webp">
<img loading="lazy" width="1376" src="...image-300x167.webp" alt="test hero" decoding="async" height="768">
```

**验证**:
- ✅ 3 个 `<source>`（large/medium/small），**无 xlarge**
- ✅ 最后一个 `<source>` 无 media 属性（small fallback）
- ✅ `img.currentSrc` = `image-900x502.webp`（桌面宽度选择最大可用断点）
- ✅ 无 `/null` URL
- ✅ 截图确认图片正常渲染，无破图

**截图**: `t3-1376w-desktop.png`

**结果**: ✅ PASS

---

## T4: UI 交互测试 — 响应式断点切换

**工具**: playwright-cli resize + reload + eval

| 窗口宽度 | `img.currentSrc` | 预期断点 | 状态 |
|----------|-------------------|---------|------|
| 桌面默认 | `image-900x502.webp` | large (>= 900px) | ✅ |
| 800px | `image-600x335.webp` | medium (>= 600px) | ✅ |
| 400px | `image-300x167.webp` | small (fallback) | ✅ |

**验证**:
- ✅ 断点切换正常，缺少 xlarge 不影响浏览器降级到最大可用断点
- ✅ 所有断点 URL 有效，无 `/null`

**结果**: ✅ PASS

---

## T5: 极小图 Fallback — 源图 200x100（小于 thumbnail 阈值 300px）

**工具**: curl + mongosh + playwright-cli

### API + DB 验证

**DB 输出**:
```
:media-image{alt="tiny" src-small="https://cdn-blog.holymolly.ai/media/staging/image-1.webp" width="200" height="100"}
```
- ✅ 只有 `src-small`（原图 URL），无其他 src-* 属性
- ✅ 不含 `/null`

### UI 渲染验证

**`<picture>` DOM 结构**:
```html
<!----><!----><!---->
<source srcset="...image-1.webp">
<img loading="lazy" width="200" src="...image-1.webp" alt="tiny" decoding="async" height="100">
```

**验证**:
- ✅ 3 个 `<!---->` = 3 个 `v-if` 条件为 false（xlarge/large/medium 全部跳过）
- ✅ 仅 1 个无 media 的 `<source>`（small fallback）
- ✅ `img.currentSrc` = `image-1.webp`（原图）
- ✅ 图片被 CSS 拉伸填充容器宽度，显示正常
- ✅ 截图确认无破图、无 404

**截图**: `t5-tiny-image.png`

**结果**: ✅ PASS

---

## T6: 回归 — 源图 2000x1000（大于所有阈值）

**工具**: curl + mongosh

**DB 输出**:
```
:media-image{alt="large" src-small="...image-2-300x150.webp" src-medium="...image-2-600x300.webp" src-large="...image-2-900x450.webp" src-xlarge="...image-2-1400x700.webp" width="2000" height="1000"}
```

**验证**:
- ✅ 全部 4 个 src-* 属性存在（small/medium/large/xlarge）
- ✅ 修复没有破坏正常场景

**结果**: ✅ PASS

---

## 测试总结

| 场景 | 测试类型 | 工具 | 状态 |
|------|---------|------|------|
| T1 核心 bug（1376px） | API 测试 | curl | ✅ PASS |
| T2 数据持久化 | DB 验证 | mongosh | ✅ PASS |
| T3 UI 渲染 | UI 渲染测试 | playwright snapshot+screenshot | ✅ PASS |
| T4 断点切换 | UI 交互测试 | playwright resize+eval | ✅ PASS |
| T5 极小图（200px） | API + UI | curl + playwright | ✅ PASS |
| T6 回归（2000px） | API 测试 | curl + mongosh | ✅ PASS |

**用户担忧回应**：小尺寸图片在前端显示效果良好。前端 `media-image` 组件每个可选断点都有 `v-if` 守卫，缺失时 `<source>` 不渲染，浏览器自动降级到最大可用断点。200px 极小图被 CSS 拉伸填充容器宽度，视觉效果正常。

**结论**: 全部 6 个场景通过，修复代码在 API 层、数据层、UI 层均验证正确，无回归风险。

## 清理

- ✅ 3 条测试文章已从 DB 删除（`db["geo-posts"].deleteMany({slug: /^test-integration\//})`）
- ✅ CMS 和前端服务已停止
