---
name: tripo-repos
description: |
  Tripo 代码仓库注册表。提供所有 Tripo 项目仓库的本地路径、远程地址、技术栈、部署信息和仓库间依赖关系。
  作为其他 skill（clean-worktree、tripo-requirement 等）的数据源，避免硬编码仓库路径。

  触发条件：
  - 需要查询仓库路径、远程地址、技术栈、部署信息
  - 其他 skill 需要获取仓库列表
  - "哪些仓库"、"仓库在哪"、"仓库列表"、"项目结构"
  - 跨仓库操作前的上下文获取
---

# Tripo 代码仓库注册表

## 仓库列表

| 仓库 | 本地路径 | 远程地址 | 技术栈 | 定位 |
|------|---------|---------|--------|------|
| tripo-cms | `/Users/macbookair/Desktop/projects/tripo-cms` | `https://github.com/vast-enterprise/tripo-cms.git` | Payload CMS 3.x + Next.js 15 + MongoDB | Headless CMS 内容管理后台 |
| fe-tripo-homepage | `/Users/macbookair/Desktop/projects/fe-tripo-homepage` | `https://github.com/vast-enterprise/fe-tripo-homepage.git` | Nuxt 4 + Vue 3 + Three.js | Tripo 官网前端 |
| fe-tripo-tools | `/Users/macbookair/Desktop/projects/fe-tripo-tools` | `https://github.com/vast-enterprise/fe-tripo-tools.git` | pnpm monorepo + TypeScript | 通用工具库（auth/design/doc/engine/utils） |

## 仓库关系

```
fe-tripo-homepage (前端) ──API调用──▶ tripo-cms (CMS后台) ──▶ MongoDB
       │
       └──依赖工具包──▶ fe-tripo-tools (auth/design/doc/engine/utils)
```

## tripo-cms

- 管理 Posts（官网博客）和 GeoPosts（百万级 GEO/SEO 文章）
- 类型包 `@tripo3d/cms-types` 发布到 GitHub Packages
- llmdoc 入口：`llmdoc/index.md`

### Dev 启动注意事项

- 分支检查：PR open → 从 worktree 启动；PR merged → 从主工作区启动
- 依赖安装：`pnpm install`（worktree 切换后必须重装）
- 环境变量：确认 `.env` 存在，关键变量（DATABASE_URI、PAYLOAD_SECRET）已配置
- 数据库选择：开发用 `payload-tripo-cms-dev`，生产用 `tripo-cms`（连错库会污染数据）
- 启动命令：`pnpm dev`（默认端口 3000）

| 环境 | 域名 | GitHub Action | K8s Deployment | 镜像 Tag |
|------|------|---------------|----------------|----------|
| staging | `https://cms-staging.itripo3d.com/` | `deploy-staging.yml` | `tripo-cms -n tripo` | `staging-{sha}` |
| production | `https://cms.itripo3d.com/` | `deploy-production.yml` | `tripo-cms -n tripo` | `prod-{sha}` |

- `workflow_dispatch` 手动触发，kubeconfig 区分集群（`ALI_STAGING_KUBECONFIG` / `ALI_PROD_KUBECONFIG`）
- 镜像仓库：阿里云 ACR，部署后飞书通知（`foxundermoon/feishu-action@v2`）

## fe-tripo-homepage

- AI 3D 生成、博客系统、多语言支持（7种语言）
- 混合内容系统（本地 JSON + 阿里云 OSS + Payload CMS）
- llmdoc 入口：`llmdoc/index.md`

### Dev 启动注意事项

- devServer 默认 HTTPS（nuxt.config.ts 配了 cert/key），本地联调需加 `--no-https`
- devServer 默认 host 为 `local.tripo3d.ai`，本地需加 `--host localhost`
- 完整启动命令：`pnpm dev --host localhost --port 3020 --no-https`
- 跨仓库联调时需 `NUXT_CMS_INTERNAL_URL=http://localhost:3000`（指向 CMS）

| 环境 | 域名 | GitHub Action | K8s Deployment | 镜像 Tag |
|------|------|---------------|----------------|----------|
| staging | `https://web-testing.tripo3d.ai` | `staging.yaml` | `tripo-feature-landing -n tripo` | `staging-{sha}` |
| production | `https://www.tripo3d.ai` | `production.yaml` | `tripo-feature-landing -n tripo` | `prod-{sha}` |
| production-pre | — | `production_pre.yaml` | `tripo-feature-landing-pre -n tripo` | — |

- `workflow_dispatch` 手动触发，kubeconfig 区分集群
- CDN：`https://cdn-web.tripo3d.ai`，刷新通过 `cdn-refresh.yml`
- PR 自动代码审查：`ai_code_review.yml`（Claude Code Action → 飞书通知）

## fe-tripo-tools

- pnpm workspace，5 个子包：auth(v0.4.1)、design(v0.5.3)、doc(VitePress)、engine(v0.2.11)、utils(v0.2.6)
- 发布到 GitHub Packages（`@tripo3d` scope），手动 `pnpm build` + `pnpm publish`
- 无 GitHub Actions，本地 husky pre-commit（`pnpm typecheck` + `lint-staged`）
- 构建工具：`tsdown`（auth/engine/utils）、`vite`（design）
- 构建顺序：`utils → auth/design → engine → doc`
- 无 llmdoc

## Agent 工作指南

1. **先读 llmdoc**：进入仓库后先读 `llmdoc/index.md`（如有）
2. **类型同步**：CMS 类型变更需同步发布 `@tripo3d/cms-types`，前端更新依赖
3. **工具库修改**：修改 fe-tripo-tools 后需发布新版本，下游项目更新依赖
4. **跨仓库联调**：各仓库需独立 worktree
