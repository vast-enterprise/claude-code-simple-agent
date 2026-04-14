# 集成测试计划：Translation Plugin

## 测试环境

| 项目 | 值 |
|------|-----|
| 服务 | tripo-cms (Payload CMS 3.69 + Next.js 15) |
| 数据库 | 本地 MongoDB (payload-tripo-cms-dev) |
| Worktree | `/Users/macbookair/Desktop/projects/tripo-cms/.worktrees/translation-plugin/` |
| 端口 | 3000 |
| 认证 | CMS admin 账户 (guokainan@vastai3d.com) |

## 前置条件

- [ ] CMS 服务在 worktree 中启动成功
- [ ] Plugin 已在 `payload.config.ts` 中注册
- [ ] 获取 admin 认证 token

## 测试场景

### T1: Plugin 注册验证

**目标**: 确认 plugin 正确注入 endpoints 和 hooks
- 启动 CMS，检查日志无报错
- 访问 `/api/translate/status?collection=posts` 验证 endpoint 存在

### T2: 文档翻译 API (POST /api/translate/document)

**目标**: 验证文档级翻译 endpoint 功能正确

| # | 场景 | 请求 | 预期 |
|---|------|------|------|
| T2.1 | 正常翻译 | collection=posts, id=一篇有英文内容的 Post, from=en, to=zh | 200, translatedData 包含中文 |
| T2.2 | emptyOnly=true（有已有翻译） | 同上但目标 locale 已有内容 | 已有内容不被覆盖 |
| T2.3 | 未认证 | 不带 auth header | 401 |
| T2.4 | 非法 collection | collection=users | 403 |
| T2.5 | 不存在的文档 | id=不存在的 ID | 500 (document not found) |

### T3: 字段翻译 API (POST /api/translate/field)

| # | 场景 | 请求 | 预期 |
|---|------|------|------|
| T3.1 | 翻译 title 字段 | fieldPath=title | 200, translatedValue 为翻译后的标题 |
| T3.2 | 翻译嵌套字段 | fieldPath=meta.title | 200, 翻译 SEO 标题 |

### T4: 翻译状态 API (GET /api/translate/status)

| # | 场景 | 请求 | 预期 |
|---|------|------|------|
| T4.1 | 单文档状态 | collection=posts&id=xxx | 返回 7 个 locale 的 complete/partial/missing |
| T4.2 | 非法 collection | collection=users | 403 |

### T5: 批量翻译 API (POST /api/translate/batch)

> 注意：batch 会实际调用 resolver 并写 DB，使用 copyResolver 避免 OpenAI 费用。

| # | 场景 | 请求 | 预期 |
|---|------|------|------|
| T5.1 | ids 模式 | ids=[2 个 Post ID], from=en, to=zh | total=2, success=2 |

### T6: UI 自动化验证（playwright-cli）

**工具**: playwright-cli
**目标**: 验证 Admin Panel 中翻译插件的 UI 注入和交互

| # | 场景 | 操作 | 验证方式 |
|---|------|------|---------|
| T6.1 | Admin 登录正常 | 打开 Admin → 登录 | 截图 + snapshot 确认进入 Dashboard |
| T6.2 | Posts 列表页加载 | 导航到 /admin/collections/posts | snapshot 确认列表渲染正常，无 console error |
| T6.3 | Post 编辑页加载 | 点击某篇 Post 进入编辑 | snapshot 确认编辑表单渲染，检查 afterRead hook 注入的 `_translationStatus` 字段 |
| T6.4 | Translate 按钮渲染 | 在 Post 编辑页查找 "Translate" 按钮 | snapshot 中有 `button "Translate"` |
| T6.5 | Translate Modal 弹出 | 点击 Translate 按钮 | 截图确认 Modal 含 Source locale、Target 下拉、emptyOnly 复选框 |
| T6.6 | Console 无代码 bug | 检查浏览器 console | 无代码导致的 error（网络 error 可接受） |

### T7: UI 端到端真实翻译流程（playwright-cli + openai resolver）

**工具**: playwright-cli
**前置**: CMS 已配置 `OPENAI_API_KEY` + `OPENAI_BASE_URL` + `OPENAI_MODEL`，真实翻译可用
**目标**: 验证从 Admin UI 触发的完整翻译流程——用户点击按钮到看到翻译结果

| # | 场景 | 操作 | 验证方式 |
|---|------|------|---------|
| T7.1 | 打开编辑页并确认 Translate 按钮 | 登录 → 导航到 Post 编辑页 | snapshot 确认 "Translate" 按钮存在 |
| T7.2 | 打开翻译 Modal | 点击 Translate 按钮 | snapshot 确认 Modal 弹出，含 Source/Target/emptyOnly |
| T7.3 | 选择目标语言 | 在 Target 下拉中选择一个 locale（如 ko） | snapshot 确认选择生效 |
| T7.4 | 执行翻译 | 点击 Modal 中的 Translate 按钮 | 等待翻译完成，截图确认结果消息（成功的翻译字段数或错误信息） |
| T7.5 | 验证翻译结果 | 翻译成功后关闭 Modal，页面 reload | 切换到目标 locale 查看翻译后的内容是否回填 |

## 降级条件

- 如果 CMS 启动失败（缺环境变量、MongoDB 未连接）：标记 ⚠️ DEFERRED
- 如果无 OpenAI API Key：使用 copyResolver 替代（仅复制文本验证流程）
- 批量翻译（T5）如影响生产数据：标记 ⚠️ DEFERRED
- playwright-cli 无法启动浏览器：标记 ⚠️ DEFERRED，附失败日志
