# Production 发车上线

完整模式，关联已有班车，创建 release，部署，验证，勾 checkbox，通知。

## 前置条件

- PR 已合入 main
- 需求已准出、已搭上班车（由 tripo-requirement 步骤 10 或用户手动完成）
- 发车中需求记录已存在

## 步骤

### 1. 确认班车

查询当前要关联的 Sprint 版本（→ tripo-tables，查询 Sprint 版本计划表，班车状态=已启动）。

确认发车类型：
- **跟车**：搭已有的每周班车
- **SSS**：临时创建的紧急版本
- **hotfix**：Bug 修复版本

### 2. 创建 release/tag

```bash
# 检查是否已存在同名 tag
git tag -l "v$(date +%Y.%m.%d)*"

# 创建 tag（基于 main 最新 commit）
git tag v<YYYY.MM.DD>
git push origin v<YYYY.MM.DD>

# 创建 GitHub Release（从合并的 PR 中提取变更）
gh release create v<YYYY.MM.DD> \
  --repo <org/repo> \
  --title "v<YYYY.MM.DD>" \
  --generate-notes
```

跟车模式下，release/tag 是版本级别的（一个 Sprint 一个），如果已有则跳过此步。
SSS 和 hotfix 每次独立创建。

### 3. 触发部署

从 `tripo-repos` skill 获取 production GitHub Action 文件名：

```bash
gh workflow run <production-workflow> --repo <org/repo> --ref main
```

等待完成：

```bash
gh run list --repo <org/repo> --workflow <production-workflow> --limit 1
gh run watch <run-id> --repo <org/repo>
```

### 4. 验证

从 `tripo-repos` skill 获取 production 域名：

```bash
curl -sL -o /dev/null -w "%{http_code}" <production-url>
```

验证要点：
- HTTP 200
- 关键页面/API 可访问
- 如有 CDN，确认 CDN 域名也已更新（fe-tripo-homepage 有 `cdn-refresh.yml`）

### 5. 勾前端部署 checkbox

更新 Sprint 版本计划的前端部署完毕字段（→ tripo-tables，checkbox 字段 ID 见 release-flow.md）：

```bash
lark-cli base +record-update \
  --base-token <base-token> \
  --table-id <sprint-table-id> \
  --record-id <sprint-record-id> \
  --json '{"fields": {"前端部署完毕": true}}'
```

### 6. 通知

通知相关人员前端已部署完毕（→ tripo-tables，notification.md）：

```bash
lark-cli im +messages-send --as bot \
  --user-id <open-id> \
  --text '[前端部署完毕] <仓库名> 已部署到 production\n版本: v<YYYY.MM.DD>\n域名: <production-url>'
```
