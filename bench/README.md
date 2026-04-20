# Tripo Agent Benchmark

> Specialist Agent 架构改造的评估基线。每 phase 改动后跑一次，对比前后分数。

## 设计原则

- **历史事故驱动**：测试集里的 regression prompt 全部来自真实复盘文档的失败模式
- **半自动评分**：runner 自动跑 + LLM-as-judge 打分 + 人工审阅终分
- **结构化归档**：每次运行生成独立 Markdown 报告，版本控制可追溯
- **以 agent 为迭代单位**：P0 baseline → P1 diagnose → P2 developer → ... → P8 主 agent 改造

## 目录结构

```
bench/
├── README.md                    # 本文件
├── rubric.md                    # 4 维度评分标准
├── runner.py                    # 批量 runner
├── judge_prompt.md              # LLM-as-judge 的评分 system prompt
├── prompts/
│   ├── regression/              # 历史事故复现（7 条）
│   └── normal/                  # 正常流程（5 条）
└── reports/
    └── P<N>-<agent>-<date>.md   # 每 phase 报告归档
```

## Prompt 文件格式

每条 prompt 是一个 `.md` 文件，格式如下：

```markdown
---
id: <唯一 ID，如 req-notify-not-blocking>
category: regression | normal
origin: <来源，如 tmp/retro-2026-04-16-blog-posts-orderable.md>
touches_rules:  # 触及的铁律编号
  - 6  # 飞书通知必须阻塞
expected_agent: <期望派到哪个 agent>
expected_skill: <期望加载哪个 skill>
---

## User Prompt
<用户输入的原文>

## Expected Behavior
<期望的行为流程，一条条列>

## Scoring Notes
- 路由准确：<这条的具体期待>
- 流程遵循：<同上>
- 铁律遵守：<同上>
- 产出质量:<同上>
```

## 使用流程

### 跑一次完整 benchmark

```bash
cd bench
python3 runner.py --phase P0 --label baseline
# 每条 prompt 独立 session 跑，收集 transcript
# LLM-as-judge 打分
# 汇总生成 reports/P0-baseline-<date>.md
```

### 对比两次 benchmark

```bash
python3 runner.py --phase P1 --label diagnose --compare-to P0-baseline-<date>
# 报告里自动含 diff 段落
```

## 环境要求

- `claude` CLI 已登录（benchmark 和 judge 都走 claude -p，共享同一套认证）
- Python 3.9+（纯标准库，无额外依赖）

## Runner 命令

```bash
# 完整跑 baseline
python3 runner.py --phase P0 --label baseline

# 只重跑 judge（复用已有 transcripts）
python3 runner.py --phase P0 --label baseline --skip-run

# 只重渲染 md（复用已有评分 JSON）
python3 runner.py --phase P0 --label baseline --skip-judge

# 单条 prompt 调试
python3 runner.py --phase P0 --label baseline --only m1-test-skill-loaded-not-executed

# 对比两轮
python3 runner.py --phase P1 --label diagnose \
    --compare-to reports/P0-baseline-2026-04-17.json
```

## Benchmark 运行策略

runner 用以下 flag 跑**被评测 session**，保留 CLAUDE.md + memory + skills 以测当前默认行为，同时避免真实副作用：
- `--permission-mode plan`：强制进 plan mode
- `--allowedTools` 白名单：Read/Grep/Glob/Skill/Task*/AskUserQuestion/Agent
- `--no-session-persistence`：不污染 `/resume` 历史
- 独立 `--session-id`（UUID）+ 独立 transcript 文件

**Judge session** 则用 `--bare + --system-prompt judge_prompt.md`：完全跳过 hooks/memory/CLAUDE.md/skills，保证 judge 不被项目规则污染、只按 rubric 打分。

user prompt 末尾自动追加 benchmark 提示：要求 agent 输出意图（路由/skill/步骤），不真的执行写入类 tool calls。

## 评分机制

详见 [rubric.md](rubric.md)。

**总分 20**（4 维度 × 5 分）：
- ≥16：通过
- 12-15：勉强
- <12：失败

**退化红线**：任一条 prompt 分数 下降 ≥3 即视为 regression，该 phase 不 merge。

## 迭代路线

详见 `../docs/plans/2026-04-17-specialist-agent-architecture.md` 第 7 节。

| Phase | 任务 | 预期改善的 prompt |
|-------|------|-----------------|
| P0 | baseline | 无 |
| P1 | diagnose agent | bug275-*, bug279-skip-llmdoc, req-tool-downgrade |
| P2 | developer agent | 所有编码相关 |
| P3 | planner + tripo-planning | req-kickoff, tech-review |
| P4 | architect + tripo-architecture | tech-review |
| P5 | tester agent | bug275-test-type-mismatch |
| P6 | release agent | bug275-deploy-before-confirm |
| P7 | scrum-master agent | req-notify-not-blocking, req-status-no-skill-load |
| P8 | notify agent + 主路由改造 | 所有通知相关 |
