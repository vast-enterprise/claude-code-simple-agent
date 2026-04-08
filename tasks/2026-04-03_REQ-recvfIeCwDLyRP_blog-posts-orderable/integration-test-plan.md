# 集成测试计划 — Blog 列表排序可控

## 测试环境

| 环境 | 说明 |
|------|------|
| CMS | tripo-cms dev (本地 localhost:3000) |
| 前端 | fe-tripo-homepage dev (本地 localhost:3020) |
| 数据库 | payload-tripo-cms-dev（开发数据库） |

## 前置条件

1. CMS 服务已启动（`pnpm dev`）
2. 前端服务已启动（`pnpm dev`）
3. 数据库中有至少 2 篇 published 状态的 posts 文章
4. `blogLegacy=false`（Feature Flag 开启 CMS 模式）

## 测试场景

### 场景 1：CMS pinned 字段保存

| 项目 | 说明 |
|------|------|
| 组件 | CMS 后台 /admin/collections/posts |
| 操作 | 编辑某篇 post，勾选 pinned 复选框，保存 |
| 预期结果 | 再次打开文章，pinned 值仍为 true |

### 场景 2：CMS 拖拽排序

| 项目 | 说明 |
|------|------|
| 组件 | CMS 后台 /admin/collections/posts |
| 操作 | 在 posts 列表页拖拽 A 文章到 B 文章之前 |
| 预期结果 | 刷新页面后，A 排在 B 之前 |

### 场景 3：API 排序验证

| 项目 | 说明 |
|------|------|
| 接口 | GET /api/blog/posts |
| 操作 | 启动前端服务，curl 请求 API |
| 预期结果 | pinned=true 的文章在 pinned=false 之前 |

### 场景 4：前端置顶标识

| 项目 | 说明 |
|------|------|
| 页面 | /blog |
| 操作 | 访问 blog 列表页 |
| 预期结果 | pinned=true 的文章显示红色 "Pinned" 标签 |
