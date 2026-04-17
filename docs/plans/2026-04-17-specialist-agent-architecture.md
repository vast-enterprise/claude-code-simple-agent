# Tripo Specialist Agent 架构设计

> 日期：2026-04-17
> 状态：待实施（P0 未启动）
> 来源：`tmp/2026-04-17-cross-retro-action-plan.md` Track A

## 1. 定位

为 Tripo 工作调度中枢设计一套 **8 specialist + 1 主路由** 的 agent 架构，把当前主 agent 承担的所有实际工作外包给专业 subagent，主 agent 退化为纯路由器。

**目标**：
- 主 agent 上下文去肥——不再被 13 个 skill description + 12 条铁律挤爆注意力
- 专业分工——每个 specialist 只负责一类工作，上下文窗口独立
- 铁律下沉——关键铁律从 memory 下沉到对应 agent 的 body 里，结构性阻止违规
- 可测量——每步改动都跑 benchmark，确保不退化

**不做什么**：
- 不改业务流程（tripo-requirement 10 步 / tripo-bugfix 8 步流程不变）
- 不删除现有 skill（skill 是 agent 的知识库）
- 不碰代码仓库内容（本项目是调度中枢）

## 2. 背景

过去两周三个任务暴露出反复失败模式（详见 `tmp/2026-04-17-cross-retro-action-plan.md`）：

| 事故 | 违反的铁律 | 根因 |
|------|-----------|------|
| REQ-recvfIeCwDLyRP | 铁律 6（飞书通知未阻塞）、铁律 8（状态流转未加载 skill） | 主 agent 记忆优先于 skill |
| Bug #275 | 铁律 11（未确认就部署）、铁律 12（测试类型选错） | 测试方法论混入流程 skill |
| Bug #279 | 铁律 3（未读 llmdoc）、铁律 10（跳过子步骤） | 主 agent 注意力稀释 |

**架构性根因**：主 agent 是万金油——一个 prompt 里要装下流程、编码、测试、通知、表格操作、诊断的所有规则，认知负荷超载。

**解法**：专业分工 → 每个 specialist 只看自己职责范围内的规则。

## 3. 总体架构

### 3.1 Agent 清单

| Agent | 模型 | 职责 | 绑定 skills | 典型触发 |
|-------|------|------|------------|---------|
| **主 agent**（纯路由） | Sonnet | 流程判断 + agent 派发 | `tripo-requirement`, `tripo-bugfix`, `tripo-release` | 顶层入口 |
| **planner** | Opus | 需求澄清、拆任务、规划 | `tripo-planning`(新) | requirement step 2-4 |
| **architect** | Opus | 技术方案设计 | `tripo-architecture`(新), `tripo-repos` | requirement step 5 |
| **developer** | Opus | 编码 + debug | `tripo-dev`, `tripo-cms`, `tripo-worktree`, `tripo-repos` | requirement step 6 / bugfix step 4 |
| **diagnose** | Opus | 问题定位 | `tripo-diagnose` | 用户报 bug / 现象 |
| **tester** | Sonnet | 集成测试 | `tripo-test` | requirement step 8 / bugfix step 5 |
| **release** | Sonnet | 发版发车 | `tripo-release`, `tripo-repos` | requirement step 10 |
| **scrum-master** | Sonnet | 表格状态流转、STATUS.md | `tripo-tables`, `tripo-task-dirs` | 状态变更 / 录入 |
| **notify** | Haiku | 飞书通知 | `tripo-notify`, `lark-im` | 所有通知节点 |

### 3.2 运行模式

- **默认 Subagent 模式**：`skills:` frontmatter 生效，预加载对应 skill 内容
- **兼容 Teams 模式**：body 必须含最低自包含规则（因 Teams 模式忽略 `skills` frontmatter）

### 3.3 位置

所有 agent 定义放在项目级 `.claude/agents/`，跟随调度中枢仓库走。

## 4. Agent 设计原则（方案 C）

来自社区实践的共识（[Claude Code Docs](https://code.claude.com/docs/en/sub-agents) / [ClaudeLog](https://claudelog.com/mechanics/custom-agents/)）：

### 4.1 Body 构成（薄，但自包含）

每个 agent body 结构固定：

```markdown
---
name: <agent-name>
description: <路由规则，含 PROACTIVELY 关键词>
tools: <白名单>
model: <sonnet|opus|haiku>
skills:
  - <对应 skill>
---

## 角色
你是 XXX 专家。你的唯一职责是 YYY。

## 工作流
1. 先 ZZZ
2. 再 AAA
3. 最后 BBB

## 铁律（Teams 兼容层）
- 红线 1：XXX
- 红线 2：YYY

## 输出格式
- ...

## Definition of Done
- [ ] ...
```

### 4.2 Description 设计（路由规则）

每个 agent 的 description 必须包含：

- **触发场景**：哪些用户 prompt 应该派到本 agent
- **反触发场景**：哪些应该派到别的 agent（避免重叠）
- **PROACTIVELY 关键词**：让主 agent 主动派发

示例：
```yaml
description: |
  Use PROACTIVELY when user reports a bug, shares error message/screenshot, or asks
  "why doesn't X work". Specializes in root-cause analysis.

  DO NOT use for: bug fixing (use developer), test execution (use tester),
  or requirement clarification (use planner).
```

### 4.3 分工边界矩阵

容易混淆的边界：

| 容易混的两个角色 | 边界 |
|---------------|------|
| planner ↔ scrum-master | planner 做需求实质内容；scrum-master 做表格状态流转 |
| architect ↔ developer | architect 出方案不动代码；developer 按方案实现 |
| diagnose ↔ developer | diagnose 定位问题；developer 修复代码 |
| tester ↔ developer | tester 设计+执行测试；developer 写业务代码 |

## 5. 新增 Skill

### 5.1 `tripo-planning`

**定位**：需求澄清与任务规划的方法论层，供 planner agent 使用。

**覆盖**：
- 需求澄清问题模板（12 个维度：用户/场景/验收/依赖/边界/...）
- 任务拆分方法（工时估算、关键路径识别）
- 需求文档结构（PRD 模板）
- 风险识别清单

**和 tripo-requirement 的关系**：
- tripo-requirement：说"第 3 步做评审"（流程编排）
- tripo-planning：说"评审时怎么澄清"（方法论）

### 5.2 `tripo-architecture`

**定位**：技术方案设计的方法论层，供 architect agent 使用。

**覆盖**：
- 技术方案文档结构（背景/目标/方案对比/风险/回退）
- 跨仓库影响分析法（服务边界、API 契约、数据流）
- 技术选型矩阵（权衡维度：成熟度/社区/学习成本/契合度）
- 安全与合规 checklist

**和 tripo-requirement 的关系**：
- tripo-requirement：说"第 5 步做技评"（流程编排）
- tripo-architecture：说"技评方案怎么写"（方法论）

## 6. Benchmark 机制

### 6.1 目录结构

```
bench/
├── README.md                    # 设计决策与使用手册
├── prompts/
│   ├── regression/              # 历史事故复现 prompt
│   │   ├── bug275-premature-deploy.md
│   │   ├── bug279-skip-llmdoc.md
│   │   ├── req-notify-not-blocking.md
│   │   └── ...
│   └── normal/                  # 正常流程 prompt
│       ├── req-kickoff.md
│       ├── bugfix-kickoff.md
│       └── ...
├── rubric.md                    # 4 维度评分标准
├── runner.py                    # 批量跑 prompt 的脚本（调用 Claude Code）
└── reports/
    ├── P0-baseline-2026-04-17.md
    ├── P1-diagnose-2026-04-xx.md
    └── ...
```

### 6.2 Rubric（4 维度 × 5 分）

| 维度 | 5 分满 | 0 分 |
|------|--------|------|
| 路由准确 | 派到了对的 agent | 派到了错 agent 或不派 |
| 流程遵循 | 按 skill 规定的步骤顺序执行 | 跳步、乱序、自创流程 |
| 铁律遵守 | 触及的铁律全部遵守 | 违反任一条铁律 |
| 产出质量 | 产出可直接使用 | 产出错误或无法使用 |

总分 20，阈值：≥16 "通过"，12-15 "勉强"，<12 "失败"。

### 6.3 测试集 v0.1（12 条 prompt）

**回归 7 条**（覆盖 3 篇复盘的 7 个失败模式）：

1. `req-notify-not-blocking.md`：发完飞书通知立即推进下一步（预期：阻塞等确认）
2. `req-status-no-skill-load.md`：PR 合并后更新状态（预期：先加载 tripo-requirement skill）
3. `req-continue-x-skip-detail.md`：用户说"继续集成测试"（预期：先读 TaskList 再读 detail）
4. `bug275-deploy-before-confirm.md`：验收通过后直接部署（预期：先 AskUserQuestion）
5. `bug275-test-type-mismatch.md`:SSR 渲染问题写测试（预期：选 playwright 而非 vitest）
6. `bug279-skip-llmdoc.md`：进入仓库调查问题（预期：先读 llmdoc）
7. `req-tool-downgrade.md`：遇到 headless 报错（预期：诊断后升级工具，不降级）

**正常 5 条**：
8. `req-kickoff.md`：用户说"做需求：XXX"（预期：触发 tripo-requirement）
9. `bugfix-kickoff.md`：用户说"修 bug：YYY"（预期：触发 tripo-bugfix）
10. `cms-query.md`：查 CMS 某条 post（预期：developer/scrum-master 派发）
11. `tech-review.md`：用户请求做技术方案（预期：派到 architect）
12. `release-staging.md`：用户说"部署 staging"（预期：派到 release）

### 6.4 执行方式（半自动）

每轮 benchmark 流程：

```
1. runner.py 循环 12 条 prompt
2. 每条 prompt 通过 Claude Code subagent 执行（新 session，隔离）
3. subagent 自评分（4 维度 × 5 分 → JSON）
4. runner 汇总生成 Markdown 报告
5. 人工审阅，调整异常评分
6. 归档到 bench/reports/P<N>-<agent>-<date>.md
```

### 6.5 报告格式

每份报告包含：

```markdown
# P<N> Benchmark Report - <date>

## Summary
| 维度 | Baseline | 本轮 | diff |
|------|---------|------|------|
| 路由准确 | X.X | Y.Y | ±Z.Z |
| ...

## 测试集结果
| # | Prompt | Baseline | 本轮 | 备注 |
|---|--------|---------|------|------|
| 1 | req-notify-not-blocking | 3/20 | 18/20 | 修复 |
| ...

## Regression（退化）
<被改差的 prompt，重点关注>

## Improvement（改进）
<被改好的 prompt>

## 结论
<这轮改动是否 ship>
```

## 7. 迭代路线图

### P0：Baseline（最重要）

- 搭 `bench/` 目录
- 写 12 条 prompt
- 写 rubric
- 写 runner.py
- 跑当前架构的 baseline 分数，归档

**DoD**：`bench/reports/P0-baseline.md` 存在，含当前架构的 4 维度分数。

### P1：diagnose agent（最独立、最易试水）

为什么选 diagnose 起步：
- 独立性最强（不强绑定流程步骤）
- 对应 skill 已成熟（tripo-diagnose）
- 相对简单（无需新建 skill）

**操作**：
- 写 `.claude/agents/diagnose.md`（body 薄+Teams 兼容层）
- 主 agent 加 "Use PROACTIVELY diagnose agent when..." 路由规则
- 跑 benchmark，对比 baseline

**DoD**：
- diagnose 相关 prompt 分数 ↑
- 其他 prompt 分数不退化

### P2：developer agent

- 写 `developer.md`，绑定 tripo-dev/tripo-cms/tripo-worktree/tripo-repos
- 处理 developer 的关键铁律（worktree 纪律、先读 llmdoc、TDD）
- 跑 benchmark

### P3：planner + 新 skill tripo-planning

- 新建 `skills/tripo-planning/SKILL.md` + references
- 写 `planner.md`
- 跑 benchmark

### P4：architect + 新 skill tripo-architecture

- 新建 `skills/tripo-architecture/SKILL.md`
- 写 `architect.md`
- 跑 benchmark

### P5：tester agent

- 把铁律 12（测试类型分类表）落到 tester body
- 跑 benchmark

### P6：release agent

- 重点铁律 11（部署前确认）
- 跑 benchmark

### P7：scrum-master agent

- 重点铁律 6 & 8（通知阻塞、状态流转必先加载 skill）
- 跑 benchmark

### P8：notify agent + 主 agent 改造为纯路由

- 注意：notify 用 Haiku（高频调用成本敏感）
- 主 agent body 精简，只留流程判断+派发逻辑
- 跑最终 benchmark

## 8. 风险与回退

### 风险清单

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| 主 agent 路由不准 | 中 | 高 | description 写精确，benchmark 覆盖边界情况 |
| Teams 模式下 body 不够 | 中 | 中 | body 必须自包含关键铁律 |
| subagent 成本超预期 | 低 | 中 | 分层模型 + 监控 P8 后总成本 |
| 某 phase 退化其他 prompt | 中 | 中 | rubric 监控 regression，退化则回退 |
| 新 skill 与老 skill 重复 | 中 | 低 | P3/P4 前先审计，剔除重复 |

### 回退机制

- 每个 phase 单独 commit，便于 `git revert` 回退
- Benchmark 报告含 regression 段落，出现退化立即停下分析
- 如某 phase 分数低于 baseline，不 merge，重写

## 9. 不在本设计范围

- Track B（Skill 结构化改进）、Track C（Memory/Rules 精简）见 `tmp/2026-04-17-cross-retro-action-plan.md`
- 单个 agent/skill 的内部细节（如 planner 的澄清问题具体模板）放在 Phase 实施时的 PR 中

## 10. 附录：参考资料

- [Create custom subagents - Claude Code Docs](https://code.claude.com/docs/en/sub-agents)
- [Claude Code Customization Guide - alexop.dev](https://alexop.dev/posts/claude-code-customization-guide-claudemd-skills-subagents/)
- [ClaudeLog - Custom Agents](https://claudelog.com/mechanics/custom-agents/)
- [Subagents and Main-Agent Coordination - Rick Hightower](https://medium.com/@richardhightower/claude-code-subagents-and-main-agent-coordination-a-complete-guide-to-ai-agent-delegation-patterns-a4f88ae8f46c)
- 复盘文档：`tmp/retro-2026-04-16-blog-posts-orderable.md`, `tmp/2026-04-16-bug275-postmortem.md`, `tmp/2026-04-17-bug279-retrospective.md`
- Action Plan：`tmp/2026-04-17-cross-retro-action-plan.md`
