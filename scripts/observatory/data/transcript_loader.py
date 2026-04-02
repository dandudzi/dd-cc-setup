"""Transcript loading for the Observatory analysis tool.

Wraps scripts/analyze/parser to load and filter ApiCall objects.
Returns list[ApiCall] — token usage lives at the turn level, not per tool.
Each caller (report) decides how to slice the data.
"""
from __future__ import annotations

from pathlib import Path

from scripts.observatory.data.parser import ApiCall, deduplicate_api_calls, discover_transcripts, parse_session
from scripts.observatory.data.filters import FilterSpec, filter_transcripts

_DEFAULT_BASE_DIR = Path.home() / ".claude" / "projects"


def load_api_calls(
    spec: FilterSpec,
    base_dir: Path | None = None,
) -> list[ApiCall]:
    """Discover, filter, parse and deduplicate transcripts.

    Args:
        spec: Filter criteria (projects, sessions, date range).
        base_dir: Root of ~/.claude/projects/. Defaults to the real path.

    Returns:
        Flat list of deduplicated ApiCall objects across all matching sessions.
    """
    root = base_dir or _DEFAULT_BASE_DIR
    all_transcripts = discover_transcripts(root)
    filtered = filter_transcripts(all_transcripts, spec)

    result: list[ApiCall] = []
    for tf in filtered:
        raw_entries = list(parse_session(tf.path))
        api_calls = deduplicate_api_calls(raw_entries, tf.session_id, tf.agent_id)
        result.extend(api_calls)
    return result
