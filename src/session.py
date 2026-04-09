"""Session 调度器：per-session 队列 + worker"""

import asyncio
import sys


class SessionDispatcher:
    def __init__(self):
        self._queues: dict[str, asyncio.Queue] = {}
        self._workers: dict[str, asyncio.Task] = {}

    async def dispatch(self, session_id: str, coro):
        """将协程分发到对应 session 的队列，首次使用时自动创建 worker"""
        if session_id not in self._queues:
            self._queues[session_id] = asyncio.Queue()
            self._workers[session_id] = asyncio.create_task(
                self._worker(session_id)
            )
        await self._queues[session_id].put(coro)

    async def _worker(self, session_id: str):
        """单个 session 的消费循环（串行处理）"""
        queue = self._queues[session_id]
        while True:
            coro = await queue.get()
            try:
                await coro
            except Exception as e:
                print(f"[Session {session_id}] 处理出错: {e}", file=sys.stderr)
            finally:
                queue.task_done()

    async def drain(self, session_id: str):
        """等待指定 session 队列中所有任务完成"""
        if session_id in self._queues:
            await self._queues[session_id].join()

    async def shutdown(self):
        """取消所有 worker，清理资源"""
        for task in self._workers.values():
            task.cancel()
        await asyncio.gather(*self._workers.values(), return_exceptions=True)

    async def drain_all(self, timeout: float = 10):
        """等待所有 session 队列清空，超时后强制 shutdown"""
        if not self._queues:
            return
        try:
            await asyncio.wait_for(
                asyncio.gather(
                    *(q.join() for q in self._queues.values())
                ),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            pass  # 超时后强制 shutdown
        await self.shutdown()
