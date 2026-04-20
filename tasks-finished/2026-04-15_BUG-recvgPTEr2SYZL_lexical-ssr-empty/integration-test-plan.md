# 集成测试计划：BUG-recvgPTEr2SYZL Lexical SSR 空标签修复

## 测试环境

- **Worktree**: `/Users/macbookair/Desktop/projects/fe-tripo-homepage/.worktrees/fix/ssr-empty-render`
- **分支**: `fix/ssr-empty-render`
- **最新 Commit**: `bef48d3` (fix: resolve SSR empty rendering for strong/em/code in text converter)
- **PR**: https://github.com/vast-enterprise/fe-tripo-homepage/pull/190

## 受影响范围（来自根因调查）

| 元素 | 文件 | 修复 Commit | 测试场景 |
|------|------|-------------|---------|
| `<blockquote>` | `blockquote.ts` | `3be11ae` | S1 |
| `<ul>/<ol>` | `list.ts` | `3be11ae` | S2 |
| `<li>` | `list.ts` | `3be11ae` | S2 |
| `<table>/<tbody>` | `table.ts` | `3be11ae` | S3 |
| `<td>/<th>` | `table.ts` | `3be11ae` | S3 |
| `<tr>` | `table.ts` | `3be11ae` | S3 |
| `<strong>` | `text.ts` | `bef48d3` | S4 |
| `<em>` | `text.ts` | `bef48d3` | S4 |
| `<code>（行内）` | `text.ts` | `bef48d3` | S4 |

## 测试场景

### S1-S6: 单元测试（VNode 结构验证）

| 场景 | 验证什么 | 工具 | 状态 |
|------|---------|------|------|
| S1 | BlockquoteVueConverter children 数组形式 | vitest | ✅ PASS |
| S2 | ListVueConverter (list + listitem) children 数组形式 | vitest | ✅ PASS |
| S3 | TableVueConverter (table/tablecell/tablerow) children 非函数 | vitest | ✅ PASS |
| S4 | TextVueConverter (strong/em/code) children 数组形式 | vitest | ✅ PASS |
| S5 | 全量回归（94 个测试） | vitest | ✅ PASS |
| S6 | 代码质量（lint + typecheck） | pnpm | ✅ PASS |

### S7: SSR 页面渲染验证（集成测试）

| 项 | 内容 |
|----|------|
| 验证什么 | blockquote/list/table/strong/em/code 在 SSR HTML 输出中有实际内容 |
| 工具 | playwright snapshot + screenshot + curl SSR HTML |
| 证据形式 | playwright snapshot YAML + 截图 + curl 正则提取 |
| 测试数据 | http://localhost:3020/blog/ssr-integration-test-rich-text（本地创建的 Lexical 文章） |
| 测试环境 | CMS (localhost:3000) + Nuxt worktree (localhost:3020) |
| 预期结果 | 所有 9 个元素在 SSR HTML 中有内容，playwright snapshot 显示元素有文本 |
| 状态 | ✅ PASS |
