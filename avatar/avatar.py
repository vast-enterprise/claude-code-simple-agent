#!/usr/bin/env python3
"""Tripo Digital Avatar — 飞书机器人数字分身 MVP"""

import asyncio
import json
import os
import signal
import subprocess
import sys
from pathlib import Path

from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions
from claude_agent_sdk.types import (
    AssistantMessage, ResultMessage, TextBlock, PermissionResultAllow, PermissionResultDeny,
    ToolPermissionContext, SystemPromptPreset,
)

ROOT = Path(__file__).resolve().parent.parent
_config_path = Path(__file__).parent / "config.json"
if not _config_path.exists():
    print("错误：请先复制 config.example.json 为 config.json 并填写配置", file=sys.stderr)
    sys.exit(1)
CONFIG = json.loads(_config_path.read_text())
PERSONA = (Path(__file__).parent / "persona.md").read_text()

OWNER_ID = CONFIG["owner_open_id"]
SENSITIVE = ["deploy", "git push", "git merge", "git reset", "rm -rf", "drop "]

# WARNING: 全局状态，仅适用于串行处理。并发迭代时必须改为 per-request context 传递。
_current_sender_id: str | None = None


async def permission_gate(
    tool_name: str, tool_input: dict, context: ToolPermissionContext
) -> PermissionResultAllow | PermissionResultDeny:
    """非所有者禁止敏感操作"""
    if tool_name == "Bash" and _current_sender_id != OWNER_ID:
        cmd = tool_input.get("command", "")
        if any(p in cmd for p in SENSITIVE):
            return PermissionResultDeny(
                message="这个操作需要凯南本人确认，我没有权限执行。"
            )
    return PermissionResultAllow()


def add_reaction(message_id: str, emoji_type: str = "OnIt") -> str | None:
    """给消息打表情回复，返回 reaction_id 用于后续删除"""
    params = json.dumps({"message_id": message_id})
    data = json.dumps({"reaction_type": {"emoji_type": emoji_type}})
    result = subprocess.run(
        [
            "lark-cli", "im", "reactions", "create",
            "--params", params, "--data", data, "--as", "bot",
        ],
        capture_output=True, text=True, timeout=10,
    )
    if result.returncode == 0:
        try:
            resp = json.loads(result.stdout)
            return resp.get("data", {}).get("reaction_id")
        except (json.JSONDecodeError, KeyError):
            pass
    return None


def remove_reaction(message_id: str, reaction_id: str):
    """移除消息上的表情回复"""
    params = json.dumps({"message_id": message_id, "reaction_id": reaction_id})
    result = subprocess.run(
        [
            "lark-cli", "im", "reactions", "delete",
            "--params", params, "--as", "bot",
        ],
        capture_output=True, text=True, timeout=10,
    )
    if result.returncode != 0:
        print(f"[Avatar] 移除表情失败: {result.stderr[:200]}", file=sys.stderr)


def reply_message(message_id: str, text: str):
    """通过 lark-cli 回复飞书消息"""
    if len(text) > 4000:
        text = text[:3950] + "\n\n...(回复过长，已截断)"

    data = json.dumps({"msg_type": "text", "content": json.dumps({"text": text})})
    result = subprocess.run(
        [
            "lark-cli", "api", "POST",
            f"/open-apis/im/v1/messages/{message_id}/reply",
            "--data", data, "--as", "bot", "--format", "data",
        ],
        capture_output=True, text=True, timeout=15,
    )
    if result.returncode != 0:
        print(f"[Avatar] 回复消息失败: {result.stderr[:200]}", file=sys.stderr)


def should_respond(event: dict) -> bool:
    """判断是否应该响应这条消息"""
    # 忽略 bot 自己的消息
    if event.get("sender_type") == "bot":
        return False

    chat_type = event.get("chat_type", "")
    content = event.get("content", "")

    # P2P 直接响应
    if chat_type == "p2p":
        return True

    # 群聊：检查是否 @bot（compact 模式下 mention 会出现在 content 中）
    if chat_type == "group":
        # compact 模式下 @bot 的消息 content 中会包含 @_user_1 等标记
        # 或者直接包含 bot 名称
        if "@_user_1" in content:
            return True

    return False


async def handle_message(client: ClaudeSDKClient, event: dict):
    """处理单条飞书消息"""
    global _current_sender_id

    content = event.get("content", "").strip()
    message_id = event.get("message_id", "")
    sender_id = event.get("sender_id", "")
    chat_type = event.get("chat_type", "p2p")

    if not content or not message_id:
        return

    # 清理 @mention 标记
    content = content.replace("@_user_1", "").strip()

    # 设置当前 sender 用于权限判断
    _current_sender_id = sender_id

    # 组装 prompt
    sender_label = "所有者" if sender_id == OWNER_ID else "同事"
    prompt = f"[{sender_label}] 在{'群聊' if chat_type == 'group' else '私聊'}中说：{content}"

    # 发送给 Claude
    await client.query(prompt)

    # 收集回复，首条消息到达时打表情表示"正在处理"
    reply_text = ""
    reaction_id = None
    async for msg in client.receive_response():
        if isinstance(msg, AssistantMessage):
            if reaction_id is None:
                reaction_id = add_reaction(message_id)
            for block in msg.content:
                if isinstance(block, TextBlock):
                    reply_text += block.text
        elif isinstance(msg, ResultMessage):
            if msg.is_error and not reply_text:
                reply_text = "抱歉，处理时出了点问题。"
            break

    # 处理完成，移除"正在处理"表情
    if reaction_id:
        remove_reaction(message_id, reaction_id)

    if reply_text.strip():
        reply_message(message_id, reply_text.strip())


async def start_event_listener_async():
    """启动 lark-cli 事件订阅子进程（async 版本，独立进程组）"""
    return await asyncio.create_subprocess_exec(
        "lark-cli", "event", "+subscribe",
        "--event-types", "im.message.receive_v1",
        "--compact", "--quiet", "--as", "bot",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
        start_new_session=True,  # 创建独立进程组，方便整组杀掉
    )


async def main():
    print(f"[Avatar] 启动数字分身 (owner: {CONFIG['owner_name']})")
    print(f"[Avatar] 工作目录: {ROOT}")
    print(f"[Avatar] 模型: {CONFIG['model']}, effort: {CONFIG['effort']}")

    # 从 config 加载环境变量（过滤空值）
    env = {k: v for k, v in CONFIG.get("env", {}).items() if v}

    options = ClaudeAgentOptions(
        cwd=str(ROOT),
        model=CONFIG["model"],
        effort=CONFIG.get("effort", "max"),
        max_turns=CONFIG.get("max_turns", 100),
        system_prompt=SystemPromptPreset(type="preset", preset="claude_code", append=PERSONA),
        permission_mode="bypassPermissions",
        setting_sources=["project"],
        can_use_tool=permission_gate,
        env=env,
    )

    # 启动事件监听（async）
    listener = await start_event_listener_async()
    print("[Avatar] 飞书事件监听已启动，等待消息...")

    client = ClaudeSDKClient(options=options)

    def _force_kill_sdk_process(client: ClaudeSDKClient):
        """强制终止 SDK 子进程。依赖 claude_agent_sdk==0.1.x 内部结构，升级时需验证。"""
        try:
            transport = getattr(client, '_transport', None)
            if transport:
                proc = getattr(transport, '_process', None)
                if proc and proc.returncode is None:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                    return proc.pid
        except (ProcessLookupError, OSError):
            pass
        return None

    # 注册清理函数：确保 SIGTERM/SIGINT/异常退出时杀掉所有子进程
    def cleanup(signum=None, frame=None):
        print(f"\n[Avatar] 收到信号 {signum}，正在清理子进程...")
        # 杀 lark-cli 事件监听（杀整个进程组，包括 node fork 的子进程）
        try:
            os.killpg(os.getpgid(listener.pid), signal.SIGKILL)
            print(f"[Avatar] 已终止 lark-cli 进程组 (PID {listener.pid})")
        except (ProcessLookupError, OSError):
            pass
        # 杀 Claude SDK 子进程
        pid = _force_kill_sdk_process(client)
        if pid:
            print(f"[Avatar] 已终止 Claude 进程组 (PID {pid})")
        print("[Avatar] 清理完成，退出")
        os._exit(0)

    signal.signal(signal.SIGTERM, cleanup)
    signal.signal(signal.SIGINT, cleanup)

    try:
        await client.connect()
        print("[Avatar] Claude SDK 已连接，开始处理消息")

        while True:
            line_bytes = await listener.stdout.readline()
            if not line_bytes:
                break
            line = line_bytes.decode().strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            if not should_respond(event):
                continue

            print(f"[Avatar] 收到消息: {event.get('content', '')[:50]}...")
            try:
                await handle_message(client, event)
                print("[Avatar] 消息处理完成")
            except Exception as e:
                print(f"[Avatar] 处理消息出错: {e}", file=sys.stderr)

    except KeyboardInterrupt:
        print("\n[Avatar] 正在关闭...")
    finally:
        # 正常退出路径（listener EOF）。信号退出走 cleanup() → os._exit(0)，不经过此处。
        if listener.returncode is None:
            listener.terminate()
            await listener.wait()
        await client.disconnect()
        print("[Avatar] 已退出")


if __name__ == "__main__":
    asyncio.run(main())
