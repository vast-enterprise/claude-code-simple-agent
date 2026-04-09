#!/usr/bin/env python3
"""Tripo Digital Avatar — 飞书机器人数字分身 MVP"""

import asyncio
import json
import os
import signal
import sys
from pathlib import Path

from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions
from claude_agent_sdk.types import (
    AssistantMessage, ResultMessage, TextBlock, PermissionResultAllow, PermissionResultDeny,
    ToolPermissionContext, SystemPromptPreset,
)

ROOT = Path(__file__).resolve().parent.parent
CONFIG = json.loads((Path(__file__).parent / "config.json").read_text())
PERSONA = (Path(__file__).parent / "persona.md").read_text()

OWNER_ID = CONFIG["owner_open_id"]
SENSITIVE = ["deploy", "git push", "git merge", "git reset", "rm -rf", "drop "]

# 闭包状态：当前消息的 sender_id
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


def reply_message(message_id: str, text: str):
    """通过 lark-cli 回复飞书消息"""
    import subprocess

    if len(text) > 4000:
        text = text[:3950] + "\n\n...(回复过长，已截断)"

    data = json.dumps({"msg_type": "text", "content": json.dumps({"text": text})})
    subprocess.run(
        [
            "lark-cli", "api", "POST",
            f"/open-apis/im/v1/messages/{message_id}/reply",
            "--data", data, "--as", "bot", "--format", "data",
        ],
        capture_output=True, text=True, timeout=15,
    )


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
        if "@_user_1" in content or "@_all" in content:
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

    # 收集回复
    reply_text = ""
    async for msg in client.receive_response():
        if isinstance(msg, AssistantMessage):
            for block in msg.content:
                if isinstance(block, TextBlock):
                    reply_text += block.text
        elif isinstance(msg, ResultMessage):
            if msg.is_error and not reply_text:
                reply_text = "抱歉，处理时出了点问题。"
            break

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
        effort=CONFIG.get("effort", "high"),
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
        if hasattr(client, '_transport') and client._transport:
            transport = client._transport
            if hasattr(transport, '_process') and transport._process:
                proc = transport._process
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                    print(f"[Avatar] 已终止 Claude 进程组 (PID {proc.pid})")
                except (ProcessLookupError, OSError):
                    pass
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
        # 正常退出也要清理
        if listener.returncode is None:
            listener.terminate()
            await listener.wait()
        await client.disconnect()
        print("[Avatar] 已退出")


if __name__ == "__main__":
    asyncio.run(main())
