---
name: tripo-dev
description: |
  Tripo 项目编码层：编码前确认、项目特有约定、质量标准、真实事故教训。
  多个流程（requirement/bugfix/hotfix）的共享编码层——调用方负责流程编排，dev 负责"怎么写对"。

  触发条件（任一命中即触发）：
  - tripo-requirement 步骤 6 / bugfix 步骤 4 显式调用
  - requirement 步骤 8/9、bugfix 步骤 5 验证不通过时的返工调用
  - 用户说"写代码"、"开始开发"、"编码"、"实现功能"
  - hotfix、重构、技术预研中涉及编码

  独立触发时的分流规则：
  - 如果没有需求文档/技术方案/bug 根因报告/验收反馈 → 引导用户走 tripo-requirement 或 tripo-bugfix
  - dev 不是独立入口，是被调用的编码层
---

# Tripo 编码知识

## 编码前确认

编码前确认这几件事。每项都要过，但返工场景（验收/自测不通过回来改）可以快速确认：已存在的 worktree 直接复用、已装的依赖跳过重装、llmdoc 快速扫一遍确认没有变化。

- **目标仓库**：单仓还是多仓？哪些仓库？（→ tripo-repos）
  - 多仓库时：各仓库独立 worktree，按依赖顺序修改（先上游再下游，如先 CMS 再前端）
  - 多仓库时，后续每项确认（worktree、依赖、llmdoc）都要对每个仓库独立执行
- **开发目标**：明确要做什么、做到什么程度
  - 首次开发：需求文档 / 技术方案 → 确认存在
  - 返工修复：验收反馈 / 自测报告 → 确认具体修复点
  - 都没有 → 不开始编码，引导走 tripo-requirement 或 tripo-bugfix
- **Worktree**：是否已在 worktree？需要创建？（→ tripo-worktree）
  - 返工时上一轮 worktree 可能还在，优先复用
- **依赖**：`pnpm install`，确认 typecheck 基线干净（worktree 无 node_modules 时 TS 报错不可信）
- **项目现状**：读 `llmdoc/index.md` + `llmdoc/overview/`，看要改动模块周围的代码怎么组织的。llmdoc 告诉你架构决策，现有代码告诉你落地模式

## 先理解再编码

确认完成后，看要改动的模块周围至少 3 个同类实现，理解现有约定（目录结构、抽象层、注册方式）。跳过理解直接写，大概率会绕过已有抽象、遗漏配套更新、或路径格式不对。

### 启动服务前查 tripo-repos

每个仓库有自己的启动注意事项（HTTPS 配置、host 设置、数据库选择等），记录在 `tripo-repos` skill 各仓库的 "Dev 启动注意事项" 中。启动前查一下，不要凭记忆。

## 质量标准

### "完成" = 运行时可用，不是代码存在

| 场景 | 代码态完成（不够） | 运行时完成（要求） |
|------|------------------|------------------|
| API endpoint | 文件存在、typecheck 通过 | curl 返回正确响应 |
| UI 组件 | 文件存在、no lint error | 启动服务 → 页面上能看到 → 截图 |
| 数据处理 | 逻辑写完 | 测试通过 → 贴输出 |

### 证据标准

什么是有效证据、什么不算，详见 `tripo-test` skill §3.2。核心原则：**先贴证据，再下结论**。

### TDD

先测试后实现。详细方法论见 `superpowers:test-driven-development` skill。

### 文档同步

代码涉及架构变更、新目录结构、新组件模式、API 变更时，使用 `tr:recorder` agent 更新仓库的 llmdoc。llmdoc 是下次会话理解项目的入口——代码改了但文档没跟上，等于给未来的自己挖坑。

### 完成 Checklist

- lint + typecheck 通过
- 测试已编写且通过（→ `superpowers:test-driven-development`）
- 运行时验证有证据（→ `tripo-test` 证据标准）
- 配套文件已更新（添加新概念时，检查同类实现更新了哪些配套文件，一并更新）
- llmdoc 已同步（如涉及架构/模式/API 变更）
