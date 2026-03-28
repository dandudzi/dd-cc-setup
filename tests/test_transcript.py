"""Tests for scripts/transcript.py — transcript tailing and factor extraction."""
import json
from pathlib import Path

from scripts.transcript import (
    compute_is_retry,
    enrich_transcript_factors,
    find_previous_tool,
    tail_transcript,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _assistant(tool_name: str, tool_input: dict, request_id: str = "req-1") -> dict:
    """Minimal completed assistant entry with a single tool_use block."""
    return {
        "type": "assistant",
        "requestId": request_id,
        "message": {
            "stop_reason": "tool_use",
            "content": [
                {
                    "type": "tool_use",
                    "id": "tu-1",
                    "name": tool_name,
                    "input": tool_input,
                }
            ],
            "usage": {"input_tokens": 100, "output_tokens": 50},
        },
    }


def _assistant_multi(tools: list[tuple[str, dict]], request_id: str = "req-1") -> dict:
    """Assistant entry with multiple tool_use blocks."""
    return {
        "type": "assistant",
        "requestId": request_id,
        "message": {
            "stop_reason": "tool_use",
            "content": [
                {"type": "tool_use", "id": f"tu-{i}", "name": name, "input": inp}
                for i, (name, inp) in enumerate(tools, start=1)
            ],
            "usage": {"input_tokens": 100, "output_tokens": 50},
        },
    }


def _assistant_streaming(tool_name: str, tool_input: dict) -> dict:
    """Partial streaming chunk — stop_reason is None."""
    return {
        "type": "assistant",
        "requestId": "req-partial",
        "message": {
            "stop_reason": None,
            "content": [
                {"type": "tool_use", "id": "tu-p", "name": tool_name, "input": tool_input}
            ],
            "usage": {"input_tokens": 10, "output_tokens": 5},
        },
    }


def _user() -> dict:
    return {
        "type": "user",
        "message": {"content": [{"type": "tool_result", "tool_use_id": "tu-1", "content": "ok"}]},
        "permissionMode": "default",
    }


def _write_jsonl(path: Path, entries: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(e) for e in entries) + "\n")


def _context(**overrides) -> dict:
    base = {
        "session_id": "sess-1",
        "tool_use_id": "tu-cur",
        "tool_name": "Read",
        "tool_input": {"file_path": "/src/app.py"},
        "transcript_path": "",
        "previous_tool": None,
        "is_retry": None,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# TestTailTranscript
# ---------------------------------------------------------------------------


class TestTailTranscript:
    def test_reads_parsed_entries_from_jsonl(self, tmp_path: Path):
        f = tmp_path / "t.jsonl"
        entries = [_assistant("Read", {"file_path": "/a.py"}), _user()]
        _write_jsonl(f, entries)
        result = tail_transcript(str(f))
        assert len(result) == 2
        assert result[0]["type"] == "assistant"

    def test_empty_file_returns_empty(self, tmp_path: Path):
        f = tmp_path / "t.jsonl"
        f.write_text("")
        assert tail_transcript(str(f)) == []

    def test_nonexistent_file_returns_empty(self, tmp_path: Path):
        assert tail_transcript(str(tmp_path / "missing.jsonl")) == []

    def test_empty_path_returns_empty(self):
        assert tail_transcript("") == []

    def test_malformed_lines_skipped(self, tmp_path: Path):
        f = tmp_path / "t.jsonl"
        f.write_text("not json\n" + json.dumps(_user()) + "\n")
        result = tail_transcript(str(f))
        assert len(result) == 1
        assert result[0]["type"] == "user"

    def test_respects_max_lines(self, tmp_path: Path):
        f = tmp_path / "t.jsonl"
        # Write 10 entries; max_lines=4 should return at most 4
        entries = [_assistant(f"Tool{i}", {}) for i in range(10)]
        _write_jsonl(f, entries)
        result = tail_transcript(str(f), max_lines=4)
        assert len(result) <= 4

    def test_never_raises_on_permission_error(self, tmp_path: Path):
        # Passing an invalid path (a directory) should return empty, not raise
        result = tail_transcript(str(tmp_path))  # directory, not a file
        assert result == []


# ---------------------------------------------------------------------------
# TestFindPreviousTool
# ---------------------------------------------------------------------------


class TestFindPreviousTool:
    def test_finds_last_tool_use_name(self):
        entries = [_assistant("Read", {"file_path": "/a.py"}), _user()]
        assert find_previous_tool(entries) == "Read"

    def test_multi_tool_entry_returns_last_tool(self):
        entry = _assistant_multi([("Read", {}), ("Grep", {"pattern": "foo"})])
        # Last tool_use block should be "Grep"
        assert find_previous_tool([entry]) == "Grep"

    def test_no_assistant_entries_returns_none(self):
        assert find_previous_tool([_user()]) is None

    def test_empty_entries_returns_none(self):
        assert find_previous_tool([]) is None

    def test_no_tool_use_blocks_returns_none(self):
        entry = {
            "type": "assistant",
            "requestId": "req-1",
            "message": {
                "stop_reason": "end_turn",
                "content": [{"type": "text", "text": "hello"}],
                "usage": {"input_tokens": 10, "output_tokens": 5},
            },
        }
        assert find_previous_tool([entry]) is None

    def test_skips_streaming_partials(self):
        # Streaming partial (stop_reason=None) should be skipped
        partial = _assistant_streaming("Edit", {"file_path": "/b.py"})
        completed = _assistant("Read", {"file_path": "/a.py"}, request_id="req-2")
        # completed appears before partial in the list
        entries = [completed, _user(), partial]
        result = find_previous_tool(entries)
        # Must return the completed entry's tool, not the partial
        assert result == "Read"

    def test_returns_most_recent_completed_tool(self):
        older = _assistant("Read", {"file_path": "/a.py"}, request_id="req-1")
        newer = _assistant("Edit", {"file_path": "/b.py"}, request_id="req-2")
        entries = [older, _user(), newer, _user()]
        assert find_previous_tool(entries) == "Edit"


# ---------------------------------------------------------------------------
# TestComputeIsRetry
# ---------------------------------------------------------------------------


class TestComputeIsRetry:
    def test_same_tool_same_input_is_true(self):
        inp = {"file_path": "/src/app.py"}
        entries = [_assistant("Read", inp)]
        assert compute_is_retry(entries, "Read", inp) is True

    def test_same_tool_different_input_is_false(self):
        entries = [_assistant("Read", {"file_path": "/a.py"})]
        assert compute_is_retry(entries, "Read", {"file_path": "/b.py"}) is False

    def test_different_tool_is_false(self):
        inp = {"file_path": "/a.py"}
        entries = [_assistant("Read", inp)]
        assert compute_is_retry(entries, "Grep", inp) is False

    def test_no_previous_tool_is_false(self):
        assert compute_is_retry([], "Read", {"file_path": "/a.py"}) is False

    def test_only_user_entries_is_false(self):
        assert compute_is_retry([_user()], "Read", {}) is False


# ---------------------------------------------------------------------------
# TestEnrichTranscriptFactors
# ---------------------------------------------------------------------------


class TestEnrichTranscriptFactors:
    def test_populates_previous_tool(self, tmp_path: Path):
        f = tmp_path / "t.jsonl"
        _write_jsonl(f, [_assistant("Edit", {"file_path": "/a.py"}), _user()])
        ctx = _context(transcript_path=str(f))
        result = enrich_transcript_factors(ctx)
        assert result["previous_tool"] == "Edit"

    def test_populates_is_retry_true(self, tmp_path: Path):
        inp = {"file_path": "/src/app.py"}
        f = tmp_path / "t.jsonl"
        _write_jsonl(f, [_assistant("Read", inp)])
        ctx = _context(tool_name="Read", tool_input=inp, transcript_path=str(f))
        result = enrich_transcript_factors(ctx)
        assert result["is_retry"] is True

    def test_populates_is_retry_false(self, tmp_path: Path):
        f = tmp_path / "t.jsonl"
        _write_jsonl(f, [_assistant("Edit", {"file_path": "/a.py"})])
        ctx = _context(tool_name="Read", tool_input={"file_path": "/b.py"}, transcript_path=str(f))
        result = enrich_transcript_factors(ctx)
        assert result["is_retry"] is False

    def test_empty_transcript_path_returns_unchanged(self):
        ctx = _context(transcript_path="")
        result = enrich_transcript_factors(ctx)
        assert result["previous_tool"] is None
        assert result["is_retry"] is None

    def test_missing_file_returns_unchanged(self, tmp_path: Path):
        ctx = _context(transcript_path=str(tmp_path / "missing.jsonl"))
        result = enrich_transcript_factors(ctx)
        assert result["previous_tool"] is None
        assert result["is_retry"] is None

    def test_immutability(self, tmp_path: Path):
        f = tmp_path / "t.jsonl"
        _write_jsonl(f, [_assistant("Edit", {})])
        ctx = _context(transcript_path=str(f))
        original_previous_tool = ctx["previous_tool"]
        enrich_transcript_factors(ctx)
        # Original must not be mutated
        assert ctx["previous_tool"] == original_previous_tool

    def test_unknown_keys_preserved(self, tmp_path: Path):
        f = tmp_path / "t.jsonl"
        _write_jsonl(f, [_assistant("Read", {})])
        ctx = _context(transcript_path=str(f))
        ctx["custom_key"] = "custom_value"
        result = enrich_transcript_factors(ctx)
        assert result["custom_key"] == "custom_value"
