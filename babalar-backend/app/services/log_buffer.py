import json
import os
from collections import deque
from datetime import datetime, timezone

LOG_FILE = os.getenv("LOG_FILE_PATH", "/app/logs/ingestion.log")
MAX_LINES = 500

_buffer: deque[dict] = deque(maxlen=MAX_LINES)


def _load_from_file() -> None:
    try:
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            _buffer.append(json.loads(line))
                        except Exception:
                            pass
    except Exception:
        pass


def append_log(level: str, message: str) -> None:
    entry = {"ts": datetime.now(timezone.utc).isoformat(), "level": level, "msg": message}
    _buffer.append(entry)
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        with open(LOG_FILE, "a") as f:
            f.write(json.dumps(entry) + "\n")
        _trim_file()
    except Exception:
        pass


def _trim_file() -> None:
    try:
        with open(LOG_FILE) as f:
            lines = f.readlines()
        if len(lines) > MAX_LINES:
            with open(LOG_FILE, "w") as f:
                f.writelines(lines[-MAX_LINES:])
    except Exception:
        pass


def get_logs() -> list[dict]:
    return list(_buffer)


_load_from_file()
