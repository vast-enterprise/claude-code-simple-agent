---
name: tripo-dispatch
description: |
  调度会话派发：通过 HTTP 控制平面（localhost:8420）查询 / 创建 / 激活 owner 的需求 session，
  主动推进停滞的需求或 Bug。用户说"看看今天哪些需求停滞了"/"把 REQ-XXX 推一下"/"查一下我的所有 session"时触发。

  被调用场景：
  - 用户在飞书主会话问"哪些需求在 pending / 今天有哪些在跑"
  - 用户要求主动推进某个停滞需求（"把 REQ-123 推一下"、"让 X 继续"）
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
      "session_id": "p2p_ou_xxx_REQ-123",
      "status": "READY",
      "task_id": "REQ-123",
      "task_type": "requirement",
      "last_active": "2026-04-24T08:30:00+00:00",
      "pending_count": 0
    },
    {
      "session_id": "p2p_ou_xxx_BUG-45",
      "status": "PROCESSING",
      "task_id": "BUG-45",
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

**何时用**：开场盘点、`AskUserQuestion` 前组装证据、cross-reference 飞书表。

### 2. POST `/sessions/{owner_id}/create` — 新建 session 并派发首条消息

**有副作用**：真会启动一个新的 ClaudeSDKClient 子进程并立即派发消息。派发前必须 `AskUserQuestion` 让用户确认。

```bash
curl -s -X POST "http://localhost:8420/sessions/{owner_id}/create" \
  -H "Content-Type: application/json" \
  -d '{
    "suffix": "REQ-123",
    "message": "请从 PRD 第 2 节继续，检查 tasks/REQ-123/STATUS.md 更新到 step 5。",
    "task_id": "REQ-123",
    "task_type": "requirement"
  }'
```

**Body 字段**：
- `suffix`（必填，字符串）：session 标识尾缀，会拼成 `p2p_{owner_id}_{suffix}`。**必须匹配白名单正则 `[A-Za-z0-9_\-\.]+`**——空格、中文、`/`、`@` 等一律 400。白名单避免与飞书侧 `/new {suffix}` / `$suffix` 命令解析冲突
- `message`（必填，非空字符串）：首条消息内容
- `task_id`（可选，字符串）：写入 store 元数据，供 GET `/sessions` 回读
- `task_type`（可选，字符串）：同上

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
curl -s -X POST "http://localhost:8420/sessions/p2p_{owner_id}_REQ-123/message" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "上次你停在 step 6，PR 已合，请推进到 step 7 的测试环节。"
  }'
```

**Body 字段**：
- `message`（必填，非空字符串）：消息内容
- `suffix`（可选，字符串）：reader 回复前缀。control-plane 场景（`internal-*` message_id）reader 的 lark 侧副作用被 handler 屏蔽，此参数实际不生效，只为与 `/create` 对称保留

**响应**：
- **200**：`{"session_id": "...", "status": "PROCESSING", "queued": true}`
- **400**：body / message 不合法
- **404**：`session_id` 不在 pool.list_sessions()。改用 POST `/create`，或确认 session_id 拼写
- **409**：`pool.get_status(session_id) == "PROCESSING"`。session 正忙，别硬塞；等或告知用户稍后
- **503**：dispatcher 未注入

**语义细节**：
- `sender_id` 内部写死为 `OWNER_ID`（只有主 agent 能调控制平面），这会影响 Claude prompt 中的角色字段，但不影响飞书侧（因 `internal-` message_id 会屏蔽 lark 反馈）
- 404 / 409 检查与 dispatch 非原子，并发场景下可能两条同时通过。调用方侧串行化

**何时用**：目标 session 已存在且不在 PROCESSING，需要续推（step N → step N+1、补一条澄清、追问结果）。

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

`suffix` 是 session_id 的尾缀，白名单正则 `[A-Za-z0-9_\-\.]+`：

- **需求**：`REQ-{ID}`（与飞书需求表的记录 ID / 业务编号对齐）
- **Bug**：`BUG-{ID}`
- **Hotfix**：`HOTFIX-{ID}`
- **技术需求**：`TECH-{ID}`
- **临时/实验会话**：用户指定的任意合法尾缀

禁用：空格、中文字符、`/`、`@`、`:`、任何非白名单字符；保留（不要用作业务 suffix）：`_dispatch`、`_system` 等下划线前缀的 system-reserved 名。

`task_id` / `task_type` 可以和 suffix 解耦写——suffix 用于 session 标识，task_id/task_type 是给 `GET /sessions` 回读时做 cross-reference 用的业务元数据。一般让二者对齐（suffix=`REQ-123`、task_id=`REQ-123`、task_type=`requirement`）最省心。

## task_id / task_type 语义

- **task_id**：需求/Bug 的业务唯一标识。格式参考飞书表或任务目录名，例如 `REQ-12345` / `BUG-678` / `HOTFIX-20260424-01`
- **task_type**：任务类型，与飞书表的用途对齐。典型值：`requirement` / `bug` / `hotfix` / `tech-requirement`
- 这两个字段**只在 POST `/create` 的 body 里提供**，POST `/message` 不接受（续推不需要再写元数据）
- `GET /sessions` 会把它们回传，便于 cross-reference 飞书表拿到的需求列表 / Bug 列表

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

1. **查飞书表**——派 scrum-master（加载 `tripo-tables`）读产品需求池 / 技术需求池 / Bug 表 / Hotfix 表，筛出 owner 名下仍在推进阶段（非"已完成"、非"未启动"）的记录列表
2. **查控制平面**——curl `GET /sessions/{owner_id}` 拿 session 清单
3. **cross-reference**——按 task_id 对齐两份列表：
   - 表里有、控制平面 NONE（未返回）→ 候选 "新建 session（POST /create）"
   - 表里有、控制平面 `CREATED` 或 `READY` → 候选 "续推（POST /message）"
   - 表里有、控制平面 `PROCESSING` → 跳过本轮，标注"该 session 正在跑"
4. **向用户汇报 plan**（不直接派发）：列出打算 create 哪些、message 哪些、跳过哪些，用 `AskUserQuestion` 让用户勾选确认
5. **用户确认后串行派发**：对同一 suffix / session_id 一次只发一条，检查响应后再发下一条

### 场景 B：用户明确说"把 REQ-XXX 推一下"

1. **先查状态**——curl `GET /sessions/{owner_id}`，在返回里找 `session_id` 含 `REQ-XXX`（或 `task_id == "REQ-XXX"`）的条目
2. **按状态分支**：
   - 没找到（视为 `NONE`）→ `AskUserQuestion` 让用户确认"新建 session 并发首条消息（建议内容：...）"；确认后 POST `/create`，suffix=`REQ-XXX`、task_id=`REQ-XXX`、task_type=`requirement`
   - `CREATED` / `READY` → `AskUserQuestion` 让用户确认消息内容；确认后 POST `/message`
   - `PROCESSING` → 告诉用户"REQ-XXX 的 session 在跑，pending_count=N，建议等它跑完"；不派发
3. **派发后**再 curl `GET /sessions/{owner_id}` 观察 status 从 PROCESSING 回到 READY，向用户回报结果

### 场景 C：用户问"今天哪些 session 在跑"

1. curl `GET /sessions/{owner_id}`
2. 过滤 `status == "PROCESSING"` 的条目
3. 按 `last_active` 倒序列出 task_id / task_type / pending_count 给用户
4. **只读**，不需要 AskUserQuestion

### 场景 D：tripo-requirement / tripo-bugfix 流程里跨 session 续推

流程 skill 的某一步要求"通知分身 session 继续 step N"时：

1. 流程层把任务 ID / 要发的消息整理好，传给调用本 skill 的上下文
2. curl `GET /sessions/{owner_id}` 确认目标 session 的 status
3. 按 A/B 场景的分支处理；PROCESSING 时阻塞，返回给流程 skill 让它等

## 与其他 skill 的关系

| 关联 skill | 关系 |
|-----------|------|
| `tripo-tables`（scrum-master 用） | 提供飞书表数据；本 skill 的 cross-reference 基础 |
| `tripo-notify`（scrum-master 用） | 派发完后若要发 R1-R4 / B1-B2 通知，由流程 skill 决定节点，不是本 skill 的事 |
| `tripo-requirement` / `tripo-bugfix` | 流程编排；本 skill 被流程 skill 在"需要跨 session 续推"时调用 |
| `tripo-release` | 发车流程；`release` specialist 在本 session 内完成，通常不需要控制平面派发 |

## 铁律

1. **所有有副作用的派发前必须 `AskUserQuestion`**——POST `/create` 和 POST `/message` 都是真正触发 Claude 子进程工作的动作，用户得明确"好"才派。`GET` 只读例外
2. **不硬塞 PROCESSING**——遇到 409 不重试，不构造 `/interrupt`（当前阶段不在本 skill 范围），告知用户等待或跳过
3. **控制平面不替代飞书**——发通知 / 改表格 / 回复用户，都不是本 skill 的事；本 skill 只管"让目标 session 动起来"
4. **不脑补 task_id**——调用方要知道 task_id 是什么（从飞书表或用户指令拿），不要凭 session_id 反解
5. **suffix 不偷懒**——白名单严格，空格和中文必 400；调用前自己本地校验过再发
6. **派发后要观测**——200 只是"派发已接受"，真正确认 Claude 处理得靠后续 `GET /sessions` 看 status 翻转和 pending_count 变化

## 示例对话片段

### 例 1：盘点停滞需求

> 用户："看看今天哪些需求停了"

主 agent 的内在流程：

1. 派 scrum-master 查飞书表拿"状态 ∈ {开发/交付中, 验收/提测中}"的 owner 名下需求，拿到 REQ-101 / REQ-102 / REQ-108
2. 本 skill：`curl -s http://localhost:8420/sessions/ou_xxx`，返回：
   - `p2p_ou_xxx_REQ-101` status=READY, last_active=2 天前
   - `p2p_ou_xxx_REQ-102` status=PROCESSING, last_active=5 分钟前
   - （REQ-108 未返回）
3. 汇报用户：
   - REQ-101 停了 2 天，建议 POST `/message` 续推
   - REQ-102 在跑中，跳过
   - REQ-108 无 session，建议 POST `/create` 开分身
4. `AskUserQuestion`：勾 REQ-101 和 REQ-108，确认消息内容
5. 用户确认后按顺序 curl POST，查 `GET /sessions` 验证 status 翻转
6. 向用户回报派发结果

### 例 2：单点推进

> 用户："把 BUG-45 推一下"

主 agent：

1. `curl -s http://localhost:8420/sessions/ou_xxx`，找到 `p2p_ou_xxx_BUG-45` status=CREATED（典型重启后未 reconnect）
2. `AskUserQuestion`：建议消息"上次你停在 step 4，已合 PR，请推进到 step 5 的验证"——用户选"确认派发"
3. `curl -s -X POST http://localhost:8420/sessions/p2p_ou_xxx_BUG-45/message -H "Content-Type: application/json" -d '{"message": "..."}'`，返回 200 `status=PROCESSING`
4. 回报用户："BUG-45 已派发，status=PROCESSING，等 session 跑完后会自己停在 READY"
