"""Client 池：per-session 独立 ClaudeSDKClient，真正的会话隔离"""

from __future__ import annotations

import asyncio
import contextlib
import dataclasses
from typing import TYPE_CHECKING

from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions

from src.config import log_debug, log_error

if TYPE_CHECKING:
    from src.store import SessionStore


class ClientPool:
    """管理 per-session 的 ClaudeSDKClient 实例。

    每个 session_id 对应一个独立的 ClaudeSDKClient（独立 claude 子进程），
    实现真正的会话上下文隔离。惰性创建，首次使用时 connect。

    可选接受 SessionStore 实例，在创建/删除 client 时同步持久化 session 映射。
    store 为 None 时所有持久化操作静默跳过（向后兼容）。

    TODO: 当前 client 只增不减，每个新 session 常驻一个 claude 子进程。
    用户量大时需要加 idle timeout 回收不活跃的 client。
    """

    def __init__(self, options: ClaudeAgentOptions, *, store: SessionStore | None = None):
        self._options = options
        self._store = store
        self._clients: dict[str, ClaudeSDKClient] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    async def get(self, session_id: str) -> ClaudeSDKClient:
        """获取指定 session 的 client，不存在则创建并 connect"""
        if session_id not in self._locks:
            self._locks[session_id] = asyncio.Lock()

        async with self._locks[session_id]:
            if session_id not in self._clients:
                # 如果 store 中有历史 claude_session_id，用 --resume 恢复
                opts = self._options
                stored_sid = self.get_claude_session_id(session_id)
                if stored_sid:
                    opts = dataclasses.replace(self._options, resume=stored_sid)
                    log_debug(f"resume session: {session_id} → {stored_sid}")

                client = ClaudeSDKClient(options=opts)
                try:
                    await client.connect()
                except Exception:
                    with contextlib.suppress(Exception):
                        await client.disconnect()
                    raise
                self._clients[session_id] = client
                log_debug(f"新建 client: {session_id}")
                if self._store:
                    self._store.save(session_id, {})

        # update_active 在锁外调用：即使是复用已有 client 也要更新活跃时间
        if self._store:
            self._store.update_active(session_id)

        return self._clients[session_id]

    async def remove(self, session_id: str) -> bool:
        """断开指定 session 的 client 并从 store 中删除。

        使用 per-session lock 确保不会与正在处理的 query/receive_response 并发冲突。

        Returns:
            True 如果 session 存在且已移除，False 如果 session 不存在。
        """
        if session_id not in self._locks:
            self._locks[session_id] = asyncio.Lock()

        async with self._locks[session_id]:
            client = self._clients.pop(session_id, None)

            if client:
                try:
                    await client.disconnect()
                except Exception as e:
                    log_error(f"disconnect {session_id} 失败: {e}")

            store_removed = False
            if self._store:
                self._store.archive(session_id)
                store_removed = self._store.remove(session_id)

            removed = client is not None or store_removed
            if removed:
                log_debug(f"已移除 session: {session_id}")

        self._locks.pop(session_id, None)
        return removed

    def list_sessions(self) -> dict:
        """返回 store 中所有 session 数据。无 store 时返回空 dict。"""
        if self._store:
            return self._store.load_all()
        return {}

    def get_claude_session_id(self, session_id: str) -> str | None:
        """获取存储的 Claude session_id，用于 resume。无则返回 None（首次创建）。"""
        if self._store:
            data = self._store.load_all()
            return data.get(session_id, {}).get("claude_session_id")
        return None

    def save_claude_session_id(self, session_id: str, claude_session_id: str) -> None:
        """保存 Claude 返回的 session_id 到 store，用于重启后 resume。"""
        if self._store:
            self._store.save(session_id, {"claude_session_id": claude_session_id})

    def session_ids(self) -> set[str]:
        """返回 store 中所有 session_id。无 store 时返回空 set。"""
        if self._store:
            return set(self._store.load_all().keys())
        return set()

    async def shutdown(self):
        """断开所有 client"""
        for sid, client in self._clients.items():
            try:
                await client.disconnect()
            except Exception as e:
                log_error(f"disconnect {sid} 失败: {e}")
        self._clients.clear()
        self._locks.clear()
