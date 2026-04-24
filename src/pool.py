"""Client 池：per-session 独立 ClaudeSDKClient，真正的会话隔离"""

from __future__ import annotations

import asyncio
import collections
import contextlib
import dataclasses
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions

from src.config import log_debug, log_error

if TYPE_CHECKING:
    from src.session import SessionDispatcher
    from src.store import SessionStore


class SessionStatus:
    """Session 状态枚举。

    - NONE:       session 完全不存在（store 和 _clients 都没有）
    - CREATED:    session 在 store 有元数据，但尚无 SDK client（重启后未 reconnect 的场景）
    - READY:      有 SDK client，空闲可接消息
    - PROCESSING: 正在执行（已发 query，等 ResultMessage）
    """

    NONE = "NONE"
    CREATED = "CREATED"
    READY = "READY"
    PROCESSING = "PROCESSING"


class ClientPool:
    """管理 per-session 的 ClaudeSDKClient 实例。

    每个 session_id 对应一个独立的 ClaudeSDKClient（独立 claude 子进程），
    实现真正的会话上下文隔离。惰性创建，首次使用时 connect。

    可选接受 SessionStore 实例，在创建/删除 client 时同步持久化 session 映射。
    store 为 None 时所有持久化操作静默跳过（向后兼容）。

    支持 LRU 回收：当活跃 client 数超过 max_active_clients 时，回收最久未活跃的 session。
    """

    def __init__(
        self,
        options: ClaudeAgentOptions,
        *,
        store: "SessionStore | None" = None,
        dispatcher: "SessionDispatcher | None" = None,
        max_active_clients: int = 5,
    ):
        self._options = options
        self._store = store
        self._dispatcher = dispatcher
        self._max_active_clients = max_active_clients
        self._clients: dict[str, ClaudeSDKClient] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._pending: dict[str, collections.deque] = {}
        self._processing: dict[str, bool] = {}

    async def get(self, session_id: str) -> ClaudeSDKClient:
        """获取指定 session 的 client，不存在则创建并 connect"""
        if session_id not in self._locks:
            self._locks[session_id] = asyncio.Lock()

        async with self._locks[session_id]:
            if session_id not in self._clients:
                # 超过阈值先回收最久未活跃的 client
                while len(self._clients) >= self._max_active_clients:
                    evicted = await self._evict_lru()
                    if evicted is None:
                        break  # 无可回收的 session，防止死循环

                # 如果 store 中有历史 claude_session_id，用 --resume 恢复
                opts = self._options
                stored_sid = self.get_claude_session_id(session_id)
                if stored_sid and dataclasses.is_dataclass(self._options):
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
        self._pending.pop(session_id, None)
        self._processing.pop(session_id, None)
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

    # ── Session 状态机 ──

    def get_status(self, session_id: str) -> str:
        """返回 session 的当前状态。见 SessionStatus。"""
        if session_id in self._clients:
            if self._processing.get(session_id, False):
                return SessionStatus.PROCESSING
            return SessionStatus.READY
        if session_id in self.session_ids():
            return SessionStatus.CREATED
        return SessionStatus.NONE

    def set_processing(self, session_id: str, is_processing: bool) -> None:
        """切换 session 的 PROCESSING/READY 标记。

        由 handler 在 query 前后调用：query 后 → True；
        收到 ResultMessage 或异常 → False。
        对未建 client 的 session 也允许设置（不会直接影响 get_status——
        CREATED 状态仍以 _clients 缺失为准）。
        """
        self._processing[session_id] = is_processing

    # ── per-session 消息 FIFO ──

    @property
    def max_active_clients(self) -> int:
        return self._max_active_clients

    def active_client_count(self) -> int:
        return len(self._clients)

    def _select_lru_session(self) -> str | None:
        """选择当前 _clients 中 last_active 最早的可回收 session。

        PROCESSING 中的 session 必须跳过——正在 query / 等 ResultMessage
        的 reader 被 cancel 会丢失本轮响应。若所有 session 都在 PROCESSING，
        返回 None，调用方（get()）会 break，池允许临时超出上限。
        """
        candidates = [
            sid for sid in self._clients.keys()
            if not self._processing.get(sid, False)
        ]
        if not candidates:
            return None
        store_data: dict = {}
        if self._store:
            store_data = self._store.load_all()
        def sort_key(sid: str) -> str:
            return store_data.get(sid, {}).get("last_active", "")
        return min(candidates, key=sort_key)

    async def _evict_lru(self) -> str | None:
        """回收最久未活跃的 session：disconnect + cancel reader + 清空 FIFO，保留 store 元数据"""
        session_id = self._select_lru_session()
        if not session_id:
            return None
        client = self._clients.pop(session_id, None)
        if client:
            try:
                await client.disconnect()
            except Exception as e:
                log_error(f"[Eviction] disconnect {session_id} 失败: {e}")
        if self._dispatcher:
            try:
                self._dispatcher.cancel_reader(session_id)
            except Exception as e:
                log_error(f"[Eviction] cancel_reader {session_id} 失败: {e}")
        pending = self._pending.pop(session_id, None)
        pending_count = len(pending) if pending else 0
        if pending_count > 0:
            log_error(f"[Eviction] 丢弃 {session_id} 的 {pending_count} 条待处理消息")
        self._processing.pop(session_id, None)
        log_debug(f"[Eviction] session={session_id} evicted (pending_dropped={pending_count})")
        return session_id

    def get_client(self, session_id: str) -> ClaudeSDKClient | None:
        """获取已有 client（不创建新的）。用于 /interrupt 等需要操作现有 client 的场景。"""
        return self._clients.get(session_id)

    def enqueue_message(self, session_id: str, message_id: str, content: str) -> None:
        """将飞书消息入队到 per-session FIFO，用于 reader task 匹配 response → reply"""
        if session_id not in self._pending:
            self._pending[session_id] = collections.deque()
        self._pending[session_id].append({
            "message_id": message_id,
            "content": content,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    def peek_pending(self, session_id: str) -> dict | None:
        """查看 FIFO 队头（不弹出）。返回 None 如果队列为空。"""
        q = self._pending.get(session_id)
        if q:
            return q[0]
        return None

    def dequeue_message(self, session_id: str) -> dict | None:
        """弹出 FIFO 队头。返回 None 如果队列为空。"""
        q = self._pending.get(session_id)
        if q:
            return q.popleft()
        return None

    def has_pending(self, session_id: str) -> bool:
        """是否有待处理消息"""
        q = self._pending.get(session_id)
        return bool(q)

    def pending_count(self, session_id: str) -> int:
        """当前 FIFO 中的消息数量"""
        q = self._pending.get(session_id)
        return len(q) if q else 0

    def dequeue_batch(self, session_id: str, count: int) -> list[dict]:
        """批量弹出 FIFO 前 count 条。用于 Claude 合并多条消息到一个 turn 时批量 dequeue。"""
        q = self._pending.get(session_id)
        if not q:
            return []
        batch = []
        for _ in range(min(count, len(q))):
            batch.append(q.popleft())
        return batch

    async def shutdown(self):
        """断开所有 client，清空 FIFO"""
        for sid, client in self._clients.items():
            try:
                await client.disconnect()
            except Exception as e:
                log_error(f"disconnect {sid} 失败: {e}")
        self._clients.clear()
        self._locks.clear()
        self._pending.clear()
        self._processing.clear()
