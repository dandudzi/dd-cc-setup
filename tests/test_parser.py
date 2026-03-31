"""Tests for scripts/analyze/parser.py — transcript discovery and parsing."""
import json
from pathlib import Path

from scripts.analyze.parser import (
    ApiCall,
    TokenUsage,
    ToolCall,
    deduplicate_api_calls,
    discover_transcripts,
    extract_tool_sequence,
    parse_session,
)


def _u(inp: int = 100, out: int = 50) -> dict:
    """Compact usage dict for tests."""
    return {
        "input_tokens": inp,
        "output_tokens": out,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0,
    }

# ---------------------------------------------------------------------------
# Factories
# ---------------------------------------------------------------------------


def _assistant_entry(**overrides) -> dict:
    """Minimal valid assistant transcript entry."""
    base = {
        "type": "assistant",
        "requestId": "req-1",
        "message": {
            "stop_reason": "end_turn",
            "content": [],
            "usage": {
                "input_tokens": 100,
                "output_tokens": 50,
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 0,
            },
        },
    }
    # Deep merge message overrides
    if "message" in overrides:
        msg_overrides = overrides.pop("message")
        base["message"].update(msg_overrides)
    base.update(overrides)
    return base


def _user_entry(**overrides) -> dict:
    """Minimal valid user transcript entry."""
    base = {
        "type": "user",
        "message": {
            "content": [],
        },
        "permissionMode": "default",
    }
    if "message" in overrides:
        msg_overrides = overrides.pop("message")
        base["message"].update(msg_overrides)
    base.update(overrides)
    return base


def _tool_use_block(tool_use_id: str = "tu-1", name: str = "Read", **inp) -> dict:
    return {
        "type": "tool_use",
        "id": tool_use_id,
        "name": name,
        "input": inp or {"file_path": "/src/app.py"},
    }


def _tool_result_block(tool_use_id: str = "tu-1", content: str = "file content") -> dict:
    return {
        "type": "tool_result",
        "tool_use_id": tool_use_id,
        "content": content,
    }


# ---------------------------------------------------------------------------
# TestDiscoverTranscripts
# ---------------------------------------------------------------------------


class TestDiscoverTranscripts:
    def test_finds_jsonl_in_project_dir(self, tmp_path: Path):
        proj = tmp_path / "proj-abc"
        proj.mkdir()
        jsonl = proj / "session-1.jsonl"
        jsonl.write_text("")
        results = discover_transcripts(tmp_path)
        assert len(results) == 1
        assert results[0].path == jsonl
        assert results[0].session_id == "session-1"
        assert results[0].is_subagent is False

    def test_skips_non_jsonl_files(self, tmp_path: Path):
        proj = tmp_path / "proj-abc"
        proj.mkdir()
        (proj / "notes.txt").write_text("")
        results = discover_transcripts(tmp_path)
        assert results == []

    def test_finds_subagent_jsonl(self, tmp_path: Path):
        proj = tmp_path / "proj-abc"
        sub = proj / "subagent-xyz"
        sub.mkdir(parents=True)
        (sub / "session-2.jsonl").write_text("")
        results = discover_transcripts(tmp_path)
        assert len(results) == 1
        assert results[0].is_subagent is True
        assert results[0].agent_id == "subagent-xyz"

    def test_reads_agent_type_from_meta(self, tmp_path: Path):
        proj = tmp_path / "proj-abc"
        sub = proj / "subagent-xyz"
        sub.mkdir(parents=True)
        meta = sub / ".meta.json"
        meta.write_text(json.dumps({"agentType": "python-reviewer"}))
        (sub / "session-2.jsonl").write_text("")
        results = discover_transcripts(tmp_path)
        assert results[0].agent_type == "python-reviewer"

    def test_empty_base_dir_returns_empty(self, tmp_path: Path):
        results = discover_transcripts(tmp_path)
        assert results == []

    def test_multiple_sessions_in_project(self, tmp_path: Path):
        proj = tmp_path / "proj-abc"
        proj.mkdir()
        (proj / "session-1.jsonl").write_text("")
        (proj / "session-2.jsonl").write_text("")
        results = discover_transcripts(tmp_path)
        assert len(results) == 2


# ---------------------------------------------------------------------------
# TestParseSession
# ---------------------------------------------------------------------------


class TestParseSession:
    def test_yields_valid_assistant_entry(self, tmp_path: Path):
        entry = _assistant_entry()
        f = tmp_path / "s.jsonl"
        f.write_text(json.dumps(entry) + "\n")
        entries = list(parse_session(f))
        assert len(entries) == 1
        assert entries[0]["type"] == "assistant"

    def test_yields_valid_user_entry(self, tmp_path: Path):
        entry = _user_entry()
        f = tmp_path / "s.jsonl"
        f.write_text(json.dumps(entry) + "\n")
        entries = list(parse_session(f))
        assert len(entries) == 1
        assert entries[0]["type"] == "user"

    def test_skips_malformed_lines(self, tmp_path: Path):
        f = tmp_path / "s.jsonl"
        f.write_text("not json\n" + json.dumps(_assistant_entry()) + "\n")
        entries = list(parse_session(f))
        assert len(entries) == 1

    def test_empty_file_returns_empty(self, tmp_path: Path):
        f = tmp_path / "s.jsonl"
        f.write_text("")
        assert list(parse_session(f)) == []

    def test_yields_both_assistant_and_user_entries(self, tmp_path: Path):
        lines = [
            json.dumps(_assistant_entry()),
            json.dumps(_user_entry()),
        ]
        f = tmp_path / "s.jsonl"
        f.write_text("\n".join(lines) + "\n")
        entries = list(parse_session(f))
        assert len(entries) == 2
        types = {e["type"] for e in entries}
        assert types == {"assistant", "user"}

    def test_skips_non_assistant_non_user_entries(self, tmp_path: Path):
        lines = [
            json.dumps({"type": "system", "content": "hello"}),
            json.dumps(_assistant_entry()),
        ]
        f = tmp_path / "s.jsonl"
        f.write_text("\n".join(lines) + "\n")
        entries = list(parse_session(f))
        assert len(entries) == 1


# ---------------------------------------------------------------------------
# TestDeduplicateApiCalls
# ---------------------------------------------------------------------------


class TestDeduplicateApiCalls:
    def test_single_complete_entry(self):
        entry = _assistant_entry(requestId="req-1")
        calls = deduplicate_api_calls([entry], session_id="sess-1")
        assert len(calls) == 1
        assert calls[0].request_id == "req-1"
        assert calls[0].stop_reason == "end_turn"

    def test_streaming_chunks_keeps_final(self):
        # Two chunks: first partial (stop_reason=None), second complete
        partial = _assistant_entry(
            requestId="req-1",
            message={"stop_reason": None, "content": [], "usage": _u(10, 5)},
        )
        final = _assistant_entry(
            requestId="req-1",
            message={"stop_reason": "end_turn", "content": [], "usage": _u(100, 50)},
        )
        calls = deduplicate_api_calls([partial, final], session_id="sess-1")
        assert len(calls) == 1
        assert calls[0].usage.output_tokens == 50

    def test_orphan_partials_skipped(self):
        # All chunks have stop_reason=None — orphan, should be skipped
        partial1 = _assistant_entry(
            requestId="req-1",
            message={"stop_reason": None, "content": [], "usage": _u(10, 5)},
        )
        partial2 = _assistant_entry(
            requestId="req-1",
            message={"stop_reason": None, "content": [], "usage": _u(20, 8)},
        )
        calls = deduplicate_api_calls([partial1, partial2], session_id="sess-1")
        assert calls == []

    def test_extracts_tool_calls(self):
        tool_block = _tool_use_block("tu-1", "Read", file_path="/src/app.py")
        entry = _assistant_entry(
            requestId="req-1",
            message={"stop_reason": "tool_use", "content": [tool_block], "usage": _u()},
        )
        calls = deduplicate_api_calls([entry], session_id="sess-1")
        assert len(calls[0].tool_calls) == 1
        tc = calls[0].tool_calls[0]
        assert tc.name == "Read"
        assert tc.tool_use_id == "tu-1"

    def test_extracts_file_path_and_ext(self):
        tool_block = _tool_use_block("tu-1", "Read", file_path="/src/app.py")
        entry = _assistant_entry(
            requestId="req-1",
            message={"stop_reason": "tool_use", "content": [tool_block], "usage": _u()},
        )
        calls = deduplicate_api_calls([entry], session_id="sess-1")
        tc = calls[0].tool_calls[0]
        assert tc.file_path == "/src/app.py"
        assert tc.file_ext == ".py"

    def test_correlates_tool_results_from_user_entry(self):
        tool_block = _tool_use_block("tu-1", "Read", file_path="/src/app.py")
        assistant = _assistant_entry(
            requestId="req-1",
            message={"stop_reason": "tool_use", "content": [tool_block], "usage": _u()},
        )
        result_block = _tool_result_block("tu-1", "file content here")
        user = _user_entry(message={"content": [result_block]})
        calls = deduplicate_api_calls([assistant, user], session_id="sess-1")
        assert len(calls[0].tool_results) == 1
        tr = calls[0].tool_results[0]
        assert tr.tool_use_id == "tu-1"
        assert tr.content_length == len("file content here")

    def test_permission_mode_from_user_entry(self):
        assistant = _assistant_entry(requestId="req-1")
        user = _user_entry(permissionMode="bypassPermissions")
        calls = deduplicate_api_calls([user, assistant], session_id="sess-1")
        assert calls[0].permission_mode == "bypassPermissions"

    def test_multi_tool_calls_in_one_entry(self):
        blocks = [
            _tool_use_block("tu-1", "Read", file_path="/a.py"),
            _tool_use_block("tu-2", "Edit", file_path="/b.py"),
        ]
        entry = _assistant_entry(
            requestId="req-1",
            message={"stop_reason": "tool_use", "content": blocks, "usage": _u(100, 80)},
        )
        calls = deduplicate_api_calls([entry], session_id="sess-1")
        assert len(calls[0].tool_calls) == 2

    def test_multiple_requests_deduplicated_independently(self):
        e1 = _assistant_entry(requestId="req-1")
        e2 = _assistant_entry(requestId="req-2")
        calls = deduplicate_api_calls([e1, e2], session_id="sess-1")
        assert len(calls) == 2
        ids = {c.request_id for c in calls}
        assert ids == {"req-1", "req-2"}


# ---------------------------------------------------------------------------
# TestExtractToolSequence
# ---------------------------------------------------------------------------


class TestExtractToolSequence:
    def _make_api_call(self, tool_calls: list[ToolCall]) -> ApiCall:
        return ApiCall(
            request_id="req-1",
            session_id="sess-1",
            agent_id=None,
            permission_mode="default",
            stop_reason="end_turn",
            tool_calls=tuple(tool_calls),
            tool_results=(),
            usage=TokenUsage(100, 50, 0, 0),
        )

    def _make_tool_call(self, name: str, tool_use_id: str = "tu-1") -> ToolCall:
        return ToolCall(
            name=name,
            tool_use_id=tool_use_id,
            input={"file_path": "/src/app.py"},
            file_path="/src/app.py",
            file_ext=".py",
        )

    def test_empty_returns_empty(self):
        assert extract_tool_sequence([]) == []

    def test_single_call_in_order(self):
        tc = self._make_tool_call("Read")
        api = self._make_api_call([tc])
        seq = extract_tool_sequence([api])
        assert seq == [tc]

    def test_preserves_order_across_calls(self):
        tc1 = self._make_tool_call("Read", "tu-1")
        tc2 = self._make_tool_call("Edit", "tu-2")
        api1 = self._make_api_call([tc1])
        api2 = self._make_api_call([tc2])
        seq = extract_tool_sequence([api1, api2])
        assert [t.name for t in seq] == ["Read", "Edit"]

    def test_multiple_tools_per_call_flattened(self):
        tc1 = self._make_tool_call("Read", "tu-1")
        tc2 = self._make_tool_call("Grep", "tu-2")
        api = self._make_api_call([tc1, tc2])
        seq = extract_tool_sequence([api])
        assert len(seq) == 2
