---
name: tripo-worktree
description: |
  Git worktree 全生命周期管理：创建、命名规范、使用纪律、扫描、清理。
  被 tripo-requirement 等流程 skill 调用，也可独立触发清理。

  触发条件：
  - 创建 worktree、清理 worktree、worktree 太多了
  - "磁盘空间不够"、"清理临时分支"
  - 需求完成后的收尾清理
---

# Worktree 管理

仓库路径从 `tripo-repos` skill 获取，不硬编码。

## 创建

命名规范：

```
feature/REQ-recXxx-ascii-desc
bugfix/BUG-recYyy-ascii-desc
```

创建命令：

```bash
git worktree add .worktrees/<branch-name> -b <branch-name>
```

创建后必须：
1. `pnpm install`（装完再跑 typecheck/lint，无 node_modules 时诊断不可信）
2. 确认后续所有 file_path 指向 worktree 路径

## 使用纪律

- **所有代码修改必须在 worktree 目录内**，禁止在主分支上 mkdir/write/edit
- Write/Edit 工具的 file_path 必须指向 worktree 路径，不是主仓库路径
- Bash 命令必须用**绝对路径**引用 worktree 文件（Bash CWD 不跨调用持久化）
- 每次开始编码前，先 `pwd` 确认当前在 worktree 内
- **跨仓库操作需各自独立 worktree**

## 清理

### 1. 扫描

```bash
bash <skill-path>/scripts/scan-worktrees.sh <repo-path-1> <repo-path-2> ...
```

输出 TSV：`REPO | PATH | BRANCH | MERGED | DIRTY | DISK_MB`

MERGED 列：
- `MERGED` — 本地 main 已包含
- `REMOTE_MERGED` — 远程 origin/main 已包含（本地 main 可能未更新）
- `NOT_MERGED` — 未合入

### 2. 分类展示

- **可安全清理**（MERGED 或 REMOTE_MERGED，且 DIRTY=0）：推荐清理，标注磁盘占用
- **需确认清理**（MERGED 或 REMOTE_MERGED，但 DIRTY>0）：提示未提交变更，用户决定
- **不建议清理**（NOT_MERGED）：仅展示

### 3. 用户确认

使用 `AskUserQuestion` 让用户选择：清理全部安全项 / 逐个选择 / 取消

### 4. 执行

```bash
bash <skill-path>/scripts/remove-worktree.sh <repo-path> <worktree-path> --delete-branch
# 有 dirty files 且用户确认强制清理：
bash <skill-path>/scripts/remove-worktree.sh <repo-path> <worktree-path> --force --delete-branch
```

### 5. 验证

重新运行扫描脚本，确认已移除，输出释放的磁盘空间总量。

## 安全规则

- **绝不清理 NOT_MERGED 的 worktree**，除非用户明确 `--force`
- **绝不删除 main/master 分支**
- 有 dirty files 时必须先展示变更内容，等用户确认
- 每次清理前 `git fetch origin` 确保合并状态准确
