"""Session 调度器：消息直推 + per-session reader task

消息到达时立即 send_message（非阻塞，仅写 stdin）。
每个 session 有一个长驻 reader task 持续读取 Claude 响应并回复飞书。
"""

import asyncio
from typing import Callable, Awaitable

from src.config import log_debug, log_error


class SessionDispatcher:
    def __init__(self):
        self._readers: dict[str, asyncio.Task] = {}

    async def dispatch(
        self,
        session_id: str,
        send_coro: Awaitable,
        reader_factory: Callable[[], Awaitable] | None = None,
    ):
        """分发消息：立即 await send_coro，并确保 reader task 已启动。

        Args:
            session_id: 会话标识
            send_coro: send_message 协程（非阻塞，仅写 stdin + 入队 FIFO）
            reader_factory: 返回 session_reader 协程的工厂函数，首次消息时调用
        """
        # send_message 是非阻塞的（仅写 stdin），直接 await
        try:
            await send_coro
        except Exception as e:
            log_error(f"[Session {session_id}] send 出错: {e}")

        # 确保 reader task 已启动
        if reader_factory and session_id not in self._readers:
            self._start_reader(session_id, reader_factory)

    def _start_reader(self, session_id: str, reader_factory: Callable[[], Awaitable]):
        """启动 per-session reader task"""
        async def _reader_wrapper():
            try:
                await reader_factory()
            except asyncio.CancelledError:
                log_debug(f"[Session {session_id}] reader 已取消")
            except Exception as e:
                log_error(f"[Session {session_id}] reader 异常退出: {e}")
            finally:
                self._readers.pop(session_id, None)

        task = asyncio.create_task(_reader_wrapper())
        self._readers[session_id] = task
        log_debug(f"[Session {session_id}] reader task 已启动")

    def cancel_reader(self, session_id: str):
        """取消指定 session 的 reader task（用于 /clear 删除 session 时）"""
        task = self._readers.pop(session_id, None)
        if task and not task.done():
            task.cancel()
            log_debug(f"[Session {session_id}] reader task 已取消")

    async def shutdown(self):
        """取消所有 reader tasks"""
        for task in self._readers.values():
            task.cancel()
        if self._readers:
            await asyncio.gather(*self._readers.values(), return_exceptions=True)
        self._readers.clear()

    async def drain_all(self, timeout: float = 10):
        """等待所有 reader tasks 完成（超时后强制 shutdown）"""
        if not self._readers:
            return
        try:
            await asyncio.wait_for(
                asyncio.gather(*self._readers.values(), return_exceptions=True),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            pass
        await self.shutdown()
