---
name: tripo-cms
description: |
  CMS 内容管理系统全操作：内容 CRUD（Posts/GeoPosts/Pages）、媒体管理、分类管理、
  数据回填、Posts-GeoPosts 迁移、Feature Flag 配置、批量操作。
  通过 Payload REST API 操作 CMS 数据，不依赖脚本，纯 API 知识库。

  触发条件：
  - "查询文章"、"创建文章"、"发布文章"、"批量更新"、"上传图片"
  - "CMS 操作"、"管理分类"、"feature flag"、"数据回填"
  - "迁移文章"、"Post 转 GeoPost"、"导入文章"
  - 需要查询/修改 CMS 中的 Posts、GeoPosts、Pages、Categories、Media 数据
  - tripo-requirement 步骤 6（数据类需求开发）、步骤 8（自测）或步骤 9（验收）中需要操作/验证 CMS 数据
---

# Tripo CMS 操作

## 操作铁律

1. **先理解后操作** — 任何 CMS 操作前，必须先了解当前数据模型
2. **双保险验证** — llmdoc 可能滞后，必须读代码验证准确性
3. **生产写操作需确认** — production 环境的 create/update/delete 必须提议 + 用户确认
4. **批量操作需 dry-run** — 影响 >10 条记录时，先查询展示影响范围

## 操作流程

```
任何 CMS 操作:
  1. 加载 tripo-repos skill → 获取 CMS 仓库路径 + 环境 URL
  2. 读 CMS llmdoc/index.md + 相关架构文档 → 建立整体理解
  3. 读相关代码文件（src/collections/ src/fields/ src/endpoints/）→ 验证 + 补充
  4. 确定目标环境 → 加载对应 API 凭证（见 api-authentication.md）
  5. 读 gotchas.md → 避免已知踩坑
  6. 组装 API 请求并执行
  7. 验证结果（查询确认变更生效）
```

## References

| 文件 | 内容 | 何时读 |
|------|------|--------|
| [api-authentication.md](references/api-authentication.md) | 环境 URL、API Key 格式、安全规则 | 首次操作时 |
| [gotchas.md](references/gotchas.md) | 不读代码容易搞错的非直觉行为 | 每次操作前 |

## Collection / Global 速查

| Collection | Slug | 公开读取 |
|------------|------|---------|
| Posts | `posts` | 仅已发布 |
| GeoPosts | `geo-posts` | 仅已发布 |
| Pages | `pages` | 仅已发布 |
| Categories | `categories` | 是 |
| Media | `media` | 是 |
| Users | `users` | 否 |
| BackfillLogs | `backfill-logs` | 否（admin） |

| Global | Slug |
|--------|------|
| AppConfig | `app-config` |
| DataBackfill | `data-backfill` |

## 自定义 Endpoints

| 路径 | 方法 | 权限 | 说明 |
|------|------|------|------|
| `/api/blog-import` | POST | 需认证 | 批量导入 GeoPosts（最多 50 篇/次） |
| `/api/migrate-post` | POST | admin+ | Posts - GeoPosts 双向迁移 |
| `/api/geo-posts-months` | GET | 公开 | GeoPosts 月份分布统计 |
| `/api/data-backfill/execute` | POST | admin+ | 执行数据回填 |
| `/api/data-backfill/rollback` | POST | admin+ | 回滚数据回填 |

## 与 tripo-requirement 的接口

- **步骤 6（开发）**：数据类需求（如批量导入、字段迁移、数据清洗），加载本 skill 在 CMS 上执行数据操作
- **步骤 8（自测）**：通过 API 查询验证 CMS 数据变更是否生效
- **步骤 9（验收）**：通过 API 查询确认线上数据状态符合需求预期
