"""session 调度器测试"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.session import SessionDispatcher


def run_async(coro):
    return asyncio.run(coro)


class TestSessionDispatcher:
    def test_dispatches_single_message(self):
        """单条消息正常分发和执行"""
        dispatcher = SessionDispatcher()
        executed = []

        async def handler():
            executed.append("a")

        async def run():
            await dispatcher.dispatch("session_1", handler())
            await dispatcher.drain("session_1")

        run_async(run())
        assert executed == ["a"]

    def test_same_session_processes_sequentially(self):
        """同一 session 内消息串行处理"""
        dispatcher = SessionDispatcher()
        order = []

        async def make_handler(label, delay=0):
            if delay:
                await asyncio.sleep(delay)
            order.append(label)

        async def run():
            await dispatcher.dispatch("s1", make_handler("first", delay=0.05))
            await dispatcher.dispatch("s1", make_handler("second"))
            await dispatcher.drain("s1")

        run_async(run())
        assert order == ["first", "second"]

    def test_different_sessions_run_concurrently(self):
        """不同 session 可并发处理"""
        dispatcher = SessionDispatcher()
        timestamps = {}

        async def make_handler(session, delay):
            timestamps[f"{session}_start"] = asyncio.get_event_loop().time()
            await asyncio.sleep(delay)
            timestamps[f"{session}_end"] = asyncio.get_event_loop().time()

        async def run():
            await dispatcher.dispatch("s1", make_handler("s1", 0.1))
            await dispatcher.dispatch("s2", make_handler("s2", 0.1))
            await dispatcher.drain("s1")
            await dispatcher.drain("s2")

        run_async(run())
        # s2 应该在 s1 完成之前就开始了（并发）
        assert timestamps["s2_start"] < timestamps["s1_end"]

    def test_handler_error_does_not_block_queue(self):
        """handler 抛异常不阻塞后续消息"""
        dispatcher = SessionDispatcher()
        executed = []

        async def bad_handler():
            raise ValueError("boom")

        async def good_handler():
            executed.append("ok")

        async def run():
            await dispatcher.dispatch("s1", bad_handler())
            await dispatcher.dispatch("s1", good_handler())
            await dispatcher.drain("s1")

        run_async(run())
        assert executed == ["ok"]

    def test_reuses_existing_worker(self):
        """同一 session 复用已有 worker，不重复创建"""
        dispatcher = SessionDispatcher()
        count = []

        async def handler():
            count.append(1)

        async def run():
            await dispatcher.dispatch("s1", handler())
            await dispatcher.dispatch("s1", handler())
            await dispatcher.drain("s1")

        run_async(run())
        assert len(count) == 2
        # 只有一个 worker task
        assert len(dispatcher._workers) == 1

    def test_shutdown_cancels_all_workers(self):
        """shutdown 取消所有 worker"""
        dispatcher = SessionDispatcher()

        async def slow_handler():
            await asyncio.sleep(10)

        async def run():
            await dispatcher.dispatch("s1", slow_handler())
            await dispatcher.shutdown()

        run_async(run())
        assert all(t.cancelled() or t.done() for t in dispatcher._workers.values())
