---
name: clean-worktree
description: |
  清理已完成任务的 git worktree。扫描所有 Tripo 项目仓库（tripo-cms、fe-tripo-homepage、fe-tripo-tools）的 worktree，
  识别已合入 main 的分支，安全移除对应 worktree 和分支，释放磁盘空间。

  触发条件：
  - `/clean-worktree` 或"清理 worktree"、"清理工作树"、"删除 worktree"
  - "磁盘空间不够"、"worktree 太多了"、"清理临时分支"
  - 需求完成后的收尾清理
---

# 清理 Worktree

## 仓库来源

从 `tripo-repos` skill 的"仓库列表"表格中获取所有仓库的"本地路径"列。
不要硬编码仓库路径——始终以 `tripo-repos` skill 为唯一数据源。

## 流程

### 1. 扫描

从 `tripo-repos` skill 获取仓库路径后，运行扫描脚本：

```bash
bash <skill-path>/scripts/scan-worktrees.sh <repo-path-1> <repo-path-2> ...
```

输出 TSV 格式：`REPO | PATH | BRANCH | MERGED | DIRTY | DISK_MB`

MERGED 列含义：
- `MERGED` — 本地 main 已包含该分支
- `REMOTE_MERGED` — 远程 origin/main 已包含（本地 main 可能未更新）
- `NOT_MERGED` — 未合入

### 2. 分类展示

将扫描结果分三组展示给用户：

**可安全清理**（MERGED 或 REMOTE_MERGED，且 DIRTY=0）：
- 直接推荐清理，标注磁盘占用

**需确认清理**（MERGED 或 REMOTE_MERGED，但 DIRTY>0）：
- 提示有未提交变更，让用户决定是否强制清理

**不建议清理**（NOT_MERGED）：
- 仅展示信息，不主动清理

### 3. 用户确认

使用 `AskUserQuestion` 让用户选择要清理的 worktree。选项：
- 清理所有"可安全清理"的 worktree
- 逐个选择
- 取消

### 4. 执行清理

对用户确认的每个 worktree，运行移除脚本：

```bash
bash <skill-path>/scripts/remove-worktree.sh <repo-path> <worktree-path> --delete-branch
```

如果有 dirty files 且用户确认强制清理：

```bash
bash <skill-path>/scripts/remove-worktree.sh <repo-path> <worktree-path> --force --delete-branch
```

### 5. 验证

清理完成后重新运行扫描脚本，确认 worktree 已移除，输出释放的磁盘空间总量。

## 安全规则

- **绝不清理 NOT_MERGED 的 worktree**，除非用户明确指定 `--force`
- **绝不删除 main/master 分支**
- 有 dirty files 时必须先展示变更内容，等用户确认
- 每次清理前 `git fetch origin` 确保合并状态准确
