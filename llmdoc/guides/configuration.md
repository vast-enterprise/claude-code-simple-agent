# How to 配置与部署 Digital Avatar

从零初始化配置、设置环境变量、配置飞书开放平台，到启动服务的完整流程。

## 1. 初始化 config.json

1. 复制模板文件：`cp config.example.json config.json`
2. 编辑 `config.json`，填写所有字段（字段说明见下方）。
3. 确认 `config.json` 已被 `.gitignore` 排除（已默认配置），绝不提交到版本控制。

加载逻辑见 `src/config.py:34-39` — 文件不存在时 `exit(1)` 并提示。

## 2. config.json 字段说明

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `owner_open_id` | string | — | 飞书所有者的 open_id（`ou_xxx` 格式），用于权限判断 |
| `owner_name` | string | — | 所有者姓名，启动日志显示用 |
| `model` | string | `"opus"` | Claude 模型选择：`opus` / `sonnet` / `haiku` |
| `effort` | string | `"max"` | 推理 effort 级别，传入 `ClaudeAgentOptions` |
| `max_turns` | number | `100` | 单次对话最大轮次 |
| `env` | object | — | 环境变量子对象，注入 Claude SDK 子进程（见下方） |
| `notify` | object | `{"enabled": false}` | 飞书异常通知配置（见下方） |

## 3. 环境变量配置（env 子对象）

`config.json` 的 `env` 字段中的键值对会在运行时注入 Claude SDK 子进程。空字符串的键会被过滤掉。

过滤逻辑见 `src/main.py:58`。

| 变量 | 用途 |
|------|------|
| `ANTHROPIC_BASE_URL` | API 代理地址（直连 Anthropic 可留空） |
| `ANTHROPIC_AUTH_TOKEN` | API 认证 Token |
| `ANTHROPIC_MODEL` | SDK 使用的模型标识 |
| `ANTHROPIC_DEFAULT_HAIKU_MODEL` | Haiku 模型 ID |
| `ANTHROPIC_DEFAULT_SONNET_MODEL` | Sonnet 模型 ID |
| `ANTHROPIC_DEFAULT_OPUS_MODEL` | Opus 模型 ID |

## 3b. 异常通知配置（notify 子对象）

`config.json` 的 `notify` 字段控制飞书异常通知行为。加载逻辑见 `src/config.py:57`。

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `enabled` | boolean | `false` | 是否启用异常通知 |
| `receive_id` | string | — | 通知接收方 ID（`ou_xxx` 格式） |
| `receive_id_type` | string | `"open_id"` | 接收方 ID 类型 |

通知触发场景：进程崩溃（`sys.excepthook`）、lark-cli 断连。60 秒内同类通知自动节流。

## 3c. .env 文件

项目支持 `.env` 文件存放敏感密钥（已被 `.gitignore` 排除）。

| 变量 | 用途 |
|------|------|
| `CMS_STAGING_API_KEY` | CMS staging 环境 API Key |
| `CMS_PROD_API_KEY` | CMS production 环境 API Key |

## 4. 修改 persona.md

`persona.md` 定义数字分身的人格、语气、能力边界和权限规则。运行时由 `src/config.py:40` 读取为纯文本，通过 `SystemPromptPreset(append=PERSONA + HEADLESS_RULES)` 注入 Claude SDK 系统提示。

修改步骤：
1. 编辑项目根目录的 `persona.md`。
2. 按现有结构修改对应章节（身份 / 语气 / OKR / 能力边界 / 权限规则 / 回复格式）。
3. 重启服务生效，无需改动代码。

## 5. 飞书开放平台前置配置

启动前需在飞书开放平台完成：
1. 创建企业自建应用，获取 App ID 和 App Secret。
2. 开通权限：`im:message`（消息读取）、`im:message:send_as_bot`（机器人发消息）、`im:resource`（资源访问）。
3. 配置事件订阅：订阅 `im.message.receive_v1` 事件。
4. 确保 `lark-cli` 已安装并完成 bot 身份认证（`lark-cli auth`）。

事件监听启动见 `src/main.py:22-31` — 通过 `lark-cli event +subscribe` 子进程实现。

## 6. 日志级别配置

项目使用 `logging.getLogger("avatar")` 统一日志系统，替代 `print(stderr)`。

| 环境变量 | 值 | 效果 | 配置位置 |
|----------|-----|------|----------|
| `AVATAR_DEBUG` | `1`（或任意非空值） | 开启 DEBUG 级别日志（含 Claude session ID、client 创建等） | `src/config.py:11-14` |
| 未设置 | — | 默认 INFO 级别 | `src/config.py:13-14` |

统一日志函数：`log_debug()`、`log_info()`、`log_error()`，均定义于 `src/config.py:20-29`，各模块通过 `from src.config import log_*` 使用。

```bash
# 启用详细日志
AVATAR_DEBUG=1 python3 src/main.py
```

## 7. 启动服务

```bash
cd /Users/macbookair/Desktop/projects/tripo-work-center
python3 src/main.py
```

启动后会输出所有者、工作目录、模型信息，启动 HTTP API server（`http://localhost:8420`），然后进入飞书事件监听循环。`Ctrl+C` 或 `SIGTERM` 触发优雅关闭（asyncio-native 信号处理）。

Session 数据持久化到 `data/sessions.json`（`data/` 目录已被 `.gitignore` 排除，自动创建）。

## 8. 密钥安全

`.gitignore` 已排除 `config.json`、`.env` 和 `data/` 目录。

验证方式：`git status` 确认 `config.json`、`.env`、`data/` 不在 untracked/modified 列表中。如果意外提交，立即轮换 `ANTHROPIC_AUTH_TOKEN`、CMS API Key 等敏感值。
