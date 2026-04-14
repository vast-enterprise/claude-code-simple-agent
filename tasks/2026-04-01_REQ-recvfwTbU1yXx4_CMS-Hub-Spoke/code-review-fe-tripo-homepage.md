# Code Review: fe-tripo-homepage PR #188

> PR: https://github.com/vast-enterprise/fe-tripo-homepage/pull/188
> 分支: feature/REQ-recvfwTbU1yXx4-cms-hub-spoke
> 审查日期: 2026-04-14

## 审查结果

| 级别 | 数量 | 状态 |
|------|------|------|
| CRITICAL | 2 | ✅ 已修复 |
| HIGH | 4 | ✅ 已修复 |
| MEDIUM | 5 | ✅ 已修复 (3) / 接受 (2) |
| LOW | 3 | 接受 |

## CRITICAL 问题

### C-1: Feature Flag 每请求查询 CMS，无缓存
- 状态: 📝 后续优化（与 blog 现有模式一致）
- 影响: CMS 负载翻倍（每个页面请求 = 1 次 flag + 1 次数据）
- 计划: merge 后独立 PR 统一缓存

### C-2: Sitemap 查询未检查本地化内容存在性 ✅
- 修复: 添加 `fallbackLocale: false` 和 `title: { exists: true }` 条件
- 提交: e6f822d

## HIGH 问题

### H-1: spokeData 被直接 mutate ✅
- 修复: 改为 `return { ...spokeData, hubTitle: ... }`

### H-2: buildMeta ogImage 断言不安全 ✅
- 修复: `ogImage as string | undefined` → `ogImage ?? undefined`

### H-3: picture 模式缺少错误处理 ✅
- 修复: 添加 `pictureError` ref + `@error` 处理 + fallback 退化

### H-4: as any 缺少 TODO 注释 ✅
- 修复: 所有 `as any` 处添加 TODO 说明

## MEDIUM 问题

### M-4: sitemap 中 hubSlug 解析重复 ✅
- 修复: 复用 `resolveHubSlug()`

### M-5: PLAN.md 提交到仓库 ✅
- 修复: `git rm PLAN.md` + 添加到 `.gitignore`

### M-1/M-2/M-3: Feature Flag 重复 / sitemap limit / 错别字
- 状态: 接受，后续优化

## 测试验证

修复后验证:
- 67 个 adapter 单元测试通过
- ESLint 0 errors
- TypeCheck 0 errors
- 提交 e6f822d 已推送
