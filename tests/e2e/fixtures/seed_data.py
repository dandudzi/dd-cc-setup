"""Minimal fixture transcript data for hermetic E2E tests.

Creates a ~/.claude/projects-compatible directory layout with enough JSONL data
for the Observatory app to load past its st.stop() gate.
"""
from __future__ import annotations

import json
from pathlib import Path

# Two assistant turns with different tools so F2 has per-category data to display.
# Turn 1: Read (cache hit — cache_read > 0, cache_creation == 0)
# Turn 2: jCodeMunch (partial hit — cache_read > 0, cache_creation > 0)
_ENTRIES = [
    {"type": "system", "content": [{"type": "text", "text": "system prompt"}]},
    {"type": "user", "message": {"content": []}, "permissionMode": "default"},
    {
        "type": "assistant",
        "requestId": "req-fixture-001",
        "message": {
            "stop_reason": "end_turn",
            "content": [
                {
                    "type": "tool_use",
                    "id": "tu-1",
                    "name": "Read",
                    "input": {"file_path": "/tmp/test.py"},
                }
            ],
            "usage": {
                "input_tokens": 1000,
                "output_tokens": 200,
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 500,
            },
        },
    },
    {
        "type": "user",
        "message": {
            "content": [{"type": "tool_result", "tool_use_id": "tu-1", "content": "file content"}]
        },
        "permissionMode": "default",
    },
    {
        "type": "assistant",
        "requestId": "req-fixture-002",
        "message": {
            "stop_reason": "end_turn",
            "content": [
                {
                    "type": "tool_use",
                    "id": "tu-2",
                    "name": "mcp__jcodemunch__get_file_content",
                    "input": {"symbol_id": "foo"},
                }
            ],
            "usage": {
                "input_tokens": 800,
                "output_tokens": 150,
                "cache_creation_input_tokens": 50,
                "cache_read_input_tokens": 300,
            },
        },
    },
]


def seed_fixture_transcripts(base_dir: Path) -> Path:
    """Write a minimal JSONL transcript into base_dir/<project>/<session>.jsonl.

    The layout matches what discover_transcripts() expects:
        base_dir/
          e2e-fixture-project/
            session-fixture-001.jsonl

    Returns base_dir for convenience.
    """
    project_dir = base_dir / "e2e-fixture-project"
    project_dir.mkdir(parents=True, exist_ok=True)
    session_file = project_dir / "session-fixture-001.jsonl"
    session_file.write_text(
        "\n".join(json.dumps(entry) for entry in _ENTRIES) + "\n",
        encoding="utf-8",
    )
    return base_dir
