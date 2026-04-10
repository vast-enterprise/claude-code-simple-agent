"""Client 池：per-session 独立 ClaudeSDKClient，真正的会话隔离"""

import asyncio
import contextlib

from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions

from src.config import log_debug, log_error


class ClientPool:
    """管理 per-session 的 ClaudeSDKClient 实例。

    每个 session_id 对应一个独立的 ClaudeSDKClient（独立 claude 子进程），
    实现真正的会话上下文隔离。惰性创建，首次使用时 connect。

    TODO: 当前 client 只增不减，每个新 session 常驻一个 claude 子进程。
    用户量大时需要加 idle timeout 回收不活跃的 client。
    """

    def __init__(self, options: ClaudeAgentOptions):
        self._options = options
        self._clients: dict[str, ClaudeSDKClient] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    async def get(self, session_id: str) -> ClaudeSDKClient:
        """获取指定 session 的 client，不存在则创建并 connect"""
        if session_id not in self._locks:
            self._locks[session_id] = asyncio.Lock()

        async with self._locks[session_id]:
            if session_id not in self._clients:
                client = ClaudeSDKClient(options=self._options)
                try:
                    await client.connect()
                except Exception:
                    with contextlib.suppress(Exception):
                        await client.disconnect()
                    raise
                self._clients[session_id] = client
                log_debug(f"新建 client: {session_id}")
            return self._clients[session_id]

    async def shutdown(self):
        """断开所有 client"""
        for sid, client in self._clients.items():
            try:
                await client.disconnect()
            except Exception as e:
                log_error(f"disconnect {sid} 失败: {e}")
        self._clients.clear()
        self._locks.clear()
