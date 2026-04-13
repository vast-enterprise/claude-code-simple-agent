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
| 2026-04-13 | 前端 CMS 接入 | ⏳ 未启动 | worktree 已创建，PLAN.md 已写入，等 CMS 合并后开发 |

## 当前状态

- **阶段**: 步骤 8 闭环完成，等待 PR 合并 + 前端开发
- **状态**: CMS PR 待合并，前端 worktree 已准备
- **下一步**: 合并 CMS PR → 部署 → 前端 CMS 接入开发 → 端到端验证

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

1. CMS PR #40 合并 + 部署到 staging/production
2. fe-tripo-homepage：Phase 2-6（API 切换 + 类型适配 + 组件适配 + Sitemap + 验证）
3. 端到端联调验证

## 关联资源

- 产品需求池: recvfwTbU1yXx4 (Base: HMvbbjDHOaHyc6sZny6cMRT8n8b, Table: tblb9E9PQHP79JHE)
- 执行中需求: recvfBp9eR8ZGK (Table: tblxLMQ8Ih5Gs5oM)
- CMS Worktree: /Users/macbookair/Desktop/projects/tripo-cms/.worktrees/hub-spoke/
- CMS 分支: feat/hub-spoke-pages

## 备注

- 2026-04-13: crescendia GEO 技术需求(recveXla9BRDKA)和 geo hub-spoke 产品需求(recvfpjiYVNoYS)已删除，统一归入本需求
