# Code Review 报告：Translation Plugin (tripo-cms)

## 审查范围

`src/plugins/translation/` — 24 个文件，3,251 行

## 审查结果

### CRITICAL（已修复）

| # | 问题 | 修复 |
|---|------|------|
| C1 | openai-resolver `JSON.parse` 未 try-catch，非 JSON 响应会抛未处理异常 | 包裹 try-catch，返回 `{ success: false }` |
| C2 | translate-batch `Promise.all` 不容错，单个失败导致整批中断 | 改用 `Promise.allSettled` + 逐 promise try-catch |
| C3 | translate-field 获取了翻译文档但未调 `payload.update`，死代码 | 删除无用的 findByID + setNestedValue |

### HIGH（已修复）

| # | 问题 | 修复 |
|---|------|------|
| H1 | translate-operation `resolver.resolve()` 无 try-catch | 包裹 try-catch，返回错误信息 |
| H3 | `setNestedValue`/`getNestedValue` 原型污染风险 | 添加 `__proto__`/`constructor`/`prototype` 键过滤 |
| H6 | API handler 无 collection 白名单校验 | 提取 `isCollectionAllowed` 共享函数，所有 handler 校验 |

### HIGH（延后修复）

| # | 问题 | 原因 |
|---|------|------|
| H2 | translatedTexts 数量与 texts 不匹配时静默错位 | 低概率，添加日志即可，不阻塞 |
| H4 | translation-status `limit: 0` 全量加载文档 | 性能优化，非功能阻塞 |
| H5 | afterRead hook 只计算当前 locale | 设计取舍，非 bug |

### MEDIUM（记录）

| # | 问题 |
|---|------|
| M1 | getResolver 重复代码 → **已修复**，提取到 `utils/get-resolver.ts` |
| M2 | UI 组件硬编码 locale 列表 → 后续从 config 动态获取 |
| M3 | batch-translate-modal 重导出命名混淆 → 可接受 |
| M4 | getNestedValue 不处理数组索引路径 → 边界场景 |
| M5 | 设计文档中 `resolve-localized-fields.ts` 缺失 → 功能合并到 traverse-fields |
| M6 | openai-resolver 缺少重试机制 → 后续迭代 |

## 修复验证

- ✅ 72 个测试全通过
- ✅ TypeScript 0 错误
- ✅ ESLint 0 警告
- ✅ 修复已 commit 并推送到 PR #42

## 做得好的方面

1. Resolver 架构设计清晰，discriminated union 类型安全
2. Lexical 遍历防御性编程完善，避免了 enchants 的崩溃 bug
3. emptyOnly 默认 true 符合设计
4. 测试覆盖率高，辅助函数设计干净
5. Plugin 入口使用 lazy import 避免循环依赖
6. Auth 守卫一致，所有 endpoint 首行检查 req.user
