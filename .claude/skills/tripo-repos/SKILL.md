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
| fe-tripo-studio | `/Users/macbookair/Desktop/projects/fe-tripo-studio` | `https://github.com/vast-enterprise/fe-tripo-studio.git` | Nuxt 4 + Vue 3 + Three.js + @tripo3d/engine | Tripo Studio 3D 模型生成与编辑平台 |
| fe-tripo-tools | `/Users/macbookair/Desktop/projects/fe-tripo-tools` | `https://github.com/vast-enterprise/fe-tripo-tools.git` | pnpm monorepo + TypeScript | 通用工具库（auth/design/doc/engine/utils） |

## 仓库关系

```
fe-tripo-homepage (官网) ──API调用──▶ tripo-cms (CMS后台) ──▶ MongoDB
       │
       └──依赖工具包──▶ fe-tripo-tools (auth/design/doc/engine/utils)
                              ▲
fe-tripo-studio (Studio) ─────┘ 依赖 auth/design/engine/utils
```

## 认证操作规范（适用所有仓库）

登录失败 / 凭证不对 / 权限不足时的标准动作：

1. 停下，不做任何"绕过"尝试
2. 向调用方报告：HTTP 状态 + 错误消息原文 + 所用账户 email（不贴密码 / token）
3. 查下面各仓"认证与凭证"段拿合法凭证；信息不够则 AskUserQuestion
4. 获得用户授权或合法凭证后再继续

反模式（遇到即停下自查）：

- 直接写数据库身份字段让自己"能登"
- 伪造 token / cookie / API Key 绕过鉴权
- 跨仓 `.env` 凑凭证、字典猜、git log 翻旧密码

绕过会连锁——今天绕 localhost、明天绕 staging。合法通道写在各仓"认证与凭证"段；那里没写的是需要用户补齐的前置条件。

## tripo-cms

- 管理 Posts（官网博客）和 GeoPosts（百万级 GEO/SEO 文章）
- 类型包 `@tripo3d/cms-types` 发布到 GitHub Packages
- llmdoc 入口：`llmdoc/index.md`

### Dev 启动注意事项

- 分支检查：PR open → 从 worktree 启动；PR merged → 从主工作区启动
- 依赖安装：`pnpm install`（worktree 切换后必须重装）
- 环境变量：确认 `.env` 存在，关键变量（DATABASE_URI、PAYLOAD_SECRET）已配置
- 启动命令：`pnpm dev`（默认端口 3000）

| 环境 | 域名 | GitHub Action | K8s Deployment | 镜像 Tag |
|------|------|---------------|----------------|----------|
| staging | `https://cms-staging.itripo3d.com/` | `deploy-staging.yml` | `tripo-cms -n tripo` | `staging-{sha}` |
| production | `https://cms.itripo3d.com/` | `deploy-production.yml` | `tripo-cms -n tripo` | `prod-{sha}` |

- `workflow_dispatch` 手动触发，kubeconfig 区分集群（`ALI_STAGING_KUBECONFIG` / `ALI_PROD_KUBECONFIG`）
- 镜像仓库：阿里云 ACR，部署后飞书通知（`foxundermoon/feishu-action@v2`）

### 认证与凭证

#### 认证机制

**API 请求（自动化 / skill 调用）**
- Payload CMS 内置 API Key（`Users.auth.useAPIKey: true`）
- 请求头：`Authorization: users API-Key <key>`
- 共享账户：`aibot@tripo3d.ai`（admin，staging + production）

**Playwright UI 测试（交互式登录）**
- 走 `/api/users/login` 完整流程，需明文 email + password
- 测试专属账户（不借用 aibot、不借用真实业务用户）
- production 不提供常驻 email / password；如需 UI 测试必须用户**单次明示授权**

#### 凭证变量（仓库根 `.env`，已 gitignore）

| 环境 | Base URL | API Key | Playwright Email | Playwright Password |
|------|----------|---------|------------------|---------------------|
| development | `http://localhost:3000` | `CMS_DEV_API_KEY` | `CMS_DEV_EMAIL` | `CMS_DEV_PASSWORD` |
| staging | `https://cms-staging.itripo3d.com` | `CMS_STAGING_API_KEY` | `CMS_STAGING_EMAIL` | `CMS_STAGING_PASSWORD` |
| production | `https://cms.itripo3d.com` | `CMS_PROD_API_KEY` | — | — |

> development 环境的 `CMS_DEV_*` 变量由开发者自行注册本地 admin 账户后填入 `.env`；**不从其它仓库 `.env` 复制**（email 重合 ≠ 同一份口令）。

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

## fe-tripo-studio

- Web 3D 模型生成与编辑平台（图/文生模型、纹理、绑骨、分割、重拓扑、导出）
- 依赖 `@tripo3d/auth`、`@tripo3d/design`、`@tripo3d/engine`、`@tripo3d/utils`
- llmdoc 入口：`llmdoc/index.md`

### Dev 启动注意事项

- devServer 默认 HTTPS + `host: local.tripo3d.ai` + 端口 8000（同 homepage 的坑）
- 本地联调需加 `--host localhost --no-https`
- 完整启动命令：`pnpm dev --host localhost --port 8000 --no-https`
- 依赖安装：`pnpm install`（需 Node.js >= 22.0.0）
- 环境变量：`.env.development`（开发）、`.env.staging`、`.env.production`

### 国际版（.tripo3d.ai）

| 环境 | 域名 | GitHub Action | K8s Deployment | 分支 |
|------|------|---------------|----------------|------|
| staging | `https://web-testing.tripo3d.ai` | `staging.yml` | `studio -n tripo`（阿里云） | main |
| production | `https://studio.tripo3d.ai` | `production.yml` | AWS: `studio-frontend -n production` + 阿里云: `studio -n tripo` | main |

- production 双集群部署（AWS ECR + 阿里云 ACR），matrix 策略并行构建推送
- `workflow_dispatch` 手动触发
- Makefile 快捷构建：`make staging` / `make production`

### 中国版（.tripo3d.com）— 独立维护

> CN 版与国际版有明显差异，可视为独立产品线。CN production 使用独立分支 `main_cn`。

| 环境 | 域名 | GitHub Action | K8s Deployment | 分支 |
|------|------|---------------|----------------|------|
| CN staging | `https://studio-test.tripo3d.com` | `cn_staging.yml` | CN 集群 | main |
| CN production | `https://studio.tripo3d.com` | `cn_production.yml` | CN 集群 | main_cn |

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
