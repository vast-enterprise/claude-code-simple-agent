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

两种模式，根据目标环境选择。部署信息从 `tripo-repos` skill 获取。

## 模式路由

| 关键词 | 模式 | 步骤数 |
|--------|------|--------|
| staging、测试环境、预览 | Staging 部署 | 4 步 |
| production、上线、发车、跟车、hotfix、SSS | Production 发车 | 6 步 |

## 涉及仓库

| 仓库 | staging workflow | production workflow |
|------|-----------------|---------------------|
| fe-tripo-homepage | `staging.yaml` | `production.yaml` |
| tripo-cms | `deploy-staging.yml` | `deploy-production.yml` |

## 共同前置条件

- [ ] PR 已合入 main
- [ ] 本地 main 已 pull 到最新（`git pull origin main`）
- [ ] 确认目标仓库（AskUserQuestion 如用户未明确指定）

---

## Staging 部署（轻量）

完整命令详见 [deploy-staging.md](references/deploy-staging.md)

| 步骤 | 动作 | 确认点 |
|------|------|--------|
| 1 | `gh workflow run <staging-workflow> --repo <org/repo> --ref main` | — |
| 2 | `gh run watch <run-id>` 等待完成 | 部署失败 → 查 Action 日志 |
| 3 | `curl -sL -w "%{http_code}" <staging-url>` 验证 HTTP 200 | 非 200 → 检查 K8s pod 状态 |
| 4 | 通知相关人（可选，`--as bot`） | — |

## Production 发车（完整）

完整命令详见 [deploy-production.md](references/deploy-production.md)

| 步骤 | 动作 | 确认点 |
|------|------|--------|
| 1 | 确认班车类型（跟车/SSS/hotfix）和 Sprint 记录 | **⏸ AskUserQuestion 确认** |
| 2 | 创建 tag + GitHub Release | tag 已存在 → 跳过或追加后缀 |
| 3 | `gh workflow run <prod-workflow>` 触发部署 | — |
| 4 | `gh run watch` + `curl` 验证 production | 部署失败 → 查 Action 日志，**不要继续** |
| 5 | 勾 Sprint 版本计划的前端部署 checkbox | → tripo-tables release-flow.md |
| 6 | 飞书通知部署完毕（`--as bot`） | — |

### tag 命名规范

- 格式：`v{YYYY}.{MM}.{DD}`，如 `v2026.04.08`
- 同一天多次：`v2026.04.08.1`、`v2026.04.08.2`
- 创建前先 `git tag -l "v$(date +%Y.%m.%d)*"` 检查

## 异常处理

| 场景 | 处理 |
|------|------|
| GitHub Action 超时/失败 | 查 Action 日志 → 修复 → 重新触发，不要盲目重试 |
| 部署后验证失败（非 200） | 检查 K8s pod 状态 → 查 pod 日志 → 必要时 rollback deployment |
| CDN 未更新（fe-tripo-homepage） | 触发 `cdn-refresh.yml` workflow |
| tag 已存在 | 追加后缀 `.1`、`.2`，或确认是否复用现有 tag |
