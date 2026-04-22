---
name: tripo-release
description: |
  前端发车/上线编排。**独立流程**，不被 requirement/bugfix 自动触发，由用户或 scrum-master 在发车时机显式调起。
  13 步发车编排：决定 → 建车 → 审需求 → 检 main → 发 release → 跑流水线 → 验证 → 勾表 → 通知验收 → 用户验收 → 发版确认 → 收尾需求 → 关车。
  自身不维护数据；表格操作引用 tripo-tables，仓库信息引用 tripo-repos，业务语义引用 references/dispatch-board.md。

  触发条件：
  - `/tripo-release`、"发车"、"上线"、"上车"、"启动发车"、"发版"、"发版完成"
  - "跟车"、"hotfix 上线"、"SSS 上线"、"部署 production"、"部署 staging"
  - scrum-master 收到「发车」指令后调用
  - tripo-requirement / tripo-bugfix 只到「提交发车候选」为止,**不自动调用本 skill**
---

# 前端发车/上线编排

## 角色分工（重要）

发车涉及**两个角色**协作,本 skill 同时承担编排视图,但在关键步骤标注主责方：

| 角色 | 主责范围 | 操作对象 |
|------|----------|----------|
| **scrum-master agent** | 表格读写、飞书通知、节奏协调 | tripo-tables(Sprint/发车中/需求池/Hotfix) + tripo-notify |
| **release agent**(本 skill 对应) | 代码、tag、流水线、部署验证 | 各仓库 git + gh + curl |
| 用户 | 决策触发、验收确认 | — |

> 数据字典(option_id / Workflow ID / 字段 ID)→ **tripo-tables/references/release-flow.md**
> 业务语义(三条路径/接力部署)→ **references/dispatch-board.md**
> 部署命令细节 → **references/deploy-staging.md / deploy-production.md**

## 何时进入本流程

- ✅ 用户说「发车」「上线」「启动发车」「上车」「发版」
- ✅ scrum-master 已汇总好候选,准备发车
- ❌ 需求/Bug 刚 staging 验收通过 → **只标记为发车候选**,不自动触发本流程
- ❌ 用户只说「部署 staging」→ 走 Staging 轻量分支(见底部),不进入 13 步编排

## 13 步发车编排

### Step 1. 决定发车 【用户/scrum-master】

触发来源：用户主动说发车 / scrum-master 判定班车满员或到期。

**1a. 先查当前班车现状**(lark-cli → tripo-tables)：
- Sprint 版本计划,筛 `班车状态=已启动` 记录
- 发车中需求,筛 `状态=待上线` 记录,按发车版本分组
- 输出:当前有 N 条跟车候选 / M 条 SSS 待上线 / K 条 Hotfix 待上线

**1b. 带现状信息 AskUserQuestion 确认**：
- 发车类型(跟车 / SSS 临时 / Hotfix)
- 若跟车有多条已启动班车 → 让用户选目标班车
- **不替用户决策**

输出：发车类型 + 目标 Sprint 版本(跟车)或新建计划(SSS/Hotfix)。

### Step 2. 查/建 Sprint 班车记录 【scrum-master】

| 类型 | 动作 |
|------|------|
| 跟车 | 查 Sprint 版本计划,找 `班车状态=已启动 & 上线类型=跟车` 记录;多条 → AskUserQuestion |
| SSS | 新建记录(`上线类型=sss、班车状态=已启动`) |
| Hotfix | 新建记录(`上线类型=hotfix、班车状态=已启动`),关联 Hotfix管理 |

工具：`lark-cli base +record-list / +record-upsert`,option_id 见 tripo-tables/references/release-flow.md

### Step 3. 审视上车需求 【scrum-master + 用户】

- 汇总候选：发车中需求表查 `状态=待上线 & 发车版本=本车` 的记录
- 跨路径汇总：跟车 Sprint 下待上线需求 + 本次 SSS/Hotfix 单独车
- **⏸ AskUserQuestion 确认上车名单**,包含需求标题、Owner、涉及仓库
- 输出：(仓库 → 需求列表)映射,供后续检 main 用

### Step 4. 检查目标分支（如 main）状态 【release】

每个涉及的仓库都做一次：

- [ ] ⚠️ **必须 AskUserQuestion 确认目标分支**（默认 main，或测试/发版分支）
- [ ] `git fetch origin && git log origin/<target-branch> -20` — 验证候选 PR 均已合入
- [ ] `gh run list --branch <target-branch> --limit 5` — CI 绿
- [ ] 本地 `git pull origin <target-branch>` — 同步到最新

发现异常(PR 未合/CI 红)→ **停下**,回 Step 3 修正名单或通知 Owner 补齐。

### Step 5. 汇总发 release 【release】

每个涉及仓库：

```bash
# tag 命名：v{YYYY}.{MM}.{DD}[.N]
# 同一天多次：追加 .1 .2
git tag -l "v$(date +%Y.%m.%d)*"  # 先看冲突
git tag v2026.04.20 && git push origin v2026.04.20
gh release create v2026.04.20 --generate-notes
```

多仓库同批发车保持 tag 一致(便于回滚对齐)。

### Step 6. 执行发车流水线 【release】

每个仓库触发 production workflow(名字见 tripo-repos)：

```bash
gh workflow run <prod-workflow> --repo <org/repo> --ref v2026.04.20
gh run watch <run-id>
```

Action 失败 → 查日志 → 修 → 重触发;**不盲重**。

### Step 7. 部署验证 【release】

```bash
curl -sL -o /dev/null -w "%{http_code}" <production-url>
```

- HTTP 200 + 关键页面/接口可访问
- 有 CDN(如 fe-tripo-homepage 的 `cdn-refresh.yml`)→ 跟着刷
- 非 200 → 查 K8s pod 日志 → 必要时 rollback,**不要进下一步**

### Step 8. 勾部署 checkbox 【scrum-master】

每个前端仓库部署完毕后,勾 Sprint 版本计划对应 checkbox：

```bash
lark-cli base +record-update \
  --base-token HMvbbjDHOaHyc6sZny6cMRT8n8b \
  --table-id tblm2FGJjiK4frzt \
  --record-id <sprint-record-id> \
  --json '{"fields": {"前端部署完毕": true}}'
```

字段 ID(算法 `fldDgrQRTd` / 后端 `fldWGA6C5g` / 前端 `fldy6ym5PN`)见 tripo-tables/references/release-flow.md。
接力部署语义(算法→后端→前端)见 references/dispatch-board.md。

### Step 9. 通知验收 【scrum-master】

- 渠道：发车群(R3 节点)
- 发送方式：`lark-cli im +message-send --as bot`
- 内容：部署完成版本 + 候选需求清单 + 请验收的对象
- 通知模板与节点表见 **tripo-notify**

### Step 10. 用户验收 【用户】

- agent **等待**,不替用户验收
- 反馈路径：用户在群里 / 任务目录 / 飞书表格批注

### Step 11. 发版完成确认 【scrum-master】

触发 `wkfv7lNEMo3XlRlR`(发版完成确认)按钮,或 lark-cli 直接更表：

- 发车中需求：`上线中 → 完成`
- Sprint 版本计划：`班车状态 → 已完成`
- 产品需求池：涉及需求 `→ 已完成`
- Hotfix 管理(如有)：关联记录 `→ 完成`

### Step 12. 关联需求收尾 【scrum-master】

Step 11 的 workflow 已带动大部分状态,手动补齐剩余：

- 技术需求管理中已发版的记录状态同步
- 发车中需求关联的任务目录(tripo-task-dirs)归档 → tasks-finished
- 必要时通知需求 Owner 车已到站(`--as bot`)

### Step 13. 班车关闭 【scrum-master】

- 核对 Sprint 版本计划本车所有 checkbox 为 true、状态为已完成
- 跟车场景：下周新班车由 `wkfEdyvotjKQHMr6` 定时创建,不需手动建
- SSS/Hotfix 场景：本车即关闭

## Staging 部署(轻量,不走 13 步)

适用：前端仓库在发 production 前先部署 staging 验证、验收环境刷新等。

完整命令详见 [deploy-staging.md](references/deploy-staging.md)

| 步骤 | 动作 | 确认点 |
|------|------|--------|
| 1 | ⚠️ 确认目标分支后执行 `gh workflow run <staging-workflow> --repo <org/repo> --ref <target-branch>` | — |
| 2 | `gh run watch <run-id>` 等待完成 | 部署失败 → 查 Action 日志 |
| 3 | `curl -sL -w "%{http_code}" <staging-url>` 验证 HTTP 200 | 非 200 → 检查 K8s pod 状态 |
| 4 | 通知相关人(可选,`--as bot`) | — |

> 有 CI 已自动发 staging → 跳过 Step 1-2,只做 Step 3 验证。

## 异常处理

| 场景 | 处理 |
|------|------|
| Step 4 发现 PR 未合入 main | 回 Step 3 修正上车名单,或通知 Owner 先合 |
| Step 5 tag 已存在 | 追加 `.1`、`.2`,或确认是否复用现有 tag |
| Step 6 workflow 超时/失败 | 查 Action 日志 → 修 → 重触发,不盲重 |
| Step 7 验证非 200 | 查 K8s pod 日志 → 必要时 rollback deployment,**不要继续后续 step** |
| Step 8 checkbox 写入失败 | 检查 record-id、base-token 是否正确(tripo-tables 速查) |
| Step 10 验收未通过 | 回 tripo-requirement / tripo-bugfix 返工 Step 6-8,本车该需求从候选名单移除(发车中需求状态回退需与 scrum-master 协商) |
| 临时回滚 | rollback deployment + 发车中需求状态改回 `待上线` / 需求池状态改回 `验收/提测中` |

## 参考

- 业务语义全景(三条路径、接力部署、前端视角) → [references/dispatch-board.md](references/dispatch-board.md)
- 数据字典(option_id / Workflow ID / 字段 ID / lark-cli 业务参数) → tripo-tables/references/release-flow.md
- Staging 命令 → [references/deploy-staging.md](references/deploy-staging.md)
- Production 命令 → [references/deploy-production.md](references/deploy-production.md)
- 仓库路径/workflow 名/域名 → tripo-repos
- 通知节点/渠道规则 → tripo-notify
