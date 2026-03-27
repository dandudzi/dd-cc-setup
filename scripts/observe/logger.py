"""
JSONL log writer for the observability pipeline.

Log path: ~/.claude/logs/actions.jsonl (override via CC_ACTION_LOG).
write_log() never raises — silently swallows all I/O errors so the engine
never crashes due to a logging failure.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path


def get_log_path() -> Path:
    """Return the log file path.

    Uses CC_ACTION_LOG env var if set; otherwise ~/.claude/logs/actions.jsonl.
    """
    env = os.environ.get("CC_ACTION_LOG")
    if env:
        return Path(env)
    return Path.home() / ".claude" / "logs" / "actions.jsonl"


def write_log(entry: dict) -> None:
    """Append an ObservationEntry dict as a single JSON line to the log file.

    Creates parent directories if needed. Never raises.
    """
    try:
        log_path = get_log_path()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass  # Never let logging failures crash the engine


def write_error_log(tool_name: str, error: str) -> None:
    """Write a minimal error entry when the engine crashes before context is built."""
    entry = {
        "ts": int(time.time()),
        "event_type": "error",
        "tool_name": tool_name,
        "errors": [error],
    }
    write_log(entry)
