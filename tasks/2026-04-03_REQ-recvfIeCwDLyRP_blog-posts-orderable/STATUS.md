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
