"""Action capture logger for Claude Code hook observability.

This module captures tool calls from Claude Code hooks and logs them to JSONL,
enriched with classification (category, plugin) and routing decisions.

Call flow:
    stdin JSON → main()
      → load_mappings(config_path)
      → classifier.classify(tool_name, mappings) → {category, plugin}
      → router.evaluate(tool_name, tool_input, routing_rules) → {decision, handler, handler_output}
      → build_entry(event, classification, routing_result, latency_ms) → dict
      → append_entry(log_path, entry)
      → exit 0 (always)

JSONL entry schema (12 fields):
    {
      "ts": 1774459459,
      "event_type": "PreToolUse",
      "tool_name": "Read",
      "category": "file_ops",
      "plugin": "core",
      "args": {"file_path": "/src/app.py"},
      "input_size": 42,
      "decision": "soft_deny",
      "handler": "scripts.routing.handlers.route_read_code",
      "handler_output": {"redirect_to": "..."},
      "latency_ms": 12,
      "session_id": "abc-123"
    }
"""

import json
import os
import sys
import time
from pathlib import Path

from scripts.categorise.classifier import classify
from scripts.categorise.router import evaluate


def load_mappings(config_path: Path | None = None) -> dict:
    """Load mappings config from JSON file.

    Args:
        config_path: Path to mappings.json. If None, auto-detects relative to logger.py.

    Returns:
        Mappings dict with keys: tools, mcp_prefixes, _fallback, routing.

    Raises:
        FileNotFoundError: If config file not found.
        json.JSONDecodeError: If config file is not valid JSON.
    """
    if config_path is None:
        # Auto-detect: config/mappings.json relative to logger.py
        config_path = Path(__file__).parent.parent.parent / "config" / "mappings.json"

    with open(config_path) as f:
        return json.load(f)


def get_log_path() -> Path:
    """Get log file path from env var or default.

    Log path is determined by:
    1. CC_ACTION_LOG env var, if set
    2. Default: ~/.claude/logs/actions.jsonl

    Returns:
        Path to log file.
    """
    env_path = os.environ.get("CC_ACTION_LOG")
    if env_path:
        return Path(env_path)

    return Path.home() / ".claude" / "logs" / "actions.jsonl"


def build_entry(
    event: dict,
    classification: dict,
    routing_result: dict,
    latency_ms: int,
) -> dict:
    """Build a JSONL entry from event, classification, and routing result.

    Args:
        event: Event dict from stdin with hook_event_name, tool_name, tool_input, session_id (opt).
        classification: Result from classifier.classify() with category, plugin.
        routing_result: Result from router.evaluate() with decision, handler, handler_output.
        latency_ms: Elapsed milliseconds since script start (int).

    Returns:
        Dict with 12 fields: ts, event_type, tool_name, category, plugin, args, input_size,
        decision, handler, handler_output, latency_ms, session_id.
    """
    tool_input = event.get("tool_input", {})

    entry = {
        "ts": int(time.time()),
        "event_type": event.get("hook_event_name", "unknown"),
        "tool_name": event.get("tool_name", "unknown"),
        "category": classification.get("category", "unknown"),
        "plugin": classification.get("plugin", "unknown"),
        "args": tool_input,
        "input_size": len(json.dumps(tool_input)),
        "decision": routing_result.get("decision", "pass"),
        "handler": routing_result.get("handler"),
        "handler_output": routing_result.get("handler_output"),
        "latency_ms": latency_ms,
        "session_id": event.get("session_id"),
    }

    return entry


def append_entry(log_path: Path, entry: dict) -> None:
    """Append a JSONL entry to log file.

    Creates parent directories if needed. Appends a single JSON line to the log.

    Args:
        log_path: Path to log file.
        entry: Dict to serialize as JSON and append.

    Raises:
        IOError: If unable to write to log file.
    """
    # Create parent directories if needed
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # Append entry as JSONL (one JSON object per line)
    with open(log_path, "a") as f:
        f.write(json.dumps(entry) + "\n")


def main() -> int:
    """Main orchestration function.

    Reads a JSON event from stdin, classifies it, evaluates routing rules,
    builds a JSONL entry, and appends to log. Always exits 0, silently
    skipping entries on any error.

    Returns:
        Always 0 (exit code).
    """
    start_time = time.time()

    try:
        # Read event from stdin
        event_line = sys.stdin.readline()
        if not event_line:
            return 0

        event = json.loads(event_line)

        # Load mappings
        mappings = load_mappings()

        # Classify the tool
        tool_name = event.get("tool_name", "unknown")
        tool_input = event.get("tool_input", {})
        classification = classify(tool_name, mappings)

        # Evaluate routing rules
        routing_rules = mappings.get("routing", [])
        routing_result = evaluate(tool_name, tool_input, routing_rules)

        # Calculate latency
        elapsed_ms = int((time.time() - start_time) * 1000)

        # Build and append entry
        entry = build_entry(event, classification, routing_result, elapsed_ms)
        log_path = get_log_path()
        append_entry(log_path, entry)

    except Exception:
        # Silently catch all exceptions — entry is skipped
        pass

    return 0
