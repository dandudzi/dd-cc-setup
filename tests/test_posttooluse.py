"""Tests for scripts/analyze/posttooluse.py — R6 PostToolUse savings analysis.

TDD: tests written before implementation (RED phase).
All extraction functions operate on deduplicated ApiCall objects to avoid
streaming chunk double-counting.
"""
from __future__ import annotations

from scripts.analyze.parser import ApiCall, TokenUsage, ToolCall, ToolResult
from scripts.analyze.posttooluse import (
    R3_MEAN_DETOUR_COST,
    R5_MEAN_CHAIN_COST,
    IndexCall,
    WriteEditEvent,
    build_error_map,
    compute_counterfactual,
    extract_deny_events,
    extract_index_calls,
    extract_write_edit_events,
)

# ---------------------------------------------------------------------------
# Factories
# ---------------------------------------------------------------------------


def _tool_call(
    name: str,
    tool_use_id: str = "tu-1",
    file_path: str | None = None,
) -> ToolCall:
    fp = file_path
    ext = None
    if fp:
        ext = "." + fp.rsplit(".", 1)[-1] if "." in fp.split("/")[-1] else None
    inp: dict = {}
    if name in ("Read", "Write", "Edit", "MultiEdit"):
        inp = {"file_path": fp or "/src/app.py"}
    elif name == "Bash":
        inp = {"command": "ls"}
    return ToolCall(
        name=name,
        tool_use_id=tool_use_id,
        input=inp,
        file_path=fp,
        file_ext=ext,
    )


def _bash_call(tool_use_id: str, command: str) -> ToolCall:
    return ToolCall(
        name="Bash",
        tool_use_id=tool_use_id,
        input={"command": command},
        file_path=None,
        file_ext=None,
    )


def _api_call(
    tool_calls: list[ToolCall],
    tool_results: list[ToolResult] | None = None,
    output_tokens: int = 100,
    request_id: str = "req-1",
    session_id: str = "sess-1",
) -> ApiCall:
    return ApiCall(
        request_id=request_id,
        session_id=session_id,
        agent_id=None,
        permission_mode="default",
        stop_reason="tool_use",
        tool_calls=tuple(tool_calls),
        tool_results=tuple(tool_results or []),
        usage=TokenUsage(50, output_tokens, 0, 0),
    )


def _deny_result(tool_use_id: str) -> ToolResult:
    return ToolResult(tool_use_id=tool_use_id, content_length=50)


def _user_entry_deny(tool_use_id: str, error_text: str, is_error: bool = True) -> dict:
    """Raw user entry with a denied tool_result (for build_error_map)."""
    return {
        "type": "user",
        "message": {
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": tool_use_id,
                    "is_error": is_error,
                    "content": error_text,
                }
            ]
        },
    }


def _user_entry_success(tool_use_id: str, content: str = "ok") -> dict:
    """Raw user entry with a successful tool_result."""
    return {
        "type": "user",
        "message": {
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": tool_use_id,
                    "is_error": False,
                    "content": content,
                }
            ]
        },
    }


def _user_entry_list_content(tool_use_id: str, text: str, is_error: bool) -> dict:
    """Raw user entry with list-style content blocks."""
    return {
        "type": "user",
        "message": {
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": tool_use_id,
                    "is_error": is_error,
                    "content": [{"type": "text", "text": text}],
                }
            ]
        },
    }


# ---------------------------------------------------------------------------
# TestBuildErrorMap
# ---------------------------------------------------------------------------


class TestBuildErrorMap:
    def test_detects_is_error_true(self):
        entries = [_user_entry_deny("tu-1", "BLOCKED: use jCodeMunch")]
        result = build_error_map(entries)
        assert "tu-1" in result
        assert result["tu-1"][0] is True

    def test_captures_error_text(self):
        entries = [_user_entry_deny("tu-1", "denied this tool")]
        result = build_error_map(entries)
        assert "denied this tool" in result["tu-1"][1]

    def test_detects_blocked_pattern_without_is_error_flag(self):
        # Some hook output may lack is_error=True but contain BLOCKED text
        entries = [_user_entry_deny("tu-2", "BLOCKED: read router", is_error=False)]
        result = build_error_map(entries)
        assert result["tu-2"][0] is True

    def test_detects_no_stderr_output_pattern(self):
        entries = [_user_entry_deny("tu-3", "hook error: No stderr output", is_error=False)]
        result = build_error_map(entries)
        assert result["tu-3"][0] is True

    def test_clean_success_is_not_deny(self):
        entries = [_user_entry_success("tu-4", '{"content": "file contents"}')]
        result = build_error_map(entries)
        assert "tu-4" in result
        assert result["tu-4"][0] is False

    def test_list_content_extracted(self):
        entries = [_user_entry_list_content("tu-5", "BLOCKED: use MCP", is_error=True)]
        result = build_error_map(entries)
        assert result["tu-5"][0] is True
        assert "BLOCKED" in result["tu-5"][1]

    def test_skips_non_user_entries(self):
        entries = [
            {"type": "assistant", "message": {"content": []}},
            _user_entry_deny("tu-6", "BLOCKED"),
        ]
        result = build_error_map(entries)
        assert "tu-6" in result
        assert len(result) == 1

    def test_multiple_results_in_one_entry(self):
        entry = {
            "type": "user",
            "message": {
                "content": [
                    {"type": "tool_result", "tool_use_id": "tu-7",
                     "is_error": True, "content": "BLOCKED"},
                    {"type": "tool_result", "tool_use_id": "tu-8",
                     "is_error": False, "content": "ok"},
                ]
            },
        }
        result = build_error_map([entry])
        assert result["tu-7"][0] is True
        assert result["tu-8"][0] is False


# ---------------------------------------------------------------------------
# TestExtractDenyEvents
# ---------------------------------------------------------------------------


class TestExtractDenyEvents:
    def test_returns_deny_for_errored_result(self):
        tc = _tool_call("Read", "tu-1")
        call = _api_call([tc], tool_results=[_deny_result("tu-1")], output_tokens=150)
        error_map = {"tu-1": (True, "BLOCKED: use jCodeMunch")}

        events = extract_deny_events([call], error_map, "sess-1")

        assert len(events) == 1
        assert events[0].tool_name == "Read"
        assert events[0].tool_use_id == "tu-1"

    def test_output_tokens_from_deduplicated_call(self):
        tc = _tool_call("Read", "tu-1")
        call = _api_call([tc], tool_results=[_deny_result("tu-1")], output_tokens=237)
        error_map = {"tu-1": (True, "BLOCKED")}

        events = extract_deny_events([call], error_map, "sess-1")

        assert events[0].output_tokens == 237

    def test_ignores_successful_results(self):
        tc = _tool_call("Read", "tu-1")
        result = ToolResult(tool_use_id="tu-1", content_length=500)
        call = _api_call([tc], tool_results=[result], output_tokens=100)
        error_map = {"tu-1": (False, "file contents here")}

        events = extract_deny_events([call], error_map, "sess-1")

        assert events == []

    def test_no_results_no_deny(self):
        tc = _tool_call("Read", "tu-1")
        call = _api_call([tc], tool_results=[], output_tokens=100)
        error_map = {}

        events = extract_deny_events([call], error_map, "sess-1")

        assert events == []

    def test_session_id_propagated(self):
        tc = _tool_call("Bash", "tu-1")
        call = _api_call([tc], tool_results=[_deny_result("tu-1")], output_tokens=50)
        error_map = {"tu-1": (True, "hook error")}

        events = extract_deny_events([call], error_map, "my-session")

        assert events[0].session_id == "my-session"

    def test_multiple_denies_in_sequence(self):
        calls = [
            _api_call(
                [_tool_call("Read", f"tu-{i}")],
                tool_results=[_deny_result(f"tu-{i}")],
                request_id=f"req-{i}",
            )
            for i in range(3)
        ]
        error_map = {f"tu-{i}": (True, "BLOCKED") for i in range(3)}

        events = extract_deny_events(calls, error_map, "sess-1")

        assert len(events) == 3


# ---------------------------------------------------------------------------
# TestExtractIndexCalls
# ---------------------------------------------------------------------------


class TestExtractIndexCalls:
    def _make_sequence(
        self, tool_names: list[str], deny_indices: list[int] | None = None
    ) -> tuple:
        """Build (api_calls, error_map) for a sequence of tool names."""
        if deny_indices is None:
            deny_indices = []
        calls = []
        error_map: dict = {}
        for i, name in enumerate(tool_names):
            tc = _tool_call(name, f"tu-{i}")
            results = []
            if i in deny_indices:
                results = [_deny_result(f"tu-{i}")]
                error_map[f"tu-{i}"] = (True, "BLOCKED")
            else:
                results = [ToolResult(tool_use_id=f"tu-{i}", content_length=100)]
                error_map[f"tu-{i}"] = (False, "ok")
            calls.append(
                _api_call([tc], tool_results=results, output_tokens=100, request_id=f"req-{i}")
            )
        return calls, error_map

    def test_detects_index_folder(self):
        calls, error_map = self._make_sequence(["mcp__jcodemunch__index_folder"])
        result = extract_index_calls(calls, error_map, "sess-1")
        assert len(result) == 1
        assert "index_folder" in result[0].tool_name

    def test_detects_index_local(self):
        calls, error_map = self._make_sequence(["mcp__jdocmunch__index_local"])
        result = extract_index_calls(calls, error_map, "sess-1")
        assert len(result) == 1
        assert "index_local" in result[0].tool_name

    def test_post_deny_trigger(self):
        # Read (denied) → index_folder
        calls, error_map = self._make_sequence(
            ["Read", "mcp__jcodemunch__index_folder"], deny_indices=[0]
        )
        result = extract_index_calls(calls, error_map, "sess-1")
        assert result[0].trigger == "post_deny"

    def test_post_toolsearch_trigger(self):
        # ToolSearch → index_folder
        calls, error_map = self._make_sequence(["ToolSearch", "mcp__jcodemunch__index_folder"])
        result = extract_index_calls(calls, error_map, "sess-1")
        assert result[0].trigger == "post_toolsearch"

    def test_other_trigger_when_no_context(self):
        # Just an index call with no prior deny or ToolSearch
        calls, error_map = self._make_sequence(["Write", "Edit", "mcp__jcodemunch__index_folder"])
        result = extract_index_calls(calls, error_map, "sess-1")
        assert result[0].trigger == "other"

    def test_deny_wins_over_toolsearch(self):
        # Both deny and ToolSearch in window — deny takes priority (closer)
        calls, error_map = self._make_sequence(
            ["ToolSearch", "Read", "mcp__jcodemunch__index_folder"],
            deny_indices=[1],
        )
        result = extract_index_calls(calls, error_map, "sess-1")
        assert result[0].trigger == "post_deny"

    def test_chain_cost_includes_deny_call(self):
        # deny call (200 tok) + index call (150 tok) → chain = 350
        tc_read = _tool_call("Read", "tu-0")
        tc_index = _tool_call("mcp__jcodemunch__index_folder", "tu-1")
        deny_call = _api_call(
            [tc_read], tool_results=[_deny_result("tu-0")], output_tokens=200, request_id="req-0"
        )
        index_call = _api_call([tc_index], tool_results=[], output_tokens=150, request_id="req-1")
        error_map = {"tu-0": (True, "BLOCKED"), "tu-1": (False, "ok")}

        result = extract_index_calls([deny_call, index_call], error_map, "sess-1")

        assert result[0].chain_cost_tokens == 350

    def test_no_index_calls_returns_empty(self):
        calls, error_map = self._make_sequence(["Read", "Write", "Edit"])
        result = extract_index_calls(calls, error_map, "sess-1")
        assert result == []

    def test_outside_lookback_window_is_other(self):
        # Deny at position 0, index at position 5 — outside default lookback of 3
        calls, error_map = self._make_sequence(
            ["Read", "Edit", "Write", "Bash", "Glob", "mcp__jcodemunch__index_folder"],
            deny_indices=[0],
        )
        result = extract_index_calls(calls, error_map, "sess-1")
        assert result[0].trigger == "other"


# ---------------------------------------------------------------------------
# TestExtractWriteEditEvents
# ---------------------------------------------------------------------------


class TestExtractWriteEditEvents:
    def test_detects_write(self):
        tc = _tool_call("Write", "tu-1", file_path="/src/app.py")
        call = _api_call([tc], output_tokens=100)

        events, _ = extract_write_edit_events([call], "sess-1")

        assert len(events) == 1
        assert events[0].tool_name == "Write"

    def test_detects_edit(self):
        tc = _tool_call("Edit", "tu-1", file_path="/src/app.ts")
        call = _api_call([tc])

        events, _ = extract_write_edit_events([call], "sess-1")

        assert events[0].tool_name == "Edit"

    def test_detects_multiedit(self):
        tc = _tool_call("MultiEdit", "tu-1", file_path="/src/app.py")
        call = _api_call([tc])

        events, _ = extract_write_edit_events([call], "sess-1")

        assert events[0].tool_name == "MultiEdit"

    def test_file_ext_extracted(self):
        tc = _tool_call("Write", "tu-1", file_path="/repo/module.py")
        call = _api_call([tc])

        events, _ = extract_write_edit_events([call], "sess-1")

        assert events[0].file_ext == ".py"

    def test_ignores_read_and_glob(self):
        calls = [
            _api_call([_tool_call("Read", "tu-1")]),
            _api_call([_tool_call("Glob", "tu-2")]),
        ]
        events, bash_creates = extract_write_edit_events(calls, "sess-1")
        assert events == []
        assert bash_creates == 0

    def test_bash_cat_redirect_counted(self):
        tc = _bash_call("tu-1", "cat > /tmp/file.py << EOF\ncode\nEOF")
        call = _api_call([tc])

        _, bash_creates = extract_write_edit_events([call], "sess-1")

        assert bash_creates == 1

    def test_bash_tee_counted(self):
        tc = _bash_call("tu-1", "echo 'content' | tee /src/output.txt")
        call = _api_call([tc])

        _, bash_creates = extract_write_edit_events([call], "sess-1")

        assert bash_creates == 1

    def test_bash_touch_counted(self):
        tc = _bash_call("tu-1", "touch /tmp/newfile.py")
        call = _api_call([tc])

        _, bash_creates = extract_write_edit_events([call], "sess-1")

        assert bash_creates == 1

    def test_bash_plain_command_not_counted(self):
        tc = _bash_call("tu-1", "ls -la /src")
        call = _api_call([tc])

        _, bash_creates = extract_write_edit_events([call], "sess-1")

        assert bash_creates == 0

    def test_session_id_propagated(self):
        tc = _tool_call("Write", "tu-1", file_path="/src/main.py")
        call = _api_call([tc])

        events, _ = extract_write_edit_events([call], "my-session")

        assert events[0].session_id == "my-session"


# ---------------------------------------------------------------------------
# TestComputeCounterfactual
# ---------------------------------------------------------------------------


class TestComputeCounterfactual:
    def _post_deny_call(self, session_id: str = "sess-1") -> IndexCall:
        return IndexCall(
            session_id=session_id,
            tool_name="mcp__jcodemunch__index_folder",
            trigger="post_deny",
            chain_cost_tokens=400,
        )

    def _post_toolsearch_call(self, session_id: str = "sess-1") -> IndexCall:
        return IndexCall(
            session_id=session_id,
            tool_name="mcp__jcodemunch__index_folder",
            trigger="post_toolsearch",
            chain_cost_tokens=300,
        )

    def _write_event(self, session_id: str = "sess-1") -> WriteEditEvent:
        return WriteEditEvent(
            session_id=session_id,
            tool_name="Write",
            file_path="/src/app.py",
            file_ext=".py",
        )

    def test_direct_savings_formula(self):
        chains = [self._post_deny_call() for _ in range(10)]
        result = compute_counterfactual(chains, [], 0, session_count=1)
        assert result.post_deny_tokens_saved == 10 * R5_MEAN_CHAIN_COST

    def test_indirect_savings_low(self):
        chains = [self._post_toolsearch_call() for _ in range(100)]
        result = compute_counterfactual(chains, [], 0, session_count=1)
        expected = int(100 * 0.25 * R3_MEAN_DETOUR_COST)
        assert result.indirect_savings_low == expected

    def test_indirect_savings_mid(self):
        chains = [self._post_toolsearch_call() for _ in range(100)]
        result = compute_counterfactual(chains, [], 0, session_count=1)
        expected = int(100 * 0.50 * R3_MEAN_DETOUR_COST)
        assert result.indirect_savings_mid == expected

    def test_indirect_savings_high(self):
        chains = [self._post_toolsearch_call() for _ in range(100)]
        result = compute_counterfactual(chains, [], 0, session_count=1)
        expected = int(100 * 0.75 * R3_MEAN_DETOUR_COST)
        assert result.indirect_savings_high == expected

    def test_indirect_low_lt_mid_lt_high(self):
        chains = [self._post_toolsearch_call() for _ in range(10)]
        result = compute_counterfactual(chains, [], 0, session_count=1)
        assert result.indirect_savings_low < result.indirect_savings_mid
        assert result.indirect_savings_mid < result.indirect_savings_high

    def test_zero_denies(self):
        result = compute_counterfactual([], [], 0, session_count=5)
        assert result.post_deny_index_chains == 0
        assert result.post_deny_tokens_saved == 0

    def test_coverage_gap_pct(self):
        writes = [self._write_event() for _ in range(8)]
        bash_creates = 2
        result = compute_counterfactual([], writes, bash_creates, session_count=1)
        assert abs(result.coverage_gap_pct - 0.2) < 0.001

    def test_coverage_gap_zero_when_no_bash_creates(self):
        writes = [self._write_event() for _ in range(5)]
        result = compute_counterfactual([], writes, 0, session_count=1)
        assert result.coverage_gap_pct == 0.0

    def test_coverage_gap_zero_when_no_mutations(self):
        result = compute_counterfactual([], [], 0, session_count=1)
        assert result.coverage_gap_pct == 0.0

    def test_writes_per_session(self):
        writes = [self._write_event() for _ in range(15)]
        result = compute_counterfactual([], writes, 0, session_count=5)
        assert result.writes_per_session == 3.0

    def test_writes_per_session_zero_sessions(self):
        result = compute_counterfactual([], [], 0, session_count=0)
        assert result.writes_per_session == 0.0

    def test_counts_mixed_index_calls(self):
        chains = [self._post_deny_call(), self._post_toolsearch_call(), self._post_deny_call()]
        result = compute_counterfactual(chains, [], 0, session_count=1)
        assert result.post_deny_index_chains == 2
        assert result.post_toolsearch_index_chains == 1


# ---------------------------------------------------------------------------
# TestR6Integration
# ---------------------------------------------------------------------------


class TestR6Integration:
    """End-to-end test: Write → Read(deny) → index_folder → Read(success)."""

    def test_full_pipeline_post_deny_chain(self):
        # Write event
        write_tc = _tool_call("Write", "tu-0", file_path="/src/app.py")
        write_call = _api_call(
            [write_tc], tool_results=[ToolResult("tu-0", 200)], output_tokens=80, request_id="req-0"
        )

        # Read (denied)
        read_tc = _tool_call("Read", "tu-1", file_path="/src/app.py")
        read_call = _api_call(
            [read_tc], tool_results=[_deny_result("tu-1")], output_tokens=180, request_id="req-1"
        )

        # index_folder (triggered by deny)
        index_tc = _tool_call("mcp__jcodemunch__index_folder", "tu-2")
        index_call = _api_call(
            [index_tc], tool_results=[ToolResult("tu-2", 100)],
            output_tokens=120, request_id="req-2",
        )

        # Read (success on retry)
        read2_tc = _tool_call("Read", "tu-3", file_path="/src/app.py")
        read2_call = _api_call(
            [read2_tc], tool_results=[ToolResult("tu-3", 2000)],
            output_tokens=160, request_id="req-3",
        )

        api_calls = [write_call, read_call, index_call, read2_call]
        error_map = {
            "tu-0": (False, "ok"),
            "tu-1": (True, "BLOCKED: use jCodeMunch"),
            "tu-2": (False, '{"success": true}'),
            "tu-3": (False, "file contents"),
        }

        write_events, bash_creates = extract_write_edit_events(api_calls, "sess-1")
        index_calls_found = extract_index_calls(api_calls, error_map, "sess-1")

        result = compute_counterfactual(
            index_calls_found,
            write_events,
            bash_creates,
            session_count=1,
        )

        # One Write event
        assert result.write_edit_count == 1
        # One post_deny index chain
        assert result.post_deny_index_chains == 1
        assert result.post_deny_tokens_saved == R5_MEAN_CHAIN_COST
        # Chain cost = deny(180) + index(120) = 300
        assert index_calls_found[0].chain_cost_tokens == 300
        # No bash creates → no coverage gap
        assert result.coverage_gap_pct == 0.0
