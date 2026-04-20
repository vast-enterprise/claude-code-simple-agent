---
id: m4-blind-debug-without-investigation
category: regression
mode: M4
origin: tmp/retro-2026-04-16-blog-posts-orderable.md
touches_rules: [3]
expected_agent: diagnose
expected_skill: tripo-diagnose
---

## User Prompt

OSS blog post 的树形渲染在 CMS preview 里看不到内容，但线上正常。帮我查查什么原因，顺便改一下。

## Expected Behavior

1. 识别为"问题诊断"类任务，派到 diagnose agent
2. diagnose agent 行为：
   - 加载 tripo-diagnose skill
   - 先读 CMS 仓库的 llmdoc（铁律 3）
   - 按优先级阶梯：文档 → 代码 → 运行时验证
   - **先对比 preview vs 线上的差异**（什么环境变量、什么渲染路径不同）
   - 给出根因假设 + 验证方法
   - 再决定是否动手改代码
3. **不直接调 depth / 盲改参数 5 轮**

## Anti-Pattern

- 直接进 CMS 仓库改 `depth` 参数，调 5 轮还没通
- 跳过 llmdoc，直接看源码
- 不对比正常/异常路径

## Scoring Notes

- 路由准确：是否派到 diagnose agent（baseline 期望 0，P1 后期望 5）
- 流程遵循：tripo-diagnose 的优先级阶梯是否遵守
- 铁律遵守：铁律 3（先读 llmdoc）
- 产出质量：是否给出根因假设 + 验证方法，不是盲改
