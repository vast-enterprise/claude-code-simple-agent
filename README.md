# Tripo Avatar

基于 Claude Code SDK 的飞书数字分身，自动响应飞书消息并执行技术任务。

## 前置条件

- Python >= 3.12
- [lark-cli](https://github.com/nicepkg/lark-cli) 已安装并登录
- Claude Code CLI 已安装

## 安装

```bash
pip install -e .
```

## 配置

复制配置模板并填写：

```bash
cp config.example.json config.json
```

| 字段 | 说明 |
|------|------|
| `owner_open_id` | 飞书 owner 的 open_id，拥有完整权限 |
| `owner_name` | 显示名称 |
| `bot_name` | 飞书机器人名称，用于群聊 @mention 匹配 |
| `model` | Claude 模型（opus / sonnet） |
| `effort` | 推理力度（max / high / low） |
| `env` | 传递给 Claude SDK 的环境变量 |

## 启动

```bash
python3 -m src.main
```

开启详细日志（显示 client 创建等内部细节）：

```bash
AVATAR_DEBUG=1 python3 -m src.main
```

## 日志级别

| 级别 | 内容 | 何时显示 |
|------|------|----------|
| INFO | 启动、收到消息、关闭 | 始终 |
| DEBUG | pool 创建 client 等内部细节 | `AVATAR_DEBUG=1` |
| ERROR | 回复失败、断连失败 | 始终 |

## 残余进程清理

Avatar 退出后可能残留 claude 子进程。查找并清理：

```bash
# 查看残余 claude 进程
ps aux | grep -E 'claude' | grep -v grep

# 查看残余 lark-cli 事件监听进程
ps aux | grep -E 'lark-cli.*event.*subscribe' | grep -v grep

# 杀掉所有残余 claude 进程
pkill -f 'claude'

# 杀掉残余 lark-cli 事件监听
pkill -f 'lark-cli.*event.*subscribe'

# 一键清理全部
pkill -f 'claude'; pkill -f 'lark-cli.*event.*subscribe'
```

## 测试

```bash
python3 -m pytest src/__tests__/ -v
```

## 架构

```
飞书消息 → lark-cli (WebSocket) → main.py (事件循环)
                                      ↓
                                SessionDispatcher (per-session 串行)
                                      ↓
                                handler.py → ClientPool → ClaudeSDKClient (per-session 独立进程)
                                      ↓
                                lark-cli (回复消息)
```

每个用户/群聊会话拥有独立的 Claude 进程，实现真正的上下文隔离。

## 项目结构

```
src/
├── main.py          # 入口：事件循环、信号处理、进程清理
├── handler.py       # 消息过滤 + 处理：should_respond / handle_message
├── pool.py          # ClientPool：per-session 独立 ClaudeSDKClient
├── session.py       # SessionDispatcher：per-session 队列 + worker
├── permissions.py   # 工具调用权限门控
├── lark.py          # 飞书交互：回复消息、表情反馈
├── config.py        # 配置加载 + 日志初始化
└── __tests__/       # 单元测试
```
