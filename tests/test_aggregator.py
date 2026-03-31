"""Tests for scripts/analyze/aggregator.py — token cost accumulation."""
import pytest

from scripts.analyze.aggregator import (
    GlobalStats,
    SessionStats,
    aggregate_session,
    compute_per_extension_costs,
    merge_sessions,
)
from scripts.analyze.parser import ApiCall, TokenUsage, ToolCall

# ---------------------------------------------------------------------------
# Factories
# ---------------------------------------------------------------------------


def _tool_call(name: str, tool_use_id: str = "tu-1", file_ext: str | None = ".py") -> ToolCall:
    fp = f"/src/app{file_ext}" if file_ext else "/src/Makefile"
    return ToolCall(
        name=name,
        tool_use_id=tool_use_id,
        input={"file_path": fp},
        file_path=fp,
        file_ext=file_ext,
    )


def _api_call(
    tool_calls: list[ToolCall],
    input_tokens: int = 100,
    output_tokens: int = 50,
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
        usage=TokenUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_creation_input_tokens=0,
            cache_read_input_tokens=0,
        ),
    )


# ---------------------------------------------------------------------------
# TestAggregateSession
# ---------------------------------------------------------------------------


class TestAggregateSession:
    def test_basic_token_accumulation(self):
        calls = [
            _api_call([_tool_call("Read")], input_tokens=100, output_tokens=50),
            _api_call(
                [_tool_call("Edit", "tu-2")],
                input_tokens=200,
                output_tokens=80,
                request_id="req-2",
            ),
        ]
        stats = aggregate_session(calls, session_id="sess-1")
        assert stats.total_input_tokens == 300
        assert stats.total_output_tokens == 130

    def test_single_tool_exact_attribution(self):
        calls = [_api_call([_tool_call("Read")], output_tokens=60)]
        stats = aggregate_session(calls, session_id="sess-1")
        costs = stats.tool_token_costs["Read"]
        assert costs["samples"] == [{"output_tokens": 60, "approximate": False}]

    def test_multi_tool_even_split_tagged_approximate(self):
        tc1 = _tool_call("Read", "tu-1", ".py")
        tc2 = _tool_call("Edit", "tu-2", ".py")
        call = _api_call([tc1, tc2], output_tokens=80)
        stats = aggregate_session([call], session_id="sess-1")
        read_samples = stats.tool_token_costs["Read"]["samples"]
        edit_samples = stats.tool_token_costs["Edit"]["samples"]
        assert read_samples[0]["output_tokens"] == 40
        assert read_samples[0]["approximate"] is True
        assert edit_samples[0]["output_tokens"] == 40
        assert edit_samples[0]["approximate"] is True

    def test_tool_call_counts(self):
        calls = [
            _api_call([_tool_call("Read")]),
            _api_call([_tool_call("Read", "tu-2")], request_id="req-2"),
            _api_call([_tool_call("Edit", "tu-3")], request_id="req-3"),
        ]
        stats = aggregate_session(calls, session_id="sess-1")
        assert stats.tool_call_counts["Read"] == 2
        assert stats.tool_call_counts["Edit"] == 1

    def test_extension_token_costs(self):
        calls = [_api_call([_tool_call("Read", file_ext=".py")], output_tokens=60)]
        stats = aggregate_session(calls, session_id="sess-1")
        assert ".py" in stats.ext_token_costs
        assert stats.ext_token_costs[".py"]["samples"][0]["output_tokens"] == 60

    def test_permission_modes_collected(self):
        calls = [
            _api_call([_tool_call("Read")], permission_mode="default"),
            _api_call(
                [_tool_call("Edit", "tu-2")],
                permission_mode="bypassPermissions",
                request_id="req-2",
            ),
        ]
        stats = aggregate_session(calls, session_id="sess-1")
        assert stats.permission_modes == {"default", "bypassPermissions"}

    def test_tool_sequence_preserved(self):
        tc1 = _tool_call("Read", "tu-1")
        tc2 = _tool_call("Edit", "tu-2")
        calls = [
            _api_call([tc1]),
            _api_call([tc2], request_id="req-2"),
        ]
        stats = aggregate_session(calls, session_id="sess-1")
        assert [t.name for t in stats.tool_sequence] == ["Read", "Edit"]

    def test_empty_api_calls(self):
        stats = aggregate_session([], session_id="sess-1")
        assert stats.total_input_tokens == 0
        assert stats.total_output_tokens == 0
        assert stats.tool_call_counts == {}

    def test_session_metadata(self):
        stats = aggregate_session(
            [], session_id="sess-1", is_subagent=True, agent_type="python-reviewer"
        )
        assert stats.session_id == "sess-1"
        assert stats.is_subagent is True
        assert stats.agent_type == "python-reviewer"

    def test_no_file_ext_tool_call_not_in_ext_costs(self):
        tc = ToolCall(
            name="Bash", tool_use_id="tu-1", input={"command": "ls"},
            file_path=None, file_ext=None,
        )
        calls = [_api_call([tc], output_tokens=30)]
        stats = aggregate_session(calls, session_id="sess-1")
        assert stats.ext_token_costs == {}


# ---------------------------------------------------------------------------
# TestMergeSessions
# ---------------------------------------------------------------------------


class TestMergeSessions:
    def _make_session(
        self,
        session_id: str,
        input_tokens: int,
        output_tokens: int,
        tool_counts: dict[str, int] | None = None,
    ) -> SessionStats:
        # Simplify: just build directly
        return aggregate_session(
            [_api_call(
                [_tool_call("Read")],
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )],
            session_id=session_id,
        )

    def test_merge_sums_tokens(self):
        s1 = aggregate_session(
            [_api_call([_tool_call("Read")], input_tokens=100, output_tokens=50)],
            session_id="s1",
        )
        s2 = aggregate_session(
            [_api_call([_tool_call("Edit", "tu-2")], input_tokens=200, output_tokens=80)],
            session_id="s2",
        )
        g = merge_sessions([s1, s2])
        assert g.total_input_tokens == 300
        assert g.total_output_tokens == 130

    def test_merge_session_count(self):
        s1 = aggregate_session([], session_id="s1")
        s2 = aggregate_session([], session_id="s2")
        g = merge_sessions([s1, s2])
        assert g.session_count == 2

    def test_merge_tool_call_counts(self):
        s1 = aggregate_session(
            [
                _api_call([_tool_call("Read")]),
                _api_call([_tool_call("Read", "tu-2")], request_id="req-2"),
            ],
            session_id="s1",
        )
        s2 = aggregate_session(
            [_api_call([_tool_call("Read", "tu-3")], request_id="req-3")],
            session_id="s2",
        )
        g = merge_sessions([s1, s2])
        assert g.tool_call_counts["Read"] == 3

    def test_merge_empty_list(self):
        g = merge_sessions([])
        assert g.total_input_tokens == 0
        assert g.session_count == 0


# ---------------------------------------------------------------------------
# TestComputePerExtensionCosts
# ---------------------------------------------------------------------------


class TestComputePerExtensionCosts:
    def _global_with_ext_samples(self, ext: str, output_tokens: list[int]) -> GlobalStats:
        """Build a GlobalStats with known per-extension samples."""
        sessions = []
        for i, ot in enumerate(output_tokens):
            sessions.append(
                aggregate_session(
                    [_api_call(
                        [_tool_call("Read", f"tu-{i}", ext)],
                        output_tokens=ot,
                        request_id=f"req-{i}",
                    )],
                    session_id=f"sess-{i}",
                )
            )
        return merge_sessions(sessions)

    def test_computes_mean(self):
        g = self._global_with_ext_samples(".py", [100, 200, 300])
        result = compute_per_extension_costs(g)
        assert result[".py"]["mean"] == pytest.approx(200.0)

    def test_computes_median(self):
        g = self._global_with_ext_samples(".py", [100, 200, 300])
        result = compute_per_extension_costs(g)
        assert result[".py"]["median"] == pytest.approx(200.0)

    def test_computes_p95(self):
        g = self._global_with_ext_samples(".py", list(range(1, 21)))  # 1..20
        result = compute_per_extension_costs(g)
        # p95 of 20 values should be close to 19
        assert result[".py"]["p95"] >= 18.0

    def test_computes_total_and_count(self):
        g = self._global_with_ext_samples(".py", [100, 200, 300])
        result = compute_per_extension_costs(g)
        assert result[".py"]["total"] == 600
        assert result[".py"]["count"] == 3

    def test_excludes_approximate_from_median(self):
        # Approximate samples (multi-tool splits) should be excluded from median
        tc1 = _tool_call("Read", "tu-1", ".py")
        tc2 = _tool_call("Edit", "tu-2", ".py")
        # Multi-tool call: both tagged approximate
        call = _api_call([tc1, tc2], output_tokens=200)
        exact_call = _api_call(
            [_tool_call("Read", "tu-3", ".py")], output_tokens=100, request_id="req-2"
        )
        session = aggregate_session([call, exact_call], session_id="sess-1")
        g = merge_sessions([session])
        result = compute_per_extension_costs(g)
        # Median should be from exact samples only: [100]
        assert result[".py"]["median"] == pytest.approx(100.0)
