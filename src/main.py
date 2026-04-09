#!/usr/bin/env python3
"""Tripo Digital Avatar — 入口、事件循环、进程管理"""

import asyncio
import json
import os
import signal
import sys

from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions
from claude_agent_sdk.types import SystemPromptPreset

from src.config import ROOT, CONFIG, PERSONA, HEADLESS_RULES, DISALLOWED_TOOLS
from src.handler import should_respond, handle_message, compute_session_id
from src.permissions import permission_gate
from src.session import SessionDispatcher


async def start_event_listener():
    """启动 lark-cli 事件订阅子进程（独立进程组）"""
    return await asyncio.create_subprocess_exec(
        "lark-cli", "event", "+subscribe",
        "--event-types", "im.message.receive_v1",
        "--compact", "--quiet", "--as", "bot",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
        start_new_session=True,
    )


async def main():
    print(f"[Avatar] 启动数字分身 (owner: {CONFIG['owner_name']})")
    print(f"[Avatar] 工作目录: {ROOT}")
    print(f"[Avatar] 模型: {CONFIG['model']}, effort: {CONFIG['effort']}")

    env = {k: v for k, v in CONFIG.get("env", {}).items() if v}

    options = ClaudeAgentOptions(
        cwd=str(ROOT),
        model=CONFIG["model"],
        effort=CONFIG.get("effort", "max"),
        max_turns=CONFIG.get("max_turns", 100),
        system_prompt=SystemPromptPreset(
            type="preset", preset="claude_code",
            append=PERSONA + HEADLESS_RULES,
        ),
        permission_mode="bypassPermissions",
        disallowed_tools=DISALLOWED_TOOLS,
        setting_sources=["user", "project"],
        can_use_tool=permission_gate,
        env=env,
    )

    listener = await start_event_listener()
    print("[Avatar] 飞书事件监听已启动，等待消息...")

    client = ClaudeSDKClient(options=options)

    def _force_kill_sdk_process(c: ClaudeSDKClient) -> int | None:
        """强制终止 SDK 子进程。依赖 claude_agent_sdk==0.1.x 内部结构，升级时需验证。"""
        try:
            transport = getattr(c, '_transport', None)
            if transport:
                proc = getattr(transport, '_process', None)
                if proc and proc.returncode is None:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                    return proc.pid
        except (ProcessLookupError, OSError):
            pass
        return None

    def cleanup(signum=None, frame=None):
        print(f"\n[Avatar] 收到信号 {signum}，正在清理子进程...")
        try:
            os.killpg(os.getpgid(listener.pid), signal.SIGKILL)
            print(f"[Avatar] 已终止 lark-cli 进程组 (PID {listener.pid})")
        except (ProcessLookupError, OSError):
            pass
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

        dispatcher = SessionDispatcher()

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

            session_id = compute_session_id(event)
            print(f"[Avatar] 收到消息 [{session_id}]: {event.get('content', '')[:50]}...")
            await dispatcher.dispatch(
                session_id,
                handle_message(client, event),
            )

    except KeyboardInterrupt:
        print("\n[Avatar] 正在关闭...")
    finally:
        # 正常退出路径（listener EOF）。信号退出走 cleanup() → os._exit(0)，不经过此处。
        if listener.returncode is None:
            listener.terminate()
            await listener.wait()
        await dispatcher.shutdown()
        await client.disconnect()
        print("[Avatar] 已退出")


if __name__ == "__main__":
    asyncio.run(main())
