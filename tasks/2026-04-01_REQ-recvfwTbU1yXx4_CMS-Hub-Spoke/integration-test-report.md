# Hub-Spoke CMS 集成测试报告

**需求ID**: recvfwTbU1yXx4
**PR**: https://github.com/vast-enterprise/tripo-cms/pull/40
**测试日期**: 2026-04-13
**测试环境**: CMS 本地 dev server (localhost:3000) + MongoDB 开发库

## 测试结果汇总

| 测试 | 场景 | 结果 | 响应 |
|------|------|------|------|
| T-1 | 未登录返回 401 | ✅ PASS | `{"error":"Unauthorized","message":"需要登录后调用"}` HTTP 401 |
| T-2 | JWT 认证通过 | ✅ PASS | `{"error":"Missing required fields"}` HTTP 400 (认证通过，缺字段) |
| T-3 | components > 100 返回 400 | ✅ PASS | `{"error":"Too many components (max 100, got 101)"}` HTTP 400 |
| T-4 | upsert Hub 创建 | ✅ PASS | `{"success":true,"action":"created","mediaSynced":true}` HTTP 200 |
| T-5 | upsert Hub 更新 | ✅ PASS | `{"success":true,"action":"updated","mediaSynced":true}` HTTP 200 |
| T-6 | upsert Spoke 关联 Hub | ✅ PASS | `{"success":true,"action":"created","mediaSynced":true}` HTTP 200 |
| T-7 | delete 已有文档 | ✅ PASS | `{"success":true,"action":"deleted"}` HTTP 200 |
| T-8 | delete 不存在文档 | ✅ PASS | `{"success":true,"action":"noop","reason":"not_found"}` HTTP 200 |
| T-9 | 图片超时保护 | ✅ PASS | `{"success":true,"mediaSynced":false,"failedImages":[{"error":"aborted due to timeout"}]}` HTTP 200 |
| T-10 | sitemap-meta 端点 | ✅ PASS | `{"locales":[]}` HTTP 200 |

**10/10 通过，0 失败，0 降级。**

## 重构验证

本次测试同时验证了 Code Review 后的重构改动：

| 改动 | 验证结果 |
|------|---------|
| 统一认证（req.user） | T-1/T-2 确认：JWT 认证正常工作 |
| 图片超时保护（10s） | T-9 确认：不可达 URL 超时后返回 failedImages，不阻塞请求 |
| components 上限（100） | T-3 确认：101 个 components 返回 400 |
| 共享 media-download 模块 | T-4/T-5 确认：图片下载 + 去重正常工作 |
| p-limit 并发控制 | T-4 确认：并发下载图片未报错 |

## 单元测试

```
Test Files  9 passed (9)
Tests       117 passed (117)
Duration    1.58s
```

## TypeCheck

```
npx tsc --noEmit → 0 errors
```

## 发现的问题

### 已修复
- T-9 首次测试时 hero block 缺少 subtitle 导致 Payload 校验失败返回 500 — 这是测试数据问题，非代码 bug

### 未发现新问题
- 所有端点行为符合预期
- 重构后功能完整性保持

## 测试数据清理

测试创建的文档已在测试完成后删除：
- `integration-test-hub` → deleted
- `test-timeout-image` → deleted
