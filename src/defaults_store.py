"""per-user 默认会话 suffix 持久化"""

import json
import os
import tempfile
from pathlib import Path

from src.config import log_error


class DefaultsStore:
    def __init__(self, path: Path):
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def get_default(self, base_session_id: str) -> str | None:
        """获取用户的默认 suffix，None 表示原始会话"""
        data = self._load()
        return data.get(base_session_id)

    def set_default(self, base_session_id: str, suffix: str | None) -> None:
        """设置默认 suffix，None 切回原始会话"""
        data = self._load()
        data[base_session_id] = suffix
        self._write(data)

    def remove_user(self, base_session_id: str) -> None:
        """清除用户的默认设置"""
        data = self._load()
        if base_session_id in data:
            del data[base_session_id]
            self._write(data)

    def _load(self) -> dict:
        if not self._path.exists():
            return {}
        try:
            return json.loads(self._path.read_text())
        except (json.JSONDecodeError, OSError):
            log_error("session_defaults.json 损坏，重置")
            return {}

    def _write(self, data: dict) -> None:
        """原子写入：先写临时文件 → fsync → rename 覆盖"""
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
