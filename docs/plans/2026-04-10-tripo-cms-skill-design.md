# tripo-cms Skill 设计文档

> 日期：2026-04-10
> 状态：待实施

## 1. 定位

为 Tripo 工作调度中枢提供 CMS 内容管理系统的统一操作入口。覆盖内容运营（查询/发布/批量操作文章）和开发联调（测试 API/创建测试数据/验证功能）两大场景。

**不做什么**：
- 不写脚本 — CMS 会随时变化，脚本维护成本高且不在同一仓库
- 不复制数据模型 — 从 CMS 仓库 llmdoc + 代码实时获取
- 不替代 tripo-release — 部署由 tripo-release 负责

## 2. 设计原则

1. **先理解后操作** — 每次操作前必须先读 CMS llmdoc + 相关代码，建立准确的数据模型认知
2. **双保险验证** — llmdoc 可能滞后，必须读代码验证准确性
3. **tripo-repos 驱动** — 仓库路径、环境 URL 从 tripo-repos 获取，不硬编码
4. **按需加载** — cookbook 按操作类型拆分，避免一次性塞满上下文
5. **安全第一** — 生产环境写操作需确认，批量操作需 dry-run

## 3. Skill 结构

```
tripo-cms/
├── SKILL.md                          # 核心指南（操作流程 + 分类路由）
└── references/
    ├── api-authentication.md          # API Key 认证 + 环境配置
    ├── cookbook-content.md             # 内容操作（Posts/GeoPosts/Pages CRUD + 批量）
    ├── cookbook-media.md               # 媒体操作（上传/查询/文件夹管理）
    ├── cookbook-system.md              # 系统操作（回填/迁移/分类/Feature Flag）
    └── payload-api-patterns.md        # Payload REST API 通用模式（查询语法/分页/过滤/排序）
```

## 4. 核心操作流程

```
任何 CMS 操作:
  1. 加载 tripo-repos skill → 获取 CMS 仓库路径 + 环境 URL
  2. 读 CMS llmdoc（至少 index.md + 相关架构文档）→ 建立整体理解
  3. 读相关代码文件（collections/fields/endpoints）→ 验证 llmdoc + 补充最新变更
  4. 确定目标环境（dev/staging/production）→ 加载对应 API Key
  5. 根据操作类型加载对应 cookbook
  6. 执行操作
  7. 验证结果
```

操作三大类：

| 类型 | 触发场景 | Cookbook |
|------|----------|---------|
| 内容操作 | 查询/创建/更新/发布/批量文章、页面管理 | cookbook-content.md |
| 媒体操作 | 上传图片、查询媒体、管理文件夹 | cookbook-media.md |
| 系统操作 | 数据回填、Posts↔GeoPosts 迁移、分类管理、Feature Flag | cookbook-system.md |

## 5. 认证与环境

### API Key 认证

在 CMS 中创建 skill 专用账户，生成 API Key，skill 中记录：

| 环境 | Base URL | API Key | 说明 |
|------|----------|---------|------|
| development | `http://localhost:3000` | （待填入） | 本地开发 |
| staging | `https://cms-staging.itripo3d.com` | （待填入） | 测试验证 |
| production | `https://cms.itripo3d.com` | （待填入） | 线上操作 |

请求头格式：`Authorization: users API-Key <key>`

### 安全约束

- 生产环境写操作（create/update/delete）→ 提议 + 用户确认后再执行
- 批量操作（影响 >10 条记录）→ 先 dry-run 展示影响范围
- 删除操作 → 任何环境都需确认

## 6. Payload API 通用模式

这部分是 Payload 框架层面的知识，CMS llmdoc 不覆盖，放在 skill 的 `payload-api-patterns.md` 中：

- `where` 查询操作符（equals, not_equals, like, contains, in, exists, greater_than, less_than 等）
- `depth` 关联展开控制
- `locale` / `fallback-locale` 多语言查询
- `sort` 排序（`-createdAt` 降序）
- `limit` / `page` 分页
- `select` / `populate` 字段选择
- 批量操作端点（`/api/<collection>?where[field][operator]=value` + PATCH/DELETE）

## 7. 与现有 Skills 关系

```
tripo-repos  ──提供仓库路径/环境URL──→  tripo-cms（本 skill）
CMS llmdoc   ──提供数据模型──→          tripo-cms（本 skill）
CMS 代码     ──验证/补充模型──→         tripo-cms（本 skill）

tripo-requirement ──可选调用──→ tripo-cms（开发联调/验收阶段）
```

## 8. 典型使用场景

1. **「查询 AI 分类下所有已发布文章」** → 内容操作 → cookbook-content.md
2. **「为这 5 篇文章添加 tutorial 分类」** → 内容操作 → cookbook-content.md
3. **「批量上传 20 篇 markdown 文章到 GeoPosts」** → 内容操作 → cookbook-content.md
4. **「上传一张图片到媒体库」** → 媒体操作 → cookbook-media.md
5. **「把这篇 Post 迁移到 GeoPost」** → 系统操作 → cookbook-system.md
6. **「切换 blogLegacy feature flag」** → 系统操作 → cookbook-system.md
7. **「开发了新字段，帮我创建测试数据验证」** → 开发联调 → 先读代码理解新字段 → cookbook-content.md
