# Hub-Spoke CMS 集成测试计划

**需求ID**: recvfwTbU1yXx4
**PR**: https://github.com/vast-enterprise/tripo-cms/pull/40
**测试日期**: 2026-04-13

## 测试环境

- CMS 本地开发服务器（端口 3000）
- MongoDB：开发数据库 `payload-tripo-cms-dev`
- 测试账号：guokainan@vastai3d.com

## 测试场景

### API 测试

#### T-1: 认证 — 未登录请求返回 401

**端点**: `POST /api/hub-spoke-sync`
**方法**: 不携带认证信息直接调用
**预期**: HTTP 401，body 含 `error: "Unauthorized"`

#### T-2: 认证 — API Key 认证成功

**端点**: `POST /api/hub-spoke-sync`
**方法**: 使用 Payload API Key 认证
**预期**: 认证通过，进入业务逻辑（可能返回 400 因缺必填字段）

#### T-3: 请求校验 — components 超过 100 返回 400

**端点**: `POST /api/hub-spoke-sync`
**方法**: 发送 `components` 数组长度 > 100
**预期**: HTTP 400，body 含 `"Too many components"`

#### T-4: upsert Hub 页面 — 创建新文档

**端点**: `POST /api/hub-spoke-sync`
**方法**: 发送完整的 Hub 页面数据（含 hero、faq、ctaBanner 三种 block + 图片 URL）
**预期**:
- HTTP 200，`action: "created"`
- MongoDB 中存在对应 slug 的文档
- 图片 URL 已替换为 Media ID
- `mediaSynced` 字段反映图片处理结果

#### T-5: upsert Hub 页面 — 更新已有文档

**端点**: `POST /api/hub-spoke-sync`
**方法**: 对 T-4 创建的文档再次发送修改后的数据（修改 title）
**预期**: HTTP 200，`action: "updated"`，title 已更新

#### T-6: upsert Spoke 页面 — 创建并关联 Hub

**端点**: `POST /api/hub-spoke-sync`
**方法**: 发送 Spoke 页面数据，`hubSlug` 指向 T-4 创建的 Hub
**预期**: HTTP 200，`hubSlug` 字段为 Hub 文档 ID（relationship）

#### T-7: delete — 删除已有文档

**端点**: `POST /api/hub-spoke-sync`
**方法**: `action: "delete"`，slug 为 T-6 创建的 Spoke
**预期**: HTTP 200，`action: "deleted"`

#### T-8: delete — 删除不存在的文档

**端点**: `POST /api/hub-spoke-sync`
**方法**: `action: "delete"`，slug 为不存在的值
**预期**: HTTP 200，`action: "noop"`

#### T-9: 图片下载超时保护

**端点**: `POST /api/hub-spoke-sync`
**方法**: 发送含不可达图片 URL 的数据（如 `http://10.255.255.1/slow.jpg`）
**预期**: 图片下载失败但不阻塞整个请求，`failedImages` 数组包含失败信息

#### T-10: sitemap-meta 端点

**端点**: `GET /api/hub-spoke-sitemap-meta`
**方法**: 直接 GET 调用
**预期**: 返回 `{ locales: [...] }` 含各语言的 count 和 lastmod

### 降级条件

以下场景如无法在本地测试，标记为 DEFERRED：
- 图片实际上传到 OSS（需 OSS 配置）→ 可用本地 Media 验证
- Webhook revalidate 触发 → 需前端服务运行

## 执行顺序

T-1 → T-2 → T-3 → T-4 → T-5 → T-6 → T-7 → T-8 → T-9 → T-10

## 前置条件

- [ ] CMS dev server 启动成功
- [ ] MongoDB 连接正常
- [ ] 获取 Payload API Key
