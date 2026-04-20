# REQ: Blog 列表排序可控（置顶 + 拖拽排序）

## 基本信息

| 字段 | 值 |
|------|-----|
| 需求ID | recvfIeCwDLyRP |
| 需求类型 | 产品需求 |
| 需求Owner | 郭凯南 |
| 研发Owner | 郭凯南 |
| 提出日期 | 2026-04-03 |
| 当前状态 | 未启动 |
| 涉及仓库 | tripo-cms, fe-tripo-homepage |

## 需求描述

在 CMS 后台为 posts 数据新增 pinned 字段和启用 orderable，让管理员能控制 blog 在前端展示的顺序。置顶文章在前端有特殊标识。

## 设计方案

1. CMS 端：posts collection 新增 `pinned: checkbox` 字段（默认 false），启用 `orderable: true`（Payload 原生 fractional indexing）
2. 前端：修改 blog 列表 API 排序逻辑为 `[-pinned, -_order, -publishedAt]`，列表组件根据 `pinned: true` 渲染置顶标识
3. 数据影响：pinned 新增字段已有文章默认 false 无需迁移，`_order` 由 Payload 自动维护

## 状态记录

### 2026-04-03 步骤 1: 接收需求
- 创建任务目录
- 需求来源：用户口头描述
- 需求尚未录入需求池

### 2026-04-03 步骤 2: 归类与录入
- 需求类型：产品需求
- 已录入产品需求池，record_id: recvfIeCwDLyRP
- 绝对优先级：L3
- 需求状态：未启动

### 2026-04-03 步骤 3: 需求评审
- 已输出 review.md
- 合规风险审查：无风险
- 评审结论：通过，建议定容
- 提议状态变更：未启动 → 定容确认

### 2026-04-03 步骤 4: 进入执行表
- 执行表记录已创建：recvfIfRCTlLP1
- 需求池状态已更新：开发/交付中
- 执行表状态：评审中

### 2026-04-03 步骤 5: 技术评审
- 已输出 technical-solution.md
- 推荐方案：pinned checkbox + Payload orderable
- 预计工作量：1 小时内完成编码
- 执行表技术评审字段：未启动 → 提议"完成"

### 2026-04-03 步骤 6: 编码开发
- tripo-cms worktree: feature/REQ-recvfIeCwDLyRP-blog-posts-orderable
- fe-tripo-homepage worktree: feature/REQ-recvfIeCwDLyRP-blog-posts-orderable
- CMS: post-shared.ts 新增 pinnedField, posts 启用 orderable
- 前端: posts.get.ts 排序改为 [-pinned, -_order, -publishedAt]
- 前端: blog-category-tabs.vue 添加 pinned 标识
- typecheck: 通过（前端 0 TS 错误，CMS tsc 通过）

### 2026-04-03 步骤 7: 创建 PR
- CMS PR: https://github.com/vast-enterprise/tripo-cms/pull/38
- 前端 PR: https://github.com/vast-enterprise/fe-tripo-homepage/pull/182

### 2026-04-15~16 步骤 8: 自动化闭环
- 8.1 Code Review: 两个仓库已审查
- 8.2 测试计划: integration-test-plan.md 已输出
- 8.3 集成测试: 3/4 PASS, 1 DEFERRED
- 8.4 验证报告: integration-test-report.md 已输出
- 验收阶段额外发现并修复:
  - CMS pinned-cell/pinned-order-cell 组件 PATCH 导致草稿文章状态异常 → 改用 ?draft=true
  - 前端置顶标识从 category 混排改为标题左侧 inline badge（品牌黄 #f9cf00 + i18n）
  - 回退预览模式草稿查询（影响 BlogFeaturedPost relationship 展开）
- 8.5 飞书通知: 已发送 (om_x100b513331d5c900c389538a04104d6)
- 等待用户验收

### 2026-04-16 步骤 9: 用户验收
- CMS PR #38: 已合并
- 前端 PR #182: 已合并（rebase 解决冲突，修复 i18n 文件丢失 login 等 key）
- 主工作区已同步: tripo-cms main, fe-tripo-homepage main
- Staging 部署:
  - CMS staging: https://cms-staging.itripo3d.com/ (HTTP 200)
  - 前端 staging: https://web-testing.tripo3d.ai/blog (HTTP 200)
- 表格状态: 执行表"完成"，需求池"验收/提测中"
- Wiki 子目录: Jc43wGs0Sif1I2kSFAfcTlYwnQc (https://a9ihi0un9c.feishu.cn/wiki/Jc43wGs0Sif1I2kSFAfcTlYwnQc)
  - 使用指南: JP4Cws9QhimGzpku2hic33CXnDd (https://a9ihi0un9c.feishu.cn/wiki/JP4Cws9QhimGzpku2hic33CXnDd)
- 等待 staging 验收通过后进入步骤 10
