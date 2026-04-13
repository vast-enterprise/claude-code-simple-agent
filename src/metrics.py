"""运行指标收集器"""

from collections import deque
from datetime import datetime, timezone


class MetricsCollector:
    def __init__(self, max_log: int = 200):
        self.start_time = datetime.now(timezone.utc)
        self.total_messages = 0
        self.total_errors = 0
        self.message_log: deque[dict] = deque(maxlen=max_log)

    def record_message(
        self, session_id: str, content: str, success: bool, reply: str
    ) -> None:
        self.total_messages += 1
        if not success:
            self.total_errors += 1
        self.message_log.append({
            "session_id": session_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "content_preview": content[:50],
            "success": success,
            "reply_preview": reply[:50],
        })

    def status(self) -> dict:
        now = datetime.now(timezone.utc)
        uptime = now - self.start_time
        hours, remainder = divmod(int(uptime.total_seconds()), 3600)
        minutes = remainder // 60
        return {
            "uptime": f"{hours}h{minutes}m",
            "start_time": self.start_time.isoformat(),
            "total_messages": self.total_messages,
            "total_errors": self.total_errors,
            "error_rate": f"{self.total_errors / max(self.total_messages, 1) * 100:.1f}%",
        }
