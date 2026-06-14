from collections import deque
from datetime import datetime, timezone

_buffer: deque[dict] = deque(maxlen=500)


def append_log(level: str, message: str) -> None:
    _buffer.append({
        "ts": datetime.now(timezone.utc).isoformat(),
        "level": level,
        "msg": message,
    })


def get_logs() -> list[dict]:
    return list(_buffer)
