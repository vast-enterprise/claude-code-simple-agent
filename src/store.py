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
        self._write(data)

    def remove(self, session_id: str) -> bool:
        data = self.load_all()
        if session_id not in data:
            return False
        del data[session_id]
        self._write(data)
        return True

    def update_active(self, session_id: str) -> None:
        data = self.load_all()
        if session_id in data:
            data[session_id]["last_active"] = datetime.now(timezone.utc).isoformat()
            data[session_id]["message_count"] = data[session_id].get("message_count", 0) + 1
            self._write(data)

    def _write(self, data: dict) -> None:
        """原子写入：先写临时文件 → fsync → rename 覆盖，避免写一半崩溃导致数据丢失"""
        content = json.dumps(data, indent=2, ensure_ascii=False)
        fd, tmp_path = tempfile.mkstemp(dir=self._path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, self._path)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
