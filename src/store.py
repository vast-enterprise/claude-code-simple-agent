"""Session 映射持久化"""

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from src.config import log_error


class SessionStore:
    def __init__(self, path: Path):
        self._path = path
        self._history_path = path.parent / "sessions_history.json"
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def load_all(self) -> dict:
        if not self._path.exists():
            return {}
        try:
            return json.loads(self._path.read_text())
        except (json.JSONDecodeError, OSError):
            log_error("sessions.json 损坏，备份后重置")
            try:
                backup = self._path.with_suffix(f".json.bad.{int(datetime.now(timezone.utc).timestamp())}")
                self._path.rename(backup)
                log_error(f"损坏文件已备份到 {backup}")
            except OSError:
                pass
            return {}

    def save(self, session_id: str, metadata: dict) -> None:
        data = self.load_all()
        now = datetime.now(timezone.utc).isoformat()
        entry = data.get(session_id, {})
        entry.update(metadata)
        entry.setdefault("created_at", now)
        entry.setdefault("last_active", now)
        entry.setdefault("message_count", 0)
        data[session_id] = entry
        self._write(self._path, data)

    def remove(self, session_id: str) -> bool:
        data = self.load_all()
        if session_id not in data:
            return False
        del data[session_id]
        self._write(self._path, data)
        return True

    def archive(self, session_id: str) -> bool:
        """将 session 归档到 sessions_history.json。

        归档记录包含原始元数据 + session_id + archived_at。
        历史文件为列表结构，同一 session_id 可多次归档。

        Returns:
            True 如果成功归档，False 如果 session 不存在。
        """
        data = self.load_all()
        entry = data.get(session_id)
        if entry is None:
            return False

        record = {**entry, "session_id": session_id, "archived_at": datetime.now(timezone.utc).isoformat()}

        history = self.load_history()
        history.append(record)
        self._write(self._history_path, history)
        return True

    def load_history(self) -> list:
        """加载归档历史记录列表。"""
        if not self._history_path.exists():
            return []
        try:
            result = json.loads(self._history_path.read_text())
            if not isinstance(result, list):
                return []
            return result
        except (json.JSONDecodeError, OSError):
            log_error("sessions_history.json 损坏，备份后重置")
            try:
                backup = self._history_path.with_suffix(
                    f".json.bad.{int(datetime.now(timezone.utc).timestamp())}"
                )
                self._history_path.rename(backup)
                log_error(f"损坏文件已备份到 {backup}")
            except OSError:
                pass
            return []

    def update_active(self, session_id: str) -> None:
        data = self.load_all()
        if session_id in data:
            data[session_id]["last_active"] = datetime.now(timezone.utc).isoformat()
            data[session_id]["message_count"] = data[session_id].get("message_count", 0) + 1
            self._write(self._path, data)

    def _write(self, path: Path, data: dict | list) -> None:
        """原子写入：先写临时文件 → fsync → rename 覆盖，避免写一半崩溃导致数据丢失"""
        content = json.dumps(data, indent=2, ensure_ascii=False)
        fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, path)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
