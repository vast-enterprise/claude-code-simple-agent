# 数字分身（Digital Avatar）设计文档

## 定位

基于飞书机器人 + Claude Code SDK，在工作群中作为郭凯南的数字分身自主应答和执行任务。

## 核心原则

- **最少代码**：~50 行 Python 主进程，配置驱动
- **复用现有体系**：cwd 指向 tripo-work-center，自动加载 CLAUDE.md + 全部 skill
- **本地先跑通**：Mac 常驻进程，后续再考虑服务端

## 架构

```
lark-cli event +subscribe          ClaudeSDKClient
  (WebSocket 常驻)                   (cwd=tripo-work-center)
       │                                  │
       │  im.message.receive_v1           │  自动加载:
       │  --compact --quiet               │  - CLAUDE.md
       ▼                                  │  - 全部 skill
  ┌──────────┐                            │  - setting_sources
  │ avatar.py│───query(msg, session)────▶ │
  │  (~50行) │◀──receive_response()────── │
  └──────────┘                            │
       │                                  │
       ▼                                  │
  lark-cli im +messages-reply             │
    --as bot                              │
```

## 组件清单

### 1. avatar.py — 主进程（~50 行）

职责：
- 启动 `lark-cli event +subscribe` 子进程，监听 `im.message.receive_v1`
- 过滤：只处理 @bot 的消息
- 提取 sender_id、chat_id、content、message_id
- 调用 `ClaudeSDKClient.query()`，session_id 按 chat_id 隔离
- 收到 ResultMessage 后，调用 `lark-cli im +messages-reply` 回复

### 2. persona.md — 人格定义

注入到 `system_prompt`，包含：
- 身份：郭凯南的数字分身，Tripo 前端团队
- 语气：专业、简洁、有边界感，偶尔幽默
- OKR：当前季度的工作目标（可定期更新）
- 边界规则：
  - 不回答与工作无关的问题
  - 不执行不合理的需求（解释原因）
  - 敏感操作（部署、合并、删除）仅限所有者
  - 不确定时说"我不确定，等凯南回来确认"

### 3. 权限分级 — can_use_tool 回调

```python
OWNER_OPEN_ID = "ou_xxx"  # 郭凯南的 open_id

async def permission_gate(tool_name, tool_input, context):
    sender_id = context.get("sender_id")  # 从消息上下文传入

    # Bash 工具中的敏感操作
    if tool_name == "Bash":
        cmd = tool_input.get("command", "")
        sensitive_patterns = ["deploy", "git push", "git merge", "rm -rf", "drop"]
        if any(p in cmd for p in sensitive_patterns):
            if sender_id != OWNER_OPEN_ID:
                return PermissionResultDeny(reason="仅所有者可执行敏感操作")

    return PermissionResultAllow()
```

### 4. 现有 skill 复用

主 Agent 在 tripo-work-center 启动，通过 `setting_sources=["project"]` 加载 CLAUDE.md。
Claude Code 自动发现所有 skill，根据消息内容自主决定调用：

| 用户消息 | 触发 skill | 执行动作 |
|---------|-----------|---------|
| "REQ-xxx 什么状态？" | tripo-tables | 查飞书多维表格 |
| "部署 staging" | tripo-release | 触发 staging 部署 |
| "这个需求的 PR 在哪？" | tripo-requirement | 查任务目录 |
| "帮我查一下 cms 仓库结构" | tripo-repos | 返回仓库信息 |
| "今天有什么会？" | (Bash → lark-cli) | 查日历 |

### 5. 飞书配置前置条件

在飞书开放平台控制台：
1. 事件订阅 → 选择"使用长连接接收事件"
2. 添加事件：`im.message.receive_v1`
3. 开通权限：`im:message:receive_as_bot`、`im:message` (发消息)

## 消息处理流程

```
1. lark-cli event +subscribe 收到消息 (NDJSON)
2. avatar.py 解析 JSON：
   - chat_id, sender_id, content, message_id, chat_type
3. 过滤：
   - 忽略 bot 自己发的消息（防循环）
   - 群聊中只响应 @bot 的消息
   - P2P 直接响应
4. 组装 prompt：
   "[{sender_name}] 在 [{chat_name}] 说：{content}"
5. client.query(prompt, session_id=chat_id)
6. 收集 ResultMessage.result
7. lark-cli im +messages-reply --message-id {id} --as bot --text "{result}"
```

## 文件结构

```
tripo-work-center/
├── avatar/
│   ├── avatar.py          # 主进程 (~50行)
│   ├── persona.md         # 人格定义
│   └── config.json        # 运行配置（owner_id、模型选择等）
├── CLAUDE.md              # 已有，自动加载
└── .claude/skills/        # 已有，自动加载
```

## 启动方式

```bash
cd /Users/macbookair/Desktop/projects/tripo-work-center
python3 avatar/avatar.py
```

## MVP 范围

- 单 session 串行处理（所有消息共用 default session）
- @bot 触发 + P2P 直接响应
- 人格注入 + 权限分级
- 复用现有 skill 体系

## 后续迭代方向

| 方向 | 说明 | 优先级 |
|------|------|--------|
| 多 session 隔离 | 按 单聊/群聊 + 交互用户 分配不同 session_id | P1 |
| 并发排队 | 同一 session 的并发请求串行排队，或走 Claude Code 默认排队机制 | P1 |
| 进程重连 | SDK 子进程崩溃后自动重连 | P1 |
| 多会话可观测性 | session 列表、活跃状态、token 消耗监控 | P2 |
| 消息长度处理 | 长回复分段或转 Markdown 卡片 | P2 |
| 费用控制 | max_budget_usd / max_turns 防单次失控 | P2 |
| 服务端部署 | 迁移到容器，7x24 运行 | P3 |
