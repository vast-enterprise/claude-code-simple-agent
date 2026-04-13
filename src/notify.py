"""飞书异常通知，60 秒同类防风暴"""

import json
import subprocess
import time

from src.config import NOTIFY_CONFIG, log_error

_throttle_cache: dict[str, float] = {}
_THROTTLE_SECONDS = 60
_notify_config = NOTIFY_CONFIG


def notify_error(title: str, detail: str) -> None:
    if not _notify_config.get("enabled", False):
        return

    now = time.time()
    if title in _throttle_cache and now - _throttle_cache[title] < _THROTTLE_SECONDS:
        return
    _throttle_cache[title] = now

    receive_id = _notify_config.get("receive_id", "")
    receive_id_type = _notify_config.get("receive_id_type", "open_id")
    if not receive_id:
        return

    text = f"⚠️ {title}\n{detail}"
    content = json.dumps({"text": text})
    data = json.dumps({"receive_id": receive_id, "msg_type": "text", "content": content})

    try:
        subprocess.run(
            [
                "lark-cli", "api", "POST",
                "/open-apis/im/v1/messages",
                "--params", json.dumps({"receive_id_type": receive_id_type}),
                "--data", data, "--as", "bot", "--format", "data",
            ],
            capture_output=True, text=True, timeout=10,
        )
    except Exception as e:
        log_error(f"发送通知失败: {e}")
