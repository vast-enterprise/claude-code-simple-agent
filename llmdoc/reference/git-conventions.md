# Git 约定规范

本文档提供 tripo-work-center 仓库的 Git 使用约定摘要与源信息指引。

## 1. 核心摘要

本仓库采用 Conventional Commits 风格的提交前缀，单主干分支 `main` 开发，按需创建 `feat/` 特性分支。提交信息使用英文，简洁描述变更意图，允许用破折号补充上下文。

## 2. Commit Message 格式

**前缀类型（按使用频率排序）：**

| 前缀 | 用途 | 示例 |
|------|------|------|
| `feat` | 新功能 | `feat: create digital avatar MVP — feishu bot powered by Claude Code SDK` |
| `fix` | 缺陷修复 | `fix: prevent orphan processes on avatar exit` |
| `refactor` | 重构（不改变行为） | `refactor: split single-file avatar into modular src/ structure` |
| `docs` | 文档变更 | `docs: add task tracking for JSON-LD and blog-posts-orderable requirements` |
| `test` | 测试相关 | `test: add unit tests for avatar (25 cases)` |
| `chore` | 杂务（归档、清理） | `chore: archive completed tasks to tasks-finished/` |

**格式规则：**

- 模式：`<type>: <简短描述>`
- 可用破折号 `—` 追加上下文说明
- 全英文，首字母小写，无句号结尾
- 无 scope 括号（不使用 `feat(auth):` 形式）

## 3. 分支策略

- 主干分支：`main`
- 特性分支命名：`feat/<功能描述>`（如 `feat/blog-push-api`）
- 开发闭环以 PR 提出为终点，Agent 禁止 merge

## 4. .gitignore 规则

当前忽略项：`.playwright-cli`、`config.json`、`__pycache__`、`tmp`、`.pytest_cache`

## 5. 信息源

- **提交历史：** `git log --oneline -20`
- **分支列表：** `git branch -a`
- **忽略规则：** `.gitignore`
- **行为约束：** `/Users/macbookair/Desktop/projects/tripo-work-center/CLAUDE.md`（Agent 职责边界 → PR 提交规则）
