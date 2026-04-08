# Code Review — fe-tripo-homepage

**分支**: feature/REQ-recvfIeCwDLyRP-blog-posts-orderable
**PR**: #182

## 审查结果

### CRITICAL: 无

### HIGH: 无

### MEDIUM

1. **"Pinned" 标签硬编码英文** — blog 组件中其他文本（如 "All", "Loading...", "No more posts"）也是硬编码英文，与现有模式一致。如需国际化可后续迭代。

### LOW

1. **sort 数组格式** — `['-pinned', '-_order', '-publishedAt']` 使用数组格式，Payload SDK `find()` 支持此格式。已验证。
2. **`pinned` 类型为 `boolean | undefined`** — 使用 `post.pinned ?? false` 处理 undefined 情况，正确。

## 结论

✅ 审查通过，无需修复。
