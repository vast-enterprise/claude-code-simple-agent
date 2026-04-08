---
name: tripo-release
description: |
  前端发版流程编排。两种模式：staging 部署（轻量）和 production 发车上线（完整）。
  自身不维护数据，引用 tripo-tables（表格操作）和 tripo-repos（仓库部署信息）。

  触发条件：
  - `/tripo-release`、"部署 staging"、"发 staging"、"上线"、"发版"、"部署生产"
  - "发车"、"跟车"、"hotfix 上线"、"SSS 上线"
  - tripo-requirement 步骤 10 调用
---

# 前端发版

两种模式，根据目标环境选择。

## 模式路由

| 关键词 | 模式 |
|--------|------|
| staging、测试环境、预览 | [deploy-staging.md](references/deploy-staging.md) |
| production、上线、发车、跟车、hotfix、SSS | [deploy-production.md](references/deploy-production.md) |

## 涉及仓库

仓库部署信息（GitHub Action 文件名、域名、K8s Deployment）→ `tripo-repos` skill。

当前可部署的前端仓库：
- **fe-tripo-homepage** — Tripo 官网前端
- **tripo-cms** — CMS 管理后台

## 前置条件

- PR 已合入 main（staging 和 production 都基于 main 分支部署）
- 本地 main 已 pull 到最新

## tag 命名规范

production 发版需要创建 tag：

- 格式：`v{YYYY}.{MM}.{DD}`，如 `v2026.04.08`
- 同一天多次发版：`v2026.04.08.1`、`v2026.04.08.2`
- 创建前先检查是否已存在同名 tag
