"""Tests for scripts/analyze/classifiers.py — session mode, waste, decision tree."""
import pytest

from scripts.analyze.aggregator import SessionStats, aggregate_session
from scripts.analyze.classifiers import (
    TIER1_CODE_EXTENSIONS,
    TIER2_CODE_EXTENSIONS,
    TIER3_CODE_EXTENSIONS,
    analyze_sequences,
    classify_session_mode,
    compute_waste,
    validate_decision_tree,
)
from scripts.analyze.parser import ApiCall, TokenUsage, ToolCall, ToolResult

# ---------------------------------------------------------------------------
# Factories
# ---------------------------------------------------------------------------


def _tool_call(name: str, tool_use_id: str = "tu-1", file_ext: str | None = ".py") -> ToolCall:
    fp = f"/src/app{file_ext}" if file_ext else None
    return ToolCall(
        name=name,
        tool_use_id=tool_use_id,
        input={"file_path": fp} if fp else {"command": "ls"},
        file_path=fp,
        file_ext=file_ext,
    )


def _api_call(
    tool_calls: list[ToolCall],
    permission_mode: str = "default",
    request_id: str = "req-1",
) -> ApiCall:
    return ApiCall(
        request_id=request_id,
        session_id="sess-1",
        agent_id=None,
        permission_mode=permission_mode,
        stop_reason="end_turn",
        tool_calls=tuple(tool_calls),
        tool_results=(),
        usage=TokenUsage(100, 50, 0, 0),
    )


def _session_with_tools(tool_names: list[str], session_id: str = "sess-1") -> SessionStats:
    """Build a SessionStats from a list of tool names."""
    calls = [
        _api_call([_tool_call(name, f"tu-{i}")], request_id=f"req-{i}")
        for i, name in enumerate(tool_names)
    ]
    return aggregate_session(calls, session_id=session_id)


# ---------------------------------------------------------------------------
# TestTieredExtensions
# ---------------------------------------------------------------------------


class TestTieredExtensions:
    def test_tier1_contains_python(self):
        assert ".py" in TIER1_CODE_EXTENSIONS

    def test_tier1_contains_typescript(self):
        assert ".ts" in TIER1_CODE_EXTENSIONS

    def test_tier2_and_tier3_non_overlapping(self):
        assert TIER1_CODE_EXTENSIONS.isdisjoint(TIER2_CODE_EXTENSIONS)
        assert TIER1_CODE_EXTENSIONS.isdisjoint(TIER3_CODE_EXTENSIONS)
        assert TIER2_CODE_EXTENSIONS.isdisjoint(TIER3_CODE_EXTENSIONS)

    def test_tier1_at_least_40_extensions(self):
        assert len(TIER1_CODE_EXTENSIONS) >= 40

    def test_tier2_has_extensions(self):
        assert len(TIER2_CODE_EXTENSIONS) >= 1

    def test_tier3_has_extensions(self):
        assert len(TIER3_CODE_EXTENSIONS) >= 1


# ---------------------------------------------------------------------------
# TestClassifySessionMode
# ---------------------------------------------------------------------------


class TestClassifySessionMode:
    @pytest.mark.parametrize(
        "tool_names,expected_mode",
        [
            # Editing: Edit+Write > 30%
            (["Read", "Edit", "Write", "Edit"], "editing"),
            (["Edit", "Write", "Edit", "Write", "Read"], "editing"),
            # Exploration: Read+Grep+Glob+Bash > 70%
            (["Read", "Grep", "Glob", "Bash"] * 2 + ["Edit"], "exploration"),
            (["Read"] * 8 + ["Edit"], "exploration"),
            # Mixed: neither threshold met (editing ≤30%, exploration ≤70%)
            (["Read", "Bash", "Mcp", "Mcp"], "mixed"),
            (["Read", "Edit", "Mcp", "Mcp", "Mcp"], "mixed"),
        ],
    )
    def test_classify_mode(self, tool_names: list[str], expected_mode: str):
        stats = _session_with_tools(tool_names)
        assert classify_session_mode(stats) == expected_mode

    def test_empty_session_is_mixed(self):
        stats = _session_with_tools([])
        assert classify_session_mode(stats) == "mixed"


# ---------------------------------------------------------------------------
# TestComputeWaste
# ---------------------------------------------------------------------------


class TestComputeWaste:
    def _make_tool_results_map(
        self, mappings: dict[str, int | None]
    ) -> dict[str, ToolResult]:
        return {
            tid: ToolResult(tool_use_id=tid, content_length=length)
            for tid, length in mappings.items()
        }

    def test_redirectable_read_no_preceding_edit(self):
        tc = ToolCall(
            name="Read",
            tool_use_id="tu-1",
            input={"file_path": "/src/app.py"},
            file_path="/src/app.py",
            file_ext=".py",
        )
        api_call = _api_call([tc])
        results_map = self._make_tool_results_map({"tu-1": 5000})
        report = compute_waste([api_call], results_map, [tc])
        assert report.total_reads == 1
        assert report.redirectable_reads == 1
        assert report.waste_fraction == pytest.approx(1.0)

    def test_non_redirectable_read_preceded_by_edit(self):
        edit_tc = _tool_call("Edit", "tu-0")
        read_tc = ToolCall(
            name="Read",
            tool_use_id="tu-1",
            input={"file_path": "/src/app.py"},
            file_path="/src/app.py",
            file_ext=".py",
        )
        api_calls = [_api_call([edit_tc]), _api_call([read_tc], request_id="req-2")]
        results_map = self._make_tool_results_map({"tu-1": 5000})
        report = compute_waste(api_calls, results_map, [edit_tc, read_tc])
        assert report.total_reads == 1
        assert report.redirectable_reads == 0
        assert report.waste_fraction == pytest.approx(0.0)

    def test_non_redirectable_read_with_offset(self):
        tc = ToolCall(
            name="Read",
            tool_use_id="tu-1",
            input={"file_path": "/src/app.py", "offset": 10},
            file_path="/src/app.py",
            file_ext=".py",
        )
        api_call = _api_call([tc])
        results_map = self._make_tool_results_map({"tu-1": 5000})
        report = compute_waste([api_call], results_map, [tc])
        assert report.redirectable_reads == 0

    def test_non_redirectable_read_with_limit(self):
        tc = ToolCall(
            name="Read",
            tool_use_id="tu-1",
            input={"file_path": "/src/app.py", "limit": 50},
            file_path="/src/app.py",
            file_ext=".py",
        )
        api_call = _api_call([tc])
        results_map = self._make_tool_results_map({"tu-1": 200})
        report = compute_waste([api_call], results_map, [tc])
        assert report.redirectable_reads == 0

    def test_waste_fraction_partial(self):
        # 2 reads: 1 redirectable, 1 not (preceded by Edit)
        edit_tc = _tool_call("Edit", "tu-0")
        read1 = ToolCall("Read", "tu-1", {"file_path": "/a.py"}, "/a.py", ".py")
        read2 = ToolCall("Read", "tu-2", {"file_path": "/b.py"}, "/b.py", ".py")
        api_calls = [
            _api_call([edit_tc]),
            _api_call([read1], request_id="req-2"),
            _api_call([read2], request_id="req-3"),
        ]
        results_map = self._make_tool_results_map({"tu-1": 1000, "tu-2": 1000})
        seq = [edit_tc, read1, read2]
        report = compute_waste(api_calls, results_map, seq)
        assert report.total_reads == 2
        assert report.redirectable_reads == 1
        assert report.waste_fraction == pytest.approx(0.5)

    def test_by_extension_populated(self):
        tc = ToolCall("Read", "tu-1", {"file_path": "/src/app.py"}, "/src/app.py", ".py")
        api_call = _api_call([tc])
        results_map = self._make_tool_results_map({"tu-1": 5000})
        report = compute_waste([api_call], results_map, [tc])
        assert ".py" in report.by_extension
        assert report.by_extension[".py"]["redirectable"] == 1

    def test_by_tier_populated(self):
        # .py is Tier 1
        tc = ToolCall("Read", "tu-1", {"file_path": "/src/app.py"}, "/src/app.py", ".py")
        api_call = _api_call([tc])
        results_map = self._make_tool_results_map({"tu-1": 5000})
        report = compute_waste([api_call], results_map, [tc])
        assert "tier1" in report.by_tier
        assert report.by_tier["tier1"]["total"] >= 1

    def test_empty_returns_zero_waste(self):
        report = compute_waste([], {}, [])
        assert report.total_reads == 0
        assert report.waste_fraction == 0.0


# ---------------------------------------------------------------------------
# TestValidateDecisionTree
# ---------------------------------------------------------------------------


class TestValidateDecisionTree:
    def test_returns_dict_with_five_keys(self):
        result = validate_decision_tree([], [])
        assert "file_size_threshold" in result
        assert "bash_unbounded_patterns" in result
        assert "tier_2_3_extensions" in result
        assert "config_files" in result
        assert "context_mode_vs_jcodemunch" in result

    def test_file_size_distribution_populated(self):
        tc = ToolCall("Read", "tu-1", {"file_path": "/src/app.py"}, "/src/app.py", ".py")
        tr = ToolResult(tool_use_id="tu-1", content_length=8000)
        api_call = ApiCall(
            request_id="req-1",
            session_id="sess-1",
            agent_id=None,
            permission_mode="default",
            stop_reason="end_turn",
            tool_calls=(tc,),
            tool_results=(tr,),
            usage=TokenUsage(100, 50, 0, 0),
        )
        result = validate_decision_tree([api_call], [tc])
        assert result["file_size_threshold"]["count"] >= 1

    def test_bash_unbounded_detection(self):
        # 'grep' is in _UNBOUNDED_SINGLE_WORD
        bash_tc = ToolCall("Bash", "tu-1", {"command": "grep -r foo ."}, None, None)
        api_call = _api_call([bash_tc])
        result = validate_decision_tree([api_call], [bash_tc])
        assert result["bash_unbounded_patterns"]["unbounded_count"] >= 1

    def test_config_files_counted(self):
        tc = ToolCall("Read", "tu-1", {"file_path": "/config.json"}, "/config.json", ".json")
        api_call = _api_call([tc])
        result = validate_decision_tree([api_call], [tc])
        assert result["config_files"]["total_reads"] >= 1

    def test_context_mode_jcodemunch_cooccurrence(self):
        cm_tc = ToolCall(
            "mcp__plugin_context-mode_context-mode__ctx_execute", "tu-1",
            {}, None, None,
        )
        jcm_tc = ToolCall(
            "mcp__jcodemunch__search_symbols", "tu-2",
            {}, None, None,
        )
        api1 = _api_call([cm_tc])
        api2 = _api_call([jcm_tc], request_id="req-2")
        result = validate_decision_tree([api1, api2], [cm_tc, jcm_tc])
        assert result["context_mode_vs_jcodemunch"]["sessions_with_both"] >= 0


# ---------------------------------------------------------------------------
# TestAnalyzeSequences
# ---------------------------------------------------------------------------


class TestAnalyzeSequences:
    def test_read_edit_pair_frequency(self):
        tc1 = _tool_call("Read", "tu-1")
        tc2 = _tool_call("Edit", "tu-2")
        result = analyze_sequences([tc1, tc2])
        assert result["read_edit_pairs"] >= 1

    def test_top_bigrams(self):
        seq = [
            _tool_call("Read", "tu-1"),
            _tool_call("Edit", "tu-2"),
            _tool_call("Read", "tu-3"),
            _tool_call("Edit", "tu-4"),
        ]
        result = analyze_sequences(seq)
        bigrams = result["top_bigrams"]
        assert len(bigrams) >= 1
        assert bigrams[0][0] == ("Read", "Edit")

    def test_empty_sequence(self):
        result = analyze_sequences([])
        assert result["read_edit_pairs"] == 0
        assert result["top_bigrams"] == []
