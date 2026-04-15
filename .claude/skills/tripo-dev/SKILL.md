---
name: tripo-dev
description: |
  Tripo 项目编码知识：项目特有的编码约定、质量标准、和从真实事故中提炼的教训。
  补充 Claude 已有编码能力中不知道的部分——不教怎么写代码，教在这个项目里怎么写对。

  触发条件（任一命中即触发）：
  - tripo-requirement 步骤 6 显式调用
  - 用户说"写代码"、"开始开发"、"编码"、"实现功能"
  - hotfix、重构、技术预研中涉及编码
  - 任何需要修改代码仓库的场景
---

# Tripo 编码知识

## 进入仓库须知

**先读文档再翻代码**：进入任何代码仓库后，先读 `llmdoc/index.md` + `llmdoc/overview/` 全部文档。llmdoc 包含架构决策和模式约定，直接翻代码会遗漏这些上下文。

**Worktree 中先装依赖**：在 worktree 中执行 `pnpm install` 后再跑 typecheck/lint。worktree 没有 node_modules 时，TypeScript 的类型诊断结果不可信——会报大量"找不到模块"的假错误。

**代码位置与分支**：用 worktree 还是主工作区，取决于要修改的代码是否已合入 main。详见 `tripo-worktree` skill。

## 项目约定

### 新概念要对齐已有模式

在项目中添加新的东西（env var、组件、endpoint、hook、field……）之前，先 grep 3 个已有的同类实现，理解项目的既定模式，然后沿用。

**为什么**：项目中有些抽象层从代码结构上不显眼，但绕过它们会埋坑。

**真实案例**：翻译插件需要 `OPENAI_API_KEY`，直接 `process.env.OPENAI_API_KEY` 读取。但项目所有 env var 都走 Zod schema（`src/constants/env.ts`）+ `.env.example` + `logEnv` 启动日志。绕过 Zod 导致：无类型校验、.env.example 没更新、启动日志不输出这个变量——后续调 401 时排查困难。

**判断标准**：如果你要加的东西在项目里已有 3 个以上同类，必须对齐；如果是全新品类，需要和用户讨论规范。

### UI 组件有隐藏的集成 gap

在 Payload CMS 和 Nuxt 中，写完组件文件 ≠ 组件能在页面上渲染。中间有框架要求的注册步骤，每一步都可能无声失败：

- **Payload**：组件必须在 `collection.admin.components` 中注册 → 路径格式去掉 `src/` 前缀 → `payload generate:importmap` 重新生成
- **Nuxt**：composable/plugin 必须在正确目录 → auto-import 才生效

**真实案例**：翻译插件写了 5 个 `.client.tsx` 文件，在 task 中标记"完成"。但 plugin index.ts 没有把组件注入 admin.components，编辑页上什么也不渲染。直到 UI 验证阶段才暴露。

**判断标准**：写完 UI 组件后，对照已有组件的注册方式检查自己有没有漏步骤——看 3 个同类怎么做的。

### 启动服务前查 tripo-repos

每个仓库有自己的启动注意事项（HTTPS 配置、host 设置、数据库选择等），都记录在 `tripo-repos` skill 中各仓库的 "Dev 启动注意事项" 小节。启动前查一下，不要凭记忆。

**真实案例**：PR 未合入就从主分支启动服务，主分支上没有新功能代码，启动了也验收不了。

## 质量标准

### "完成" = 运行时可用，不是代码存在

| 场景 | 代码态完成（不够） | 运行时完成（要求） |
|------|------------------|------------------|
| API endpoint | 文件存在、typecheck 通过 | curl 返回正确响应 |
| UI 组件 | 文件存在、no lint error | 启动服务 → 页面上能看到 → 截图 |
| 数据处理 | 逻辑写完 | 测试通过 → 贴输出 |

**真实案例**：翻译 UI 组件写了但没注入 admin panel，标记"完成"。代码存在但运行时不可见。

### 证据标准

什么是有效证据、什么不算，详见 `tripo-test` skill §3.2。核心原则：**先贴证据，再下结论**。

### TDD

先测试后实现。详细方法论见 `superpowers:test-driven-development` skill。

### 完成 Checklist

- lint + typecheck 通过
- 测试已编写且通过（→ `superpowers:test-driven-development`）
- 运行时验证有证据（→ `tripo-test` 证据标准）
- 新增概念已对齐同类（命名、位置、注册方式一致）
- 配套文件已更新：新 env var → .env.example + Zod schema + logEnv；新组件 → importMap 重新生成；新 collection → types 包同步
- llmdoc 已同步（如涉及架构/模式/API 变更 → 使用 `tr:recorder` agent）
