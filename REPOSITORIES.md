# Tripo 代码仓库

> 本文档记录 Tripo 业务线维护的核心代码仓库信息。

## 仓库列表

| 仓库 | 本地路径 | 远程地址 | 技术栈 | 定位 |
|------|---------|---------|--------|------|
| tripo-cms | `/Users/macbookair/Desktop/projects/tripo-cms` | `https://github.com/vast-enterprise/tripo-cms.git` | Payload CMS 3.x + Next.js 15 + MongoDB | Headless CMS 内容管理后台 |
| fe-tripo-homepage | `/Users/macbookair/Desktop/projects/fe-tripo-homepage` | `https://github.com/vast-enterprise/fe-tripo-homepage.git` | Nuxt 4 + Vue 3 + Three.js | Tripo 官网前端 |
| fe-tripo-tools | `/Users/macbookair/Desktop/projects/fe-tripo-tools` | `https://github.com/vast-enterprise/fe-tripo-tools.git` | pnpm monorepo + TypeScript | 通用工具库（auth/design/doc/engine/utils） |

## 仓库关系

```
┌─────────────────────────────────────────────────────────────────┐
│                    Tripo 技术架构                                │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   fe-tripo-homepage (前端)                                       │
│        │                                                         │
│        │  API 调用        │ 依赖工具包                           │
│        ▼                  ▼                                      │
│   tripo-cms (CMS后台)    fe-tripo-tools (工具库)                 │
│        │                  ├── auth (认证)                        │
│        │                  ├── design (设计)                      │
│        │                  ├── doc (文档)                         │
│        │                  ├── engine (引擎)                      │
│        │                  └── utils (工具)                       │
│        │                                                         │
│        │  数据存储                                               │
│        ▼                                                         │
│   MongoDB                                                        │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## tripo-cms 详情

- **定位**: Tripo 官网的 Headless CMS 内容管理后台
- **功能**: 管理 Posts（官网博客）和 GeoPosts（百万级 GEO/SEO 文章）
- **类型包**: `@tripo3d/cms-types` 发布到 GitHub Packages
- **部署**: Docker + Kubernetes，三环境（dev/staging/prod）
- **llmdoc**: 完整文档系统，入口 `/Users/macbookair/Desktop/projects/tripo-cms/llmdoc/index.md`

## fe-tripo-homepage 详情

- **定位**: Tripo 官网前端
- **功能**: AI 3D 生成、博客系统、多语言支持（7种语言）
- **架构**: 混合内容系统（本地 JSON + 阿里云 OSS + Payload CMS）
- **部署**: Docker + Kubernetes（阿里云）
- **llmdoc**: 完整文档系统，入口 `/Users/macbookair/Desktop/projects/fe-tripo-homepage/llmdoc/index.md`

## fe-tripo-tools 详情

- **定位**: Tripo 通用工具库 monorepo
- **架构**: pnpm workspace，包含 5 个子包
  - `auth` - 认证相关
  - `design` - 设计相关
  - `doc` - 文档
  - `engine` - 引擎
  - `utils` - 工具函数
- **发布**: 发布到 npm/GitHub Packages，供其他项目依赖

## Agent 工作指南

当 Agent 需要在这些仓库工作时：

1. **先读 llmdoc**: 进入仓库后，先读取 `llmdoc/index.md` 了解项目（如有）
2. **理解关系**:
   - 前端调用 CMS API，CMS 提供内容数据
   - 前端依赖工具库（fe-tripo-tools）
3. **类型同步**: CMS 类型变更需同步发布 `@tripo3d/cms-types`，前端更新依赖
4. **工具库修改**: 修改 fe-tripo-tools 后需发布新版本，下游项目更新依赖