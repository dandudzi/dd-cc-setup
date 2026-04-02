"""Tests for scripts/observatory/reports/f1_turn_cost.py.

TDD: written before implementation (RED phase).
Finding 1: Turn Cost Asymmetry (Read vs MCP).
Key invariant: token usage belongs to the API turn, not individual tool calls.
Only single-tool turns can be cleanly attributed.
"""
from __future__ import annotations

from scripts.observatory.data.parser import ApiCall, TokenUsage, ToolCall, ToolResult


# ---------------------------------------------------------------------------
# Factories (same pattern as test_posttooluse.py)
# ---------------------------------------------------------------------------


def _tc(name: str, tool_use_id: str = "tu-1", file_path: str | None = None) -> ToolCall:
    inp: dict = {}  # type: ignore[type-arg]
    if name == "Read":
        inp = {"file_path": file_path or "/src/app.py"}
    return ToolCall(name=name, tool_use_id=tool_use_id, input=inp,
                    file_path=file_path, file_ext=None)


def _result(tool_use_id: str, content_length: int | None = 500) -> ToolResult:
    return ToolResult(tool_use_id=tool_use_id, content_length=content_length)


def _call(
    tool_calls: list[ToolCall],
    input_tokens: int = 100,
    output_tokens: int = 150,
    cache_read: int = 0,
    tool_results: list[ToolResult] | None = None,
    session_id: str = "sess-1",
    request_id: str = "req-1",
) -> ApiCall:
    return ApiCall(
        request_id=request_id,
        session_id=session_id,
        agent_id=None,
        permission_mode="default",
        stop_reason="tool_use",
        tool_calls=tuple(tool_calls),
        tool_results=tuple(tool_results or []),
        usage=TokenUsage(input_tokens, output_tokens, 0, cache_read),
    )


# ---------------------------------------------------------------------------
# classify_tool
# ---------------------------------------------------------------------------


class TestClassifyTool:
    def test_read(self) -> None:
        from scripts.observatory.reports.f1_turn_cost import classify_tool
        assert classify_tool("Read") == "Read"

    def test_jcodemunch_get_file_content(self) -> None:
        from scripts.observatory.reports.f1_turn_cost import classify_tool
        assert classify_tool("mcp__jcodemunch__get_file_content") == "jCodeMunch"

    def test_jcodemunch_get_symbol_source(self) -> None:
        from scripts.observatory.reports.f1_turn_cost import classify_tool
        assert classify_tool("mcp__jcodemunch__get_symbol_source") == "jCodeMunch"

    def test_jcodemunch_search_symbols(self) -> None:
        from scripts.observatory.reports.f1_turn_cost import classify_tool
        assert classify_tool("mcp__jcodemunch__search_symbols") == "jCodeMunch"

    def test_jdocmunch_get_section(self) -> None:
        from scripts.observatory.reports.f1_turn_cost import classify_tool
        assert classify_tool("mcp__jdocmunch__get_section") == "jDocMunch"

    def test_jdocmunch_search_sections(self) -> None:
        from scripts.observatory.reports.f1_turn_cost import classify_tool
        assert classify_tool("mcp__jdocmunch__search_sections") == "jDocMunch"

    def test_bash_returns_none(self) -> None:
        from scripts.observatory.reports.f1_turn_cost import classify_tool
        assert classify_tool("Bash") is None

    def test_agent_returns_none(self) -> None:
        from scripts.observatory.reports.f1_turn_cost import classify_tool
        assert classify_tool("Agent") is None

    def test_index_folder_returns_none(self) -> None:
        # Index operations are NOT retrieval — excluded from F1 comparison
        from scripts.observatory.reports.f1_turn_cost import classify_tool
        assert classify_tool("mcp__jcodemunch__index_folder") is None

    def test_index_local_returns_none(self) -> None:
        from scripts.observatory.reports.f1_turn_cost import classify_tool
        assert classify_tool("mcp__jdocmunch__index_local") is None

    def test_unknown_mcp_tool_returns_none(self) -> None:
        from scripts.observatory.reports.f1_turn_cost import classify_tool
        assert classify_tool("mcp__someother__do_thing") is None


# ---------------------------------------------------------------------------
# compute_f1
# ---------------------------------------------------------------------------


class TestComputeF1:
    def test_empty_returns_zero_totals(self) -> None:
        from scripts.observatory.reports.f1_turn_cost import compute_turn_cost
        result = compute_turn_cost([])
        assert result["total_turns"] == 0
        assert result["single_tool_turns"] == 0
        assert result["single_tool_fraction"] == 0.0

    def test_empty_stats_all_zero_n(self) -> None:
        from scripts.observatory.reports.f1_turn_cost import compute_turn_cost
        result = compute_turn_cost([])
        for s in result["stats"]:
            assert s.n == 0

    def test_multi_tool_turns_excluded(self) -> None:
        from scripts.observatory.reports.f1_turn_cost import compute_turn_cost
        # Turn with 2 tool calls — must not count
        call = _call([_tc("Read", "tu-1"), _tc("Bash", "tu-2")])
        result = compute_turn_cost([call])
        assert result["single_tool_turns"] == 0
        read_stats = next(s for s in result["stats"] if s.category == "Read")
        assert read_stats.n == 0

    def test_single_read_turn_counted(self) -> None:
        from scripts.observatory.reports.f1_turn_cost import compute_turn_cost
        call = _call([_tc("Read")], input_tokens=238, output_tokens=160)
        result = compute_turn_cost([call])
        read_stats = next(s for s in result["stats"] if s.category == "Read")
        assert read_stats.n == 1
        assert read_stats.mean_input_tokens == 238.0

    def test_single_jcodemunch_turn_counted(self) -> None:
        from scripts.observatory.reports.f1_turn_cost import compute_turn_cost
        call = _call([_tc("mcp__jcodemunch__get_file_content")], input_tokens=3, output_tokens=160)
        result = compute_turn_cost([call])
        jcm_stats = next(s for s in result["stats"] if s.category == "jCodeMunch")
        assert jcm_stats.n == 1
        assert jcm_stats.mean_input_tokens == 3.0

    def test_single_jdocmunch_turn_counted(self) -> None:
        from scripts.observatory.reports.f1_turn_cost import compute_turn_cost
        call = _call([_tc("mcp__jdocmunch__search_sections")], input_tokens=5, output_tokens=160)
        result = compute_turn_cost([call])
        jdm_stats = next(s for s in result["stats"] if s.category == "jDocMunch")
        assert jdm_stats.n == 1
        assert jdm_stats.mean_input_tokens == 5.0

    def test_mean_input_tokens_computed_correctly(self) -> None:
        from scripts.observatory.reports.f1_turn_cost import compute_turn_cost
        c1 = _call([_tc("Read", "tu-1")], input_tokens=200, request_id="r1")
        c2 = _call([_tc("Read", "tu-2")], input_tokens=300, request_id="r2")
        result = compute_turn_cost([c1, c2])
        read_stats = next(s for s in result["stats"] if s.category == "Read")
        assert read_stats.n == 2
        assert read_stats.mean_input_tokens == 250.0

    def test_content_length_from_tool_result(self) -> None:
        from scripts.observatory.reports.f1_turn_cost import compute_turn_cost
        call = _call(
            [_tc("Read", "tu-1")],
            tool_results=[_result("tu-1", content_length=3874)],
        )
        result = compute_turn_cost([call])
        read_stats = next(s for s in result["stats"] if s.category == "Read")
        assert read_stats.mean_content_length == 3874.0

    def test_content_length_none_when_no_results(self) -> None:
        from scripts.observatory.reports.f1_turn_cost import compute_turn_cost
        call = _call([_tc("Read")], tool_results=[])
        result = compute_turn_cost([call])
        read_stats = next(s for s in result["stats"] if s.category == "Read")
        assert read_stats.mean_content_length is None

    def test_single_tool_fraction(self) -> None:
        from scripts.observatory.reports.f1_turn_cost import compute_turn_cost
        single = _call([_tc("Read", "tu-1")], request_id="r1")
        multi = _call([_tc("Read", "tu-2"), _tc("Bash", "tu-3")], request_id="r2")
        result = compute_turn_cost([single, multi])
        assert result["total_turns"] == 2
        assert result["single_tool_turns"] == 1
        assert result["single_tool_fraction"] == 0.5

    def test_result_has_three_categories(self) -> None:
        from scripts.observatory.reports.f1_turn_cost import compute_turn_cost
        result = compute_turn_cost([])
        categories = {s.category for s in result["stats"]}
        assert categories == {"Read", "jCodeMunch", "jDocMunch"}

    def test_bash_single_turn_not_in_any_category(self) -> None:
        from scripts.observatory.reports.f1_turn_cost import compute_turn_cost
        # Bash turn is single-tool but unclassified — counted in single_tool_turns
        # but not added to any bucket
        call = _call([_tc("Bash")], input_tokens=50)
        result = compute_turn_cost([call])
        assert result["single_tool_turns"] == 1
        for s in result["stats"]:
            assert s.n == 0
