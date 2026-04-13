"""session 调度器测试：消息直推 + reader task 管理"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.session import SessionDispatcher


def run_async(coro):
    return asyncio.run(coro)


class TestSessionDispatcher:
    def test_dispatches_send_immediately(self):
        """send_coro 立即被 await"""
        dispatcher = SessionDispatcher()
        executed = []

        async def send():
            executed.append("sent")

        async def run():
            await dispatcher.dispatch("s1", send())

        run_async(run())
        assert executed == ["sent"]

    def test_starts_reader_on_first_message(self):
        """首次消息启动 reader task"""
        dispatcher = SessionDispatcher()
        reader_started = []

        async def send():
            pass

        async def reader():
            reader_started.append(True)

        async def run():
            await dispatcher.dispatch("s1", send(), reader_factory=lambda: reader())
            # 给 reader task 时间启动
            await asyncio.sleep(0.05)

        run_async(run())
        assert len(reader_started) == 1
        # reader 已完成（mock 立即返回），自动从 _readers 清理

    def test_does_not_restart_reader(self):
        """多次 dispatch 不重复启动 reader"""
        dispatcher = SessionDispatcher()
        reader_count = []

        async def send():
            pass

        async def reader():
            reader_count.append(1)
            await asyncio.sleep(1)  # 长驻

        async def run():
            factory = lambda: reader()
            await dispatcher.dispatch("s1", send(), reader_factory=factory)
            await dispatcher.dispatch("s1", send(), reader_factory=factory)
            await asyncio.sleep(0.05)
            await dispatcher.shutdown()

        run_async(run())
        assert len(reader_count) == 1

    def test_cancel_reader(self):
        """cancel_reader 取消指定 session 的 reader"""
        dispatcher = SessionDispatcher()

        async def send():
            pass

        async def reader():
            await asyncio.sleep(10)

        async def run():
            await dispatcher.dispatch("s1", send(), reader_factory=lambda: reader())
            await asyncio.sleep(0.05)
            dispatcher.cancel_reader("s1")
            await asyncio.sleep(0.05)

        run_async(run())
        assert "s1" not in dispatcher._readers

    def test_shutdown_cancels_all_readers(self):
        """shutdown 取消所有 reader tasks"""
        dispatcher = SessionDispatcher()

        async def send():
            pass

        async def reader():
            await asyncio.sleep(10)

        async def run():
            await dispatcher.dispatch("s1", send(), reader_factory=lambda: reader())
            await dispatcher.dispatch("s2", send(), reader_factory=lambda: reader())
            await asyncio.sleep(0.05)
            await dispatcher.shutdown()

        run_async(run())
        assert len(dispatcher._readers) == 0

    def test_drain_all_timeout_forces_shutdown(self):
        """drain_all 超时后强制取消"""
        dispatcher = SessionDispatcher()

        async def send():
            pass

        async def reader():
            await asyncio.sleep(100)

        async def run():
            await dispatcher.dispatch("s1", send(), reader_factory=lambda: reader())
            await asyncio.sleep(0.05)
            await dispatcher.drain_all(timeout=0.1)

        run_async(run())
        assert len(dispatcher._readers) == 0

    def test_send_error_does_not_crash(self):
        """send_coro 异常不影响 reader 启动"""
        dispatcher = SessionDispatcher()
        reader_started = []

        async def bad_send():
            raise ValueError("send failed")

        async def reader():
            reader_started.append(True)

        async def run():
            await dispatcher.dispatch("s1", bad_send(), reader_factory=lambda: reader())
            await asyncio.sleep(0.05)
            await dispatcher.shutdown()

        run_async(run())
        assert len(reader_started) == 1

    def test_no_reader_factory(self):
        """不传 reader_factory 时不启动 reader"""
        dispatcher = SessionDispatcher()

        async def send():
            pass

        async def run():
            await dispatcher.dispatch("s1", send())

        run_async(run())
        assert "s1" not in dispatcher._readers
