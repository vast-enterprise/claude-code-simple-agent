#!/usr/bin/env bash
# scan-worktrees.sh — 扫描指定仓库的所有 worktree，输出状态报告
# Usage: scan-worktrees.sh <repo-path> [<repo-path2> ...]
# Output: TSV format — repo | worktree_path | branch | merged | dirty_count | disk_mb

set -euo pipefail

scan_repo() {
  local repo="$1"
  local repo_name
  repo_name=$(basename "$repo")

  # Get main branch name
  local main_branch
  main_branch=$(git -C "$repo" symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's|refs/remotes/origin/||' || echo "main")

  # List worktrees (skip the main worktree itself)
  git -C "$repo" worktree list --porcelain | grep "^worktree " | sed 's/^worktree //' | while read -r wt_path; do
    # Skip the main repo directory
    if [ "$wt_path" = "$repo" ]; then
      continue
    fi

    # Branch name
    local branch
    branch=$(git -C "$wt_path" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "DETACHED")

    # Merged status: check if branch is merged into main
    local merged="NOT_MERGED"
    if git -C "$repo" branch --merged "$main_branch" 2>/dev/null | grep -qw "$branch"; then
      merged="MERGED"
    fi

    # Also check remote merged (in case local main is behind)
    if [ "$merged" = "NOT_MERGED" ]; then
      if git -C "$repo" branch -r --merged "origin/$main_branch" 2>/dev/null | grep -q "origin/$branch"; then
        merged="REMOTE_MERGED"
      fi
    fi

    # Dirty file count
    local dirty_count
    dirty_count=$(git -C "$wt_path" status --porcelain 2>/dev/null | wc -l | tr -d ' ')

    # Disk usage in MB
    local disk_mb
    disk_mb=$(du -sm "$wt_path" 2>/dev/null | cut -f1 || echo "?")

    printf "%s\t%s\t%s\t%s\t%s\t%s\n" "$repo_name" "$wt_path" "$branch" "$merged" "$dirty_count" "$disk_mb"
  done
}

if [ $# -eq 0 ]; then
  echo "Usage: scan-worktrees.sh <repo-path> [<repo-path2> ...]" >&2
  exit 1
fi

# Header
printf "REPO\tPATH\tBRANCH\tMERGED\tDIRTY\tDISK_MB\n"

for repo in "$@"; do
  if [ -d "$repo/.git" ] || [ -f "$repo/.git" ]; then
    scan_repo "$repo"
  else
    echo "WARN: $repo is not a git repository" >&2
  fi
done
