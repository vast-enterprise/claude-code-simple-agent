# API 认证与环境配置

## 环境列表

| 环境 | Base URL | 用途 |
|------|----------|------|
| development | `http://localhost:3000` | 本地开发调试 |
| staging | `https://cms-staging.itripo3d.com` | 测试验证 |
| production | `https://cms.itripo3d.com` | 线上操作 |

> 环境 URL 也可从 tripo-repos skill 获取（部署信息表），以 tripo-repos 为准。

## API Key 认证

CMS 使用 Payload CMS 内置的 API Key 机制（`Users.auth.useAPIKey: true`）。

### 请求头格式

```
Authorization: users API-Key <your-api-key>
```

### Skill 专用账户

| 环境 | 邮箱 | 角色 |
|------|------|------|
| staging | `aibot@tripo3d.ai` | editor |
| production | `aibot@tripo3d.ai` | editor |

### API Key 配置

API Key 存储在项目根目录的 `.env` 文件中（已 gitignore）：

```bash
CMS_STAGING_API_KEY="<staging-key>"
CMS_PROD_API_KEY="<prod-key>"
```

使用前加载：`source .env`

### 使用示例

```bash
# 查询 staging 环境的文章
curl -H "Authorization: users API-Key $CMS_STAGING_API_KEY" \
  "https://cms-staging.itripo3d.com/api/posts?limit=5"
```

## 安全规则

| 规则 | 说明 |
|------|------|
| 生产写操作需确认 | production 的 POST/PATCH/DELETE 必须先展示操作内容，用户确认后执行 |
| 批量操作需 dry-run | 影响 >10 条记录时，先用 GET 查询展示将被影响的记录 |
| 删除需确认 | 任何环境的 DELETE 操作都需用户确认 |
| 不暴露 Key | API Key 只从环境变量读取，不硬编码在命令中 |

