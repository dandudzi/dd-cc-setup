"""Transcript tailing for the observability pipeline.

Reads the last N lines of a Claude session JSONL transcript to extract
the two intent-based decision factors: previous_tool and is_retry.

Design constraints:
- Never raises — all errors caught, return safe defaults (fail-open).
- No imports from scripts.analyze — this is hot-path code (~1ms/call).
- Returns new dicts (immutable — never mutates input context).
"""
from __future__ import annotations

import json


def tail_transcript(transcript_path: str, max_lines: int = 200) -> list[dict]:
    """Return the last max_lines parsed JSONL entries from the transcript.

    Returns an empty list if the path is empty, missing, or unreadable.
    Malformed lines are silently skipped.
    """
    if not transcript_path:
        return []

    try:
        with open(transcript_path, "rb") as fh:
            lines = _tail_bytes(fh, max_lines)
    except OSError:
        return []

    result = []
    for line in lines:
        try:
            entry = json.loads(line)
            if isinstance(entry, dict):
                result.append(entry)
        except (json.JSONDecodeError, ValueError):
            continue
    return result


def _tail_bytes(fh, max_lines: int) -> list[bytes]:
    """Read the last max_lines lines from an open binary file handle."""
    fh.seek(0, 2)  # seek to end
    file_size = fh.tell()
    if file_size == 0:
        return []

    chunk_size = min(8192, file_size)
    buf = b""
    pos = file_size
    lines: list[bytes] = []

    while pos > 0 and len(lines) <= max_lines:
        read_size = min(chunk_size, pos)
        pos -= read_size
        fh.seek(pos)
        buf = fh.read(read_size) + buf
        lines = buf.split(b"\n")
        # Keep only complete lines (all but the first, which may be partial)
        if pos > 0:
            buf = lines[0]
            lines = lines[1:]
        else:
            # At start of file: all lines are complete
            buf = b""

    # lines already split; drop empty trailing lines
    return [ln for ln in lines[-max_lines:] if ln.strip()]


def find_previous_tool(entries: list[dict]) -> str | None:
    """Return the name of the last tool called in the most recent completed assistant turn.

    Walks entries in reverse, skipping streaming partials (stop_reason=None).
    Returns None if no completed tool call is found.
    """
    for entry in reversed(entries):
        if entry.get("type") != "assistant":
            continue
        message = entry.get("message") or {}
        if message.get("stop_reason") is None:
            continue  # skip streaming partial
        content = message.get("content") or []
        tool_use_blocks = [
            b for b in content if isinstance(b, dict) and b.get("type") == "tool_use"
        ]
        if tool_use_blocks:
            # Last block in the turn is the "most recent" tool in a parallel call
            return tool_use_blocks[-1].get("name")
    return None


def _find_previous_tool_block(entries: list[dict]) -> dict | None:
    """Return the last tool_use block from the most recent completed assistant turn."""
    for entry in reversed(entries):
        if entry.get("type") != "assistant":
            continue
        message = entry.get("message") or {}
        if message.get("stop_reason") is None:
            continue
        content = message.get("content") or []
        tool_use_blocks = [
            b for b in content if isinstance(b, dict) and b.get("type") == "tool_use"
        ]
        if tool_use_blocks:
            return tool_use_blocks[-1]
    return None


def compute_is_retry(
    entries: list[dict],
    current_tool_name: str,
    current_tool_input: dict,
) -> bool:
    """Return True if the current call is an exact repeat of the previous call.

    Same tool name AND same tool input (dict equality) → retry.
    """
    block = _find_previous_tool_block(entries)
    if block is None:
        return False
    return block.get("name") == current_tool_name and block.get("input") == current_tool_input


def enrich_transcript_factors(context: dict) -> dict:
    """Enrich context with previous_tool and is_retry from the session transcript.

    Returns a new dict. If transcript_path is empty or unreadable, returns
    context with factors unchanged (stays None — fail-open).
    """
    transcript_path = context.get("transcript_path", "")
    if not transcript_path:
        return dict(context)

    entries = tail_transcript(transcript_path)
    if not entries:
        return dict(context)

    previous_tool = find_previous_tool(entries)
    is_retry = compute_is_retry(
        entries,
        context.get("tool_name", ""),
        context.get("tool_input", {}),
    )

    updated = dict(context)
    updated["previous_tool"] = previous_tool
    updated["is_retry"] = is_retry
    return updated
