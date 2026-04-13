#!/usr/bin/env python3
"""Tripo Digital Avatar — 入口、事件循环、进程管理"""

import asyncio
import json
import os
import signal
import sys

from claude_agent_sdk import ClaudeAgentOptions
from claude_agent_sdk.types import SystemPromptPreset

from src.config import ROOT, CONFIG, PERSONA, HEADLESS_RULES, DISALLOWED_TOOLS, log_debug, log_info
from src.handler import should_respond, send_message, session_reader, compute_session_id
from src.metrics import MetricsCollector
from src.notify import notify_error
from src.permissions import permission_gate
from src.pool import ClientPool
from src.server import start_server
from src.session import SessionDispatcher
from src.store import SessionStore

# 优雅关闭信号
_shutdown = asyncio.Event()

# 全局异常钩子：进程崩溃时推飞书通知
_original_excepthook = sys.excepthook


def _crash_hook(exc_type, exc_value, exc_tb):
    notify_error("数字分身崩溃", f"{exc_type.__name__}: {exc_value}")
    _original_excepthook(exc_type, exc_value, exc_tb)


sys.excepthook = _crash_hook


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


async def _read_or_shutdown(reader) -> bytes | None:
    """readline + shutdown event 多路复用，shutdown 触发时返回 None"""
    read_task = asyncio.ensure_future(reader.readline())
    shutdown_task = asyncio.ensure_future(_shutdown.wait())
    done, pending = await asyncio.wait(
        [read_task, shutdown_task],
        return_when=asyncio.FIRST_COMPLETED,
    )
    for t in pending:
        t.cancel()
        try:
            await t
        except asyncio.CancelledError:
            pass
    if shutdown_task in done:
        return None
    return read_task.result()


async def main():
    log_info(f"启动数字分身 (owner: {CONFIG['owner_name']})")
    log_info(f"工作目录: {ROOT}")
    log_info(f"模型: {CONFIG['model']}, effort: {CONFIG.get('effort', 'max')}")

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
    log_info("飞书事件监听已启动，等待消息...")

    store = SessionStore(ROOT / "data" / "sessions.json")
    pool = ClientPool(options, store=store)
    metrics = MetricsCollector()
    dispatcher = SessionDispatcher()

    server_runner = await start_server(pool, metrics, port=8420)

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda s=sig: (_shutdown.set(), log_info(f"收到信号 {s}，准备优雅关闭...")))

    try:
        while not _shutdown.is_set():
            line_bytes = await _read_or_shutdown(listener.stdout)
            if line_bytes is None or len(line_bytes) == 0:
                if not _shutdown.is_set():
                    notify_error("飞书事件监听断连", "lark-cli 进程退出")
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
            log_info(f"收到消息 [{session_id}]: {event.get('content', '')[:50]}...")
            await dispatcher.dispatch(
                session_id,
                send_message(pool, event, metrics=metrics),
                reader_factory=lambda sid=session_id: session_reader(sid, pool, metrics=metrics),
            )

    except KeyboardInterrupt:
        log_info("正在关闭...")
    finally:
        log_info("开始清理...")
        # 0. 停止 HTTP server（不再接受新请求）
        if server_runner:
            await server_runner.cleanup()
        # 1. 杀掉 lark-cli 整个进程组（start_new_session=True 建的独立组）
        if listener.returncode is None:
            try:
                os.killpg(os.getpgid(listener.pid), signal.SIGTERM)
            except (ProcessLookupError, OSError):
                pass
            try:
                await asyncio.wait_for(listener.wait(), timeout=5)
            except asyncio.TimeoutError:
                try:
                    os.killpg(os.getpgid(listener.pid), signal.SIGKILL)
                except (ProcessLookupError, OSError):
                    pass
        # 2. 等待正在处理的消息完成（最多 10 秒），超时后强制取消
        await dispatcher.drain_all(timeout=10)
        # 3. 断开所有 client
        await pool.shutdown()
        log_info("已退出")


if __name__ == "__main__":
    asyncio.run(main())
