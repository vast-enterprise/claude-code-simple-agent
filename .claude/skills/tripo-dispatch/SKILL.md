---
name: tripo-dispatch
description: |
  调度会话派发：通过 HTTP 控制平面（localhost:8420）查询 / 创建 / 激活 owner 的需求 session，
  主动推进停滞的需求或 Bug。用户说"看看今天哪些需求停滞了"/"把 XXX 推一下"/"查一下我的所有 session"时触发。

  被调用场景：
  - 用户在飞书主会话问"哪些需求在 pending / 今天有哪些在跑"
  - 用户要求主动推进某个停滞需求（"把 homepage-schema 推一下"、"让 X 继续"）
  - 需要盘点 owner 所有活跃 session 的状态
  - tripo-requirement 或 tripo-bugfix 流程中需要向其他 session 派发消息（跨 session 协作）

  不要用于：
  - 用户自己在 Feishu 里用 /new / $suffix 等指令操作自己的 session（那是 multi-session 本地指令）
  - 调度 session 内部的工作流执行（那是在 session 内运行的 specialist agent 的事）
---

# Tripo 调度会话派发

## 定位

本 skill 是**控制平面客户端**：通过本机 HTTP（`http://localhost:8420`）向运行中的 avatar 服务派发 session 指令，用于主 Claude agent 从**外部**盘点、激活、续推 owner 名下的分身 session。

**不直接操作飞书**——Feishu 侧的读写、通知、@、回复，都是各 session 内部 agent 的事（见 `lark-im` / `tripo-notify` / `tripo-tables`）。本 skill 只做「指挥谁起来、让谁往前走一步」。

**不决策**——哪个需求要推、该发什么内容、要不要创建新 session，全部由调用方（主 agent）判断。本 skill 只提供 curl 模板、状态机查询、错误码对照表和几套典型工作流的编排骨架。调用方拿到材料自己拼，最后真正派发前向用户 `AskUserQuestion` 确认。

## 前置条件

调用前先确认以下两条，任何一条不满足都不要派发：

1. **服务健康**：`curl -s http://localhost:8420/api/status` 返回 200 且 JSON 体正常。否则说明 avatar 服务没启动 / 已崩溃 / 端口被占，通知用户/运维，不要硬跑控制平面端点。
2. **运行身份**：本 skill 只在 owner 的主 p2p session（`p2p_{owner_id}`）里调用才合理。其他 session（专用分身、群聊 session）调控制平面等于越权替 owner 下单——能跑通但绕过了权限边界。

端点只绑定 `127.0.0.1`，外网访问不到；所有调用必须是本机 curl。

## 三个 HTTP 端点

### 1. GET `/sessions/{owner_id}` — 列 owner 名下所有 session

**只读**，可直接调用、不需要用户确认。返回 store 里归属该 owner 的全部 session（含 p2p 与群聊），带实时状态 / task 元数据 / FIFO 未处理消息数。

```bash
curl -s "http://localhost:8420/sessions/{owner_id}"
```

**响应（200）**：

```json
{
  "sessions": [
    {
      "session_id": "p2p_ou_xxx_req-homepage-jsonld-schema",
      "status": "READY",
      "task_id": "recvhqUZJ2eZAI",
      "task_type": "requirement",
      "last_active": "2026-04-24T08:30:00+00:00",
      "pending_count": 0
    },
    {
      "session_id": "p2p_ou_xxx_bug-recommend-empty",
      "status": "PROCESSING",
      "task_id": "bug12345",
      "task_type": "bug",
      "last_active": "2026-04-24T09:10:00+00:00",
      "pending_count": 2
    }
  ]
}
```

**字段说明**：
- `session_id`：形如 `p2p_{owner_id}_{suffix}` 或 `group_*_{owner_id}[_suffix]`
- `status`：见下方状态机
- `task_id` / `task_type`：POST `/create` 时写入的任务元数据，用于与飞书表 cross-reference；无则为 `null`
- `last_active`：ISO-8601 UTC；用于判断停滞时间
- `pending_count`：per-session FIFO 中未处理的飞书消息数；>0 通常意味着 session 在 PROCESSING 中积攒了新消息

**匹配规则**：`_owner_matches` 会把 `p2p_{owner_id}*` 和含 `_{owner_id}` 段的 `group_*` session 都归给这个 owner。其他 owner 的 session 不会返回。

**何时用**：开场盘点、`AskUserQuestion` 前组装证据、cross-reference 飞书表、**派发前检查 suffix 是否已被占用**（见命名规范节）。

### 2. POST `/sessions/{owner_id}/create` — 新建 session 并派发首条消息

**有副作用**：真会启动一个新的 ClaudeSDKClient 子进程并立即派发消息。派发前必须 `AskUserQuestion` 让用户确认。

```bash
curl -s -X POST "http://localhost:8420/sessions/{owner_id}/create" \
  -H "Content-Type: application/json" \
  -d '{
    "suffix": "req-homepage-jsonld-schema",
    "message": "<context block + 期望动作，见下节>",
    "task_id": "recvhqUZJ2eZAI",
    "task_type": "requirement"
  }'
```

**Body 字段**：
- `suffix`（必填，字符串）：session 标识尾缀，会拼成 `p2p_{owner_id}_{suffix}`。**必须匹配白名单正则 `[A-Za-z0-9_\-\.]+`**——空格、中文、`/`、`@` 等一律 400。命名规范见专门一节
- `message`（必填，非空字符串）：首条消息内容。**必须以 context block 起手**（见 §"派发消息体规范"），子 session 是新 Claude 进程，不带任何当前会话上下文，message 是它唯一的入口
- `task_id`（可选，字符串）：写入 store 元数据，供 GET `/sessions` 回读。一般填飞书 record_id 用作回飞书表的反查键
- `task_type`（可选，字符串）：`requirement` / `bug` / `hotfix` / `tech-requirement` 之一

**回传行为（无需配置）**：子 session 处理完成后自动主动发一条消息到 owner 飞书私聊（即 `OWNER_ID`），带 `来自 {suffix} 的回复：\n` 前缀。判定依据是事件 message_id 形如 `internal-*`（控制平面虚构）→ 走主动 send；非 `internal-*`（飞书真实事件）→ 走原 quote-reply。两条路互不干扰，本 skill 调用方不需要传任何字段控制。

**响应**：
- **200**：`{"session_id": "p2p_...", "status": "PROCESSING", "created": true}`——派发已接受
- **400**：body 非 JSON / suffix 非法 / message 缺失或非字符串 / task_id / task_type 类型错误。读 `error` 字段修正重试
- **409**：`session_id` 已存在。调用方应改用 POST `/message` 复用
- **503**：dispatcher 未注入（avatar 服务启动时未挂好）。通知运维，不重试

**语义细节**：
- 200 仅表示**派发已接受**，不代表 Claude 子进程已经处理完。要确认消息是否真的落地，之后用 GET `/sessions/{owner_id}` 观察 `status` 变化
- 同一 suffix 并发 create 存在 TOCTOU 窗口（409 检查 → save 非原子）。调用方侧串行化同一 suffix 的请求

**何时用**：飞书表显示某需求/Bug 在推进阶段、但 GET `/sessions` 里没有对应 session → 新开分身。

### 3. POST `/sessions/{session_id}/message` — 向已存在 session 追加消息

**有副作用**：会真的把消息推进 session 的 FIFO 并唤起 Claude 处理。派发前必须 `AskUserQuestion`。

```bash
curl -s -X POST "http://localhost:8420/sessions/p2p_{owner_id}_req-homepage-jsonld-schema/message" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "<变化部分 + 期望动作，已交付字段可省，见下节>"
  }'
```

**Body 字段**：
- `message`（必填，非空字符串）：消息内容。续推到已接手的 session 时可省略已交付字段、只贴变化部分；首次派发到一个空 session 仍需要完整 context block
- `suffix`（可选，字符串）：仅用于 `来自 {suffix} 的回复：` 前缀；不传则从 session_id 解析

**回传行为**：同 POST `/create`——session 完成 ResultMessage 后自动主动发到 owner 飞书私聊，带 suffix 前缀。无需配置。

**响应**：
- **200**：`{"session_id": "...", "status": "PROCESSING", "queued": true}`
- **400**：body / message 不合法
- **404**：`session_id` 不在 pool.list_sessions()。改用 POST `/create`，或确认 session_id 拼写
- **409**：`pool.get_status(session_id) == "PROCESSING"`。session 正忙，别硬塞；等或告知用户稍后
- **503**：dispatcher 未注入

**语义细节**：
- `sender_id` 内部写死为 `OWNER_ID`（只有主 agent 能调控制平面），这会影响 Claude prompt 中的角色字段
- reader 见到 `internal-*` 形式的 message_id 时跳过原 quote-reply（虚构 ID 不能 reply），改走主动 send 到 owner p2p
- 404 / 409 检查与 dispatch 非原子，并发场景下可能两条同时通过。调用方侧串行化

**何时用**：目标 session 已存在且不在 PROCESSING，需要续推（step N → step N+1、补一条澄清、追问结果）。

## 派发消息体（context block）规范

控制面派发出去的消息是子 session 唯一的入口。子 session 是新 Claude 进程——它不知道你是谁、不知道这条需求在哪干活、不知道 STATUS.md 说了什么。如果 `message` 只写"推进到 step N"，子 session 要么从零盘点（浪费 token 和时间），要么脑补跑偏（编造路径、找错 record）。

**首次派发（POST `/create`）的 `message` 必须以结构化 context block 起手**，再写期望动作：

```
[需求] req-homepage-jsonld-schema
[飞书表 record_id] recvhqUZJ2eZAI
[task-dir] tasks/req-homepage-jsonld-schema/
[Wiki] https://xxx.feishu.cn/wiki/wikcnXXXXXXX
[当前阶段] tripo-requirement step 10（上线收尾）
[STATUS 摘要] step 9/10 已完成；PR #234 已合；已部署 production v2026.04.16；Wiki node_token=wikcnXXXXXXX 已同步
[飞书原文] 所有者私聊："需求已完成上线，请在 tasks/ 目录下完成收尾：1) 更新 STATUS.md 标记完成 2) 检查 Wiki 同步是否完成 3) 发 R4 通知确认上线"

请执行以下动作：
1. Read tasks/req-homepage-jsonld-schema/STATUS.md 核对最新状态
2. 把 step 10 标记为「已完成」，回写更新时间戳
3. 检查 Wiki 是否同步完成（看 STATUS.md 里 node_token，必要时 lark-wiki 复核）
4. 通过 scrum-master 派发 R4 通知确认上线（引用 Wiki URL）
5. 完成后回报：每条任务做了什么、是否阻塞、产物链接
```

### 最小字段集

缺一项子 session 大概率跑偏。每个字段的存在都是为了让子 session 跳过"找入口"这一步：

| 字段 | 来源 | 子 session 用它做什么 |
|---|---|---|
| **需求/Bug suffix** | 调用方约定（业务 slug） | 自我标识，对齐飞书前缀 |
| **飞书 record_id** | 飞书表（产品需求池 / Bug 表） | 用 `tripo-tables` 反查需求记录、拿原始描述 |
| **task-dir** | 本地 `tasks/<task-dir>/` 完整相对路径 | `Read STATUS.md` / `review.md` / `technical-solution.md` 等流程产物 |
| **Wiki URL**（如已建） | STATUS.md 里 `node_token` 或调用方记录 | 读 Wiki 原文、引用到通知里 |
| **当前阶段** | 调用方判断（流程 skill 的 step 编号） | 直接定位流程位置，不用从 step 1 扫起 |
| **STATUS 摘要** | 调用方提取（最近 3-5 条变更 + 当前 step + 关键产物） | 知道前面发生过什么，避免重做 |
| **飞书原文** | 触发本次派发的 owner 消息 | 理解 owner 当前到底要什么——不要让子 session 去猜 |
| **期望动作** | 调用方明示（编号列表） | 知道这次要做什么、做完什么算完、回报什么 |

### 反例

| 错误写法 | 为什么错 |
|---|---|
| `"推进到 step 10"` | 不知道哪个需求、没 task-dir、不知道 STATUS 现状 |
| `"BUG-45 修一下"` | record_id 不是工作目录；子 session 找不到本地 tasks/ |
| `"按上次说的继续"` | 子 session 没有"上次"——它是控制面派发出来的新进程，不知道你说过什么 |
| `"看看 homepage-schema 进度"` | 太开放；子 session 不知道"进度"该读哪份产物、回报到哪里 |

### 续推（POST `/message`）的简化

续推到一个**已经接过手**的 session 时，子 session 已有上文（task-dir、record_id 已在它的对话历史里），context block 可省略已交付字段，只贴**变化部分** + 期望动作：

```
[更新] PR #234 已合并（之前阻塞在 review）
[当前阶段] step 9 → step 10
请推进到 step 10：检查 Wiki 同步 → 发 R4 通知。完成后回报。
```

但**首次派发到一个空 session（POST `/create`）必须完整 context block**，没有例外——子 session 不会读飞书表、不会自动查 tasks 目录，它只能信你 message 里写的。

## Session 状态机速查

`GET /sessions` 返回的 `status` 四态，决定下一步能派什么：

| 状态值 | 含义 | 下一步可派 |
|--------|------|-----------|
| `"NONE"` | session 完全不存在（store 和 _clients 都没有） | POST `/create` |
| `"CREATED"` | store 有元数据，但 SDK client 未建（重启后未 reconnect 的典型态） | POST `/message`——底层 `pool.get()` 会自动用存的 `claude_session_id` 走 `--resume` 恢复 |
| `"READY"` | client 活着，空闲 | POST `/message` |
| `"PROCESSING"` | 已 query 还未收 ResultMessage，忙 | **不派**。告知用户该 session 在跑、等或跳过本轮 |

> `GET /sessions` 只会返回 store 里有记录的 session，所以实际返回列表里不会出现 `"NONE"`；`"NONE"` 只在"调用方按 task_id 反查 session 但列表里没有"时才对调用方有意义——这时路径是走 POST `/create`。

## suffix 命名规范

`suffix` 是 session_id 的尾缀，白名单正则 `[A-Za-z0-9_\-\.]+`（空格、中文、`/`、`@`、`:` 一律 400）。

**新规范：用业务 slug，不用 record_id。**

理由：suffix 直接出现在 session_id（`p2p_{owner}_{suffix}`）和飞书侧前缀（`来自 {suffix} 的回复：`）里，是 owner 唯一会反复读的字段。`REQ-recvhqUZJ2eZAI` 这种飞书内部 ID 让 owner 在多个分身间无法快速区分；改用业务 slug 后 `req-homepage-jsonld-schema` 一眼看出是哪条需求。

### slug 生成原则

- 从需求标题取核心动词/对象，转成 **kebab-case 短英文**（中文标题需主 agent 翻译/缩写）
- 长度 ≤ 30 字符（含连字符），保持 owner 在飞书前缀读起来不刷屏
- 同一 owner 名下 slug 唯一；调用方在派发前 `GET /sessions/{owner_id}` 检查命中——已存在 → 走 POST `/message` 续推（不要换名重开造成 session 分裂）

### 类型前缀（推荐，不强制）

| 任务类型 | 前缀 | 示例 |
|---|---|---|
| 需求 | `req-` | `req-homepage-jsonld-schema` |
| Bug | `bug-` | `bug-recommend-empty` |
| Hotfix | `hotfix-` | `hotfix-cdn-purge-stuck` |
| 技术需求 | `tech-` | `tech-payload-v3-upgrade` |
| 临时/实验 | `exp-` 或纯 slug | `exp-llm-eval-loop` |

slug 自身已能描述任务时可省前缀。**保留前缀不用作业务 slug**：以 `_` 开头的所有名（system-reserved，如 `_dispatch` / `_system`）。

### task_id 与 suffix 解耦

| 字段 | 角色 | 取值 |
|---|---|---|
| **suffix** | 人类辨识（飞书前缀、session_id 一部分） | 业务 slug（如 `req-homepage-jsonld-schema`） |
| **task_id** | 机器反查（cross-reference 飞书表） | 飞书 record_id（如 `recvhqUZJ2eZAI`） |
| **task_type** | 任务类型分类 | `requirement` / `bug` / `hotfix` / `tech-requirement` |

`GET /sessions/{owner_id}` 返回里，session_id 含 slug 易读、task_id 带 record_id 可回飞书表反查，两边都满足。

### 命名样例

| 需求标题 | suffix（slug） | task_id | session_id |
|---|---|---|---|
| 首页结构化数据接入 | `req-homepage-jsonld-schema` | `recvhqUZJ2eZAI` | `p2p_ou_xxx_req-homepage-jsonld-schema` |
| CMS 自动翻译 | `req-cms-auto-translation` | `recveo3GdVelIk` | `p2p_ou_xxx_req-cms-auto-translation` |
| 推荐位空白修复 | `bug-recommend-empty` | `bug12345` | `p2p_ou_xxx_bug-recommend-empty` |
| CDN 清缓卡死 hotfix | `hotfix-cdn-purge-stuck` | `hotfix20260424-01` | `p2p_ou_xxx_hotfix-cdn-purge-stuck` |

### 反例

| 别这么命名 | 为什么 |
|---|---|
| `REQ-recvhqUZJ2eZAI` | record_id 在飞书前缀里读不出业务含义 |
| `req-12345` | 数字编号同样无业务含义 |
| `推荐位空白` | 中文不在白名单 |
| `req-homepage-structured-data-and-jsonld-schema-for-seo` | 太长（>30 字符），飞书前缀刷屏 |

## 错误处理清单

| 响应码 | 场景 | 动作 |
|--------|------|------|
| `400` | body 非 JSON / suffix 不合白名单 / message 为空 / 可选字段类型错 | 读 `error` 字段修正后重试 |
| `404`（message） | `session_id` 不在 store | 改用 POST `/create`，或核对 session_id 拼写 |
| `409`（create） | session 已存在 | 改用 POST `/message` 复用 |
| `409`（message） | session 正在 PROCESSING | 告知用户"该 session 已忙"，等空闲后重试；**不**硬塞第二次 |
| `503` | dispatcher 未注入 | 不应该发生；通知运维排查 avatar 服务启动流程，不重试 |
| Connection refused / timeout | avatar 服务未运行或已崩 | 不重试；先 `curl /api/status` 探活，通知运维 |

## 典型工作流

### 场景 A：用户问"看看今天哪些需求停滞了"

1. **查飞书表**——派 scrum-master（加载 `tripo-tables`）读产品需求池 / 技术需求池 / Bug 表 / Hotfix 表，筛出 owner 名下仍在推进阶段（非"已完成"、非"未启动"）的记录列表，**带回每条的：业务标题、record_id、当前流程阶段、task-dir 名、Wiki URL（如有）、最新 STATUS 摘要**——这些是后续 context block 的原料
2. **查控制平面**——curl `GET /sessions/{owner_id}` 拿 session 清单
3. **cross-reference**——按 task_id 对齐两份列表：
   - 表里有、控制平面 NONE（未返回）→ 候选 "新建 session（POST /create）"，调用方为这条需求生成 slug
   - 表里有、控制平面 `CREATED` 或 `READY` → 候选 "续推（POST /message）"
   - 表里有、控制平面 `PROCESSING` → 跳过本轮，标注"该 session 正在跑"
4. **向用户汇报 plan**（不直接派发）：列出打算 create 哪些（含拟定 slug）、message 哪些、跳过哪些，用 `AskUserQuestion` 让用户勾选确认
5. **用户确认后串行派发**：对每条 create 组装完整 context block（最小字段集），对 message 组装变化部分；同一 suffix / session_id 一次只发一条，检查响应后再发下一条。子 session 处理完后回报会自动出现在 owner 飞书 p2p（带前缀），无需额外配置

### 场景 B：用户明确说"把 X 推一下"

1. **解析 X**——X 可能是 slug（`homepage-schema`）、record_id（`recvhqUZJ2eZAI`）、或自然语言描述。先派 scrum-master 在飞书表里定位到那条记录，拿到完整字段（含 task-dir、Wiki、STATUS 摘要、最近一条飞书原文）
2. **查 session 状态**——curl `GET /sessions/{owner_id}`，按 `task_id == record_id` 或 `session_id` 含已知 slug 找条目
3. **按状态分支**：
   - 没找到（视为 `NONE`）→ `AskUserQuestion` 让用户确认拟定 slug + context block 内容；确认后 POST `/create`
   - `CREATED` / `READY` → 组装变化部分 + 期望动作的简化 message，`AskUserQuestion` 确认后 POST `/message`
   - `PROCESSING` → 告诉用户"该 session 在跑，pending_count=N，建议等它跑完"；不派发
4. **派发后**再 curl `GET /sessions/{owner_id}` 观察 status 从 PROCESSING 回到 READY；owner 会在飞书 p2p 看到子 session 的回传消息（带 `来自 {suffix} 的回复：` 前缀）

### 场景 C：用户问"今天哪些 session 在跑"

1. curl `GET /sessions/{owner_id}`
2. 过滤 `status == "PROCESSING"` 的条目
3. 按 `last_active` 倒序列出 task_id / task_type / pending_count 给用户
4. **只读**，不需要 AskUserQuestion

### 场景 D：tripo-requirement / tripo-bugfix 流程里跨 session 续推

流程 skill 的某一步要求"通知分身 session 继续 step N"时：

1. 流程层把任务 ID / task-dir / 当前 step / 变化部分整理好，传给调用本 skill 的上下文
2. curl `GET /sessions/{owner_id}` 确认目标 session 的 status
3. 按 A/B 场景的分支处理；首次派发完整 context block，续推用变化部分；PROCESSING 时阻塞，返回给流程 skill 让它等

## 与其他 skill 的关系

| 关联 skill | 关系 |
|-----------|------|
| `tripo-tables`（scrum-master 用） | 提供飞书表数据；本 skill 的 cross-reference 基础，**也是 context block 字段的源头** |
| `tripo-task-dirs`（scrum-master 用） | 维护 tasks/<task-dir>/ 生命周期；context block 中的 task-dir 字段由它定义 |
| `tripo-notify`（scrum-master 用） | 派发完后若要发 R1-R4 / B1-B2 通知，由流程 skill 决定节点，不是本 skill 的事 |
| `tripo-requirement` / `tripo-bugfix` | 流程编排；本 skill 被流程 skill 在"需要跨 session 续推"时调用 |
| `tripo-release` | 发车流程；`release` specialist 在本 session 内完成，通常不需要控制平面派发 |

## 铁律

1. **所有有副作用的派发前必须 `AskUserQuestion`**——POST `/create` 和 POST `/message` 都是真正触发 Claude 子进程工作的动作，用户得明确"好"才派。`GET` 只读例外
2. **不硬塞 PROCESSING**——遇到 409 不重试，不构造 `/interrupt`（当前阶段不在本 skill 范围），告知用户等待或跳过
3. **控制平面不替代飞书**——发通知 / 改表格 / 回复用户，都不是本 skill 的事；本 skill 只管"让目标 session 动起来"
4. **不脑补 task_id**——调用方要知道 task_id 是什么（从飞书表或用户指令拿），不要凭 session_id 反解
5. **suffix 不偷懒**——白名单严格、用业务 slug、长度受控；调用前自己本地校验过再发
6. **派发后要观测**——200 只是"派发已接受"，真正确认 Claude 处理得靠后续 `GET /sessions` 看 status 翻转和 pending_count 变化
7. **派发不下沉**——子 session 是新 Claude 进程，没有当前会话的上下文。POST `/create` 的 message 必须包含完整 context block（最小字段集见 §"派发消息体规范"）；偷懒省字段 = 子 session 跑偏 / 找不到 task-dir / 编路径
8. **回传是内置行为，不要试图"配置"**——session 处理完后会自动主动发到 owner 飞书私聊（带 `来自 {suffix} 的回复：` 前缀）。本 skill 不接受 `echo_chat_id` 之类的字段控制目标——之前有过这种过度设计已被删除。如果未来真有需求发到群或第三方，再加新字段，**不要在 message body 里偷偷塞老字段**（server 会静默忽略未知字段）

## 示例对话片段

### 例 1：盘点停滞需求

> 用户："看看今天哪些需求停了"

主 agent 的内在流程：

1. 派 scrum-master 查飞书表拿"状态 ∈ {开发/交付中, 验收/提测中}"的 owner 名下需求，**带回完整字段**：
   - REQ-1：标题"首页结构化数据"、record_id `recvhqUZJ2eZAI`、task-dir `tasks/req-homepage-jsonld-schema/`、Wiki `wikcnAAAA`、step 9（PR review 中）
   - REQ-2：标题"CMS 自动翻译"、record_id `recveo3GdVelIk`、task-dir `tasks/req-cms-auto-translation/`、Wiki `wikcnBBBB`、step 8（提测）
   - REQ-3：标题"推荐位修复"、record_id `bug12345`、task-dir `tasks/bug-recommend-empty/`、step 4（修复中）
2. 本 skill：`curl -s http://localhost:8420/sessions/ou_xxx`，返回：
   - `p2p_ou_xxx_req-homepage-jsonld-schema` status=READY, last_active=2 天前
   - `p2p_ou_xxx_req-cms-auto-translation` status=PROCESSING, last_active=5 分钟前
   - （`bug-recommend-empty` 未返回）
3. 汇报用户：
   - REQ-1（首页结构化数据）停了 2 天，建议 POST `/message` 续推到 step 10
   - REQ-2（CMS 自动翻译）在跑中，跳过
   - REQ-3（推荐位修复）无 session，建议 POST `/create`，slug=`bug-recommend-empty`、首条 message 为完整 context block
4. `AskUserQuestion`：勾选 REQ-1 + REQ-3，确认 message 内容（context block 已组装好预览给用户）
5. 用户确认后按顺序 curl POST：
   - REQ-1：POST `/message`，body 含变化部分 + 期望动作
   - REQ-3：POST `/create`，body 含完整 context block + slug + task_id
6. 查 `GET /sessions` 验证 status 翻转；告诉用户子 session 的回报会出现在 owner p2p 飞书里

### 例 2：单点推进

> 用户："把 homepage-schema 推一下"

主 agent：

1. 派 scrum-master 解析"homepage-schema" → 飞书表定位到"首页结构化数据"，拿到 record_id `recvhqUZJ2eZAI`、task-dir `tasks/req-homepage-jsonld-schema/`、Wiki `wikcnAAAA`、当前 step 9（PR 已合，待提测）、最近一条飞书原文
2. `curl -s http://localhost:8420/sessions/ou_xxx`，找到 `p2p_ou_xxx_req-homepage-jsonld-schema` status=CREATED（重启后未 reconnect）
3. 组装 message（续推简化版）：

   ```
   [更新] PR #234 已合并；最新 staging 部署已通过冒烟
   [当前阶段] step 9 → step 10（上线收尾）
   [STATUS 摘要] 见 tasks/req-homepage-jsonld-schema/STATUS.md（你已有上下文）
   请推进到 step 10：检查 Wiki node_token 是否同步、通过 scrum-master 派 R4 通知。完成后回报。
   ```
4. `AskUserQuestion`：建议消息预览给用户 + 提示"回报会出现在你的飞书私聊"——用户选"确认派发"
5. `curl -s -X POST http://localhost:8420/sessions/p2p_ou_xxx_req-homepage-jsonld-schema/message -H "Content-Type: application/json" -d '{"message": "..."}'`，返回 200 `status=PROCESSING`
6. 回报用户："homepage-schema 已派发，status=PROCESSING；子 session 回报会带 `来自 req-homepage-jsonld-schema 的回复：` 前缀出现在你的飞书 p2p。"
