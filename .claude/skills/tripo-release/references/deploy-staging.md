# Staging 部署

轻量模式，不涉及发车流程。

## 前置条件

- PR 已合入 main
- 本地 main 已 pull 到最新

## 步骤

### 1. 确认仓库和 workflow

从 `tripo-repos` skill 获取目标仓库的 staging GitHub Action 文件名。

### 2. 触发部署

```bash
gh workflow run <staging-workflow> --repo <org/repo> --ref main
```

### 3. 等待部署完成

```bash
# 查看最近一次 run
gh run list --repo <org/repo> --workflow <staging-workflow> --limit 1
# 等待完成
gh run watch <run-id> --repo <org/repo>
```

### 4. 验证

从 `tripo-repos` skill 获取 staging 域名，验证服务可用：

```bash
curl -sL -o /dev/null -w "%{http_code}" <staging-url>
```

验证要点：
- HTTP 200
- 如有特定页面或 API，额外验证关键路径

### 5. 通知（可选）

如果是协作场景，通知相关人员 staging 已部署：

```bash
lark-cli im +messages-send --as bot \
  --user-id <open-id> \
  --text '[Staging 已部署] <仓库名> main 分支已部署到 staging 环境'
```
