#!/usr/bin/env bash
# remove-worktree.sh — 安全移除一个 worktree 及其关联分支
# Usage: remove-worktree.sh <repo-path> <worktree-path> [--force] [--delete-branch]
#
# Safety checks:
#   1. Worktree must exist and belong to the repo
#   2. No dirty files (unless --force)
#   3. Branch must be merged into main (unless --force)
#
# --delete-branch: also delete the local branch after removing worktree

set -euo pipefail

FORCE=false
DELETE_BRANCH=false
REPO=""
WT_PATH=""

for arg in "$@"; do
  case "$arg" in
    --force) FORCE=true ;;
    --delete-branch) DELETE_BRANCH=true ;;
    *)
      if [ -z "$REPO" ]; then
        REPO="$arg"
      elif [ -z "$WT_PATH" ]; then
        WT_PATH="$arg"
      fi
      ;;
  esac
done

if [ -z "$REPO" ] || [ -z "$WT_PATH" ]; then
  echo "Usage: remove-worktree.sh <repo-path> <worktree-path> [--force] [--delete-branch]" >&2
  exit 1
fi

# Resolve absolute paths
REPO=$(cd "$REPO" && pwd)
WT_PATH=$(cd "$WT_PATH" && pwd 2>/dev/null || echo "$WT_PATH")

# Verify worktree belongs to repo
if ! git -C "$REPO" worktree list --porcelain | grep -q "^worktree $WT_PATH$"; then
  echo "ERROR: $WT_PATH is not a worktree of $REPO" >&2
  exit 1
fi

# Get branch name
BRANCH=$(git -C "$WT_PATH" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "")

# Safety check: dirty files
DIRTY_COUNT=$(git -C "$WT_PATH" status --porcelain 2>/dev/null | wc -l | tr -d ' ')
if [ "$DIRTY_COUNT" -gt 0 ] && [ "$FORCE" = false ]; then
  echo "ERROR: Worktree has $DIRTY_COUNT uncommitted changes. Use --force to override." >&2
  git -C "$WT_PATH" status --short >&2
  exit 1
fi

# Safety check: branch merged
MAIN_BRANCH=$(git -C "$REPO" symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's|refs/remotes/origin/||' || echo "main")
MERGED=false
if [ -n "$BRANCH" ] && [ "$BRANCH" != "HEAD" ]; then
  if git -C "$REPO" branch --merged "$MAIN_BRANCH" 2>/dev/null | grep -qw "$BRANCH"; then
    MERGED=true
  elif git -C "$REPO" branch -r --merged "origin/$MAIN_BRANCH" 2>/dev/null | grep -q "origin/$BRANCH"; then
    MERGED=true
  fi
fi

if [ "$MERGED" = false ] && [ "$FORCE" = false ]; then
  echo "ERROR: Branch '$BRANCH' is not merged into $MAIN_BRANCH. Use --force to override." >&2
  exit 1
fi

# Remove worktree
echo "Removing worktree: $WT_PATH (branch: $BRANCH)"
git -C "$REPO" worktree remove "$WT_PATH" --force 2>/dev/null || {
  echo "WARN: git worktree remove failed, trying manual cleanup..." >&2
  rm -rf "$WT_PATH"
  git -C "$REPO" worktree prune
}

# Delete branch if requested
if [ "$DELETE_BRANCH" = true ] && [ -n "$BRANCH" ] && [ "$BRANCH" != "HEAD" ] && [ "$BRANCH" != "main" ] && [ "$BRANCH" != "master" ]; then
  echo "Deleting branch: $BRANCH"
  git -C "$REPO" branch -D "$BRANCH" 2>/dev/null || echo "WARN: Could not delete branch $BRANCH"
fi

echo "Done."
