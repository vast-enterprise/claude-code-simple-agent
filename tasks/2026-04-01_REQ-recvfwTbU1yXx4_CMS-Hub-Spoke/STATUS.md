# REQ: CMS接入Hub-Spoke

## 基本信息

| 项目 | 值 |
|------|-----|
| 需求ID | recvfwTbU1yXx4 |
| 需求描述 | CMS接入Hub-Spoke |
| 需求Owner | 连想 |
| 研发Owner | 郭凯南 |
| 启动时间 | 2026-04-01 |
| 预期交付 | 2026-04-16 |
| 涉及仓库 | tripo-cms, fe-tripo-homepage |

## 状态历史

| 时间 | 阶段 | 状态 | 备注 |
|------|------|------|------|
| 2026-04-01 | 需求录入 | ✅ 完成 | 已录入产品需求池 recvfwTbU1yXx4 |
| 2026-04-01 | 进入执行表 | ✅ 完成 | 执行表记录 recvfBp9eR8ZGK |
| 2026-04-01 ~ 04-08 | CMS 后端开发 | ✅ 完成 | worktree: tripo-cms/.worktrees/hub-spoke/, 分支: feat/hub-spoke-pages |
| 2026-04-01 ~ 04-10 | 前端渲染层开发 | ✅ 完成 | feat/hub-spoke + fix-hub-spoke 分支已全部合入 main (PR #186 等) |
| 2026-04-13 | 需求重组 | ✅ 完成 | 原名"CMS接入Hub-Spoke & 编辑blog首页"拆分，Hub-Spoke 独立，"编辑blog首页"归入 Blog 排序需求 |
| 2026-04-13 | Code Review | ✅ 完成 | 对抗性审查完成，H-1(超时)/H-4(数组限制)已修复 |
| 2026-04-13 | 统一重构 | ✅ 完成 | 提取 media-download.ts 共享模块，统一认证/超时/并发 |
| 2026-04-13 | CMS PR | ✅ 完成 | PR #40: https://github.com/vast-enterprise/tripo-cms/pull/40 |
| 2026-04-13 | 集成测试 | ✅ 完成 | 10/10 通过，117 单元测试通过，tsc 0 errors |
| 2026-04-13 | 飞书通知 | ✅ 完成 | 步骤 8 闭环通知已发送 |
| 2026-04-14 | CMS PR 合并 | ✅ 完成 | PR #40 已合并到 main，主工作区已同步 |
| 2026-04-14 | 验收修复 | ✅ 完成 | 移除 sync API delete 能力、补全 articleHeader 必填字段、更新 API 文档并推送 wiki |
| 2026-04-14 | 前端 CMS 接入 | ⏳ 未启动 | worktree 已创建，PLAN.md 已写入，CMS 已合并可开发 |
| 2026-04-14 | 前端技术评审 | ✅ 完成 | 方案 A+（服务端适配层 + Media sizes 响应式），用户确认 |
| 2026-04-14 | 前端开发 | ✅ 完成 | 8 文件改动，67 单测，151 全量测试通过 |
| 2026-04-14 | 前端 PR | ✅ 完成 | PR #188: https://github.com/vast-enterprise/fe-tripo-homepage/pull/188 |
| 2026-04-14 | 前端闭环 | 🔄 进行中 | 步骤 8 Code Review + 测试 |

## 当前状态

- **阶段**: 步骤 9 验收中 → 前端子循环步骤 8（自动化闭环）
- **状态**: PR #188 已创建，进入 Code Review + 测试闭环
- **下一步**: Code Review → 测试报告 → 飞书通知 → 本地联调 → 合并

## 已完成的工作

### tripo-cms（后端）
- `HubSpokePages` Collection：17 种 block 类型
- `POST /api/hub-spoke-sync`：Crescendia 数据推送端点（统一 Payload API Key 认证）
- `GET /api/hub-spoke-sitemap-meta`：sitemap 元数据端点
- `src/utilities/media-download.ts`：共享图片下载模块（10s 超时 + 10MB 限制 + p-limit 并发 + sourceUrl 去重）
- 117 个单元测试（含 hub-spoke-sync 65 个）
- 集成测试 10/10 通过
- llmdoc 架构文档 + 对外 API 文档 + Python 客户端
- PR #40 已推送，待合并

### fe-tripo-homepage（前端）
- 渲染层已合入 main（Hub-Spoke 页面路由、17 种组件、SEO、JSON-LD）
- CMS 接入 worktree 已创建：`feature/REQ-recvfwTbU1yXx4-cms-hub-spoke`
- 开发计划 PLAN.md 已写入（Phase 2-6，Phase 1 已砍）

## 待完成的工作

1. ~~CMS PR #40 合并~~ ✅ + 部署到 production（staging 已部署）
2. 三步迁移:
   - Step 1: 单篇推送验证（CMS sync API 端到端）
   - Step 2: 全量推送联调（所有 Crescendia 数据灌入 CMS）
   - Step 3: 前端切换渲染（方案 A 服务端适配层，4 文件改动）
3. Sitemap 集成
4. 端到端联调验证
5. PR 创建 + Code Review + 闭环测试

## 关联资源

- 产品需求池: recvfwTbU1yXx4 (Base: HMvbbjDHOaHyc6sZny6cMRT8n8b, Table: tblb9E9PQHP79JHE)
- 执行中需求: recvfBp9eR8ZGK (Table: tblxLMQ8Ih5Gs5oM)
- CMS Worktree: /Users/macbookair/Desktop/projects/tripo-cms/.worktrees/hub-spoke/
- CMS 分支: feat/hub-spoke-pages
- 前端 Worktree: /Users/macbookair/Desktop/projects/fe-tripo-homepage/.worktrees/feature/REQ-recvfwTbU1yXx4-cms-hub-spoke/
- 前端分支: feature/REQ-recvfwTbU1yXx4-cms-hub-spoke
- Wiki 子目录: KnYcwc6aYi0laPkjpZ4czZYlnqd (https://a9ihi0un9c.feishu.cn/wiki/KnYcwc6aYi0laPkjpZ4czZYlnqd)
- Wiki 文档:
  - Hub-Spoke Sync API 文档: W3qkwBZ29iLK6WklIhfczd7Gn3b (https://a9ihi0un9c.feishu.cn/wiki/W3qkwBZ29iLK6WklIhfczd7Gn3b)
  - 技术方案（前端CMS接入）: IZgwwpVFDi5zcbki0y3cq6Lhnhb (https://a9ihi0un9c.feishu.cn/wiki/IZgwwpVFDi5zcbki0y3cq6Lhnhb)

## 备注

- 2026-04-13: crescendia GEO 技术需求(recveXla9BRDKA)和 geo hub-spoke 产品需求(recvfpjiYVNoYS)已删除，统一归入本需求
