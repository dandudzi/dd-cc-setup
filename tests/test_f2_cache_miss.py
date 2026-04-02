"""Tests for scripts/observatory/reports/f2_cache_miss/compute.py."""
from __future__ import annotations

import pytest

from scripts.observatory.data.parser import ApiCall, ToolCall, ToolResult, TokenUsage, _extract_usage
from scripts.observatory.reports.f2_cache_miss.compute import CacheMissStats, compute_cache_miss, table_height


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _usage(
    input_tokens: int = 1000,
    cache_creation: int = 0,
    cache_read: int = 0,
    cache_5m: int = 0,
    cache_1h: int = 0,
) -> TokenUsage:
    return TokenUsage(
        input_tokens=input_tokens,
        output_tokens=100,
        cache_creation_input_tokens=cache_creation,
        cache_read_input_tokens=cache_read,
        cache_creation_5m_tokens=cache_5m,
        cache_creation_1h_tokens=cache_1h,
    )


def _call(
    tool_name: str,
    cache_creation: int = 0,
    cache_read: int = 0,
    cache_5m: int = 0,
    cache_1h: int = 0,
    input_tokens: int = 1000,
    tool_use_id: str = "tu1",
) -> ApiCall:
    tc = ToolCall(
        name=tool_name,
        tool_use_id=tool_use_id,
        input={},
        file_path=None,
        file_ext=None,
    )
    return ApiCall(
        request_id="r1",
        session_id="s1",
        agent_id=None,
        permission_mode=None,
        stop_reason="tool_use",
        tool_calls=(tc,),
        tool_results=(),
        usage=_usage(
            input_tokens=input_tokens,
            cache_creation=cache_creation,
            cache_read=cache_read,
            cache_5m=cache_5m,
            cache_1h=cache_1h,
        ),
    )


def _multi_tool_call() -> ApiCall:
    """A turn with two tool calls — should be excluded."""
    tc1 = ToolCall(name="Read", tool_use_id="tu1", input={}, file_path=None, file_ext=None)
    tc2 = ToolCall(name="Glob", tool_use_id="tu2", input={}, file_path=None, file_ext=None)
    return ApiCall(
        request_id="r2",
        session_id="s1",
        agent_id=None,
        permission_mode=None,
        stop_reason="tool_use",
        tool_calls=(tc1, tc2),
        tool_results=(),
        usage=_usage(cache_creation=500),
    )


# ---------------------------------------------------------------------------
# TestComputeCacheMiss
# ---------------------------------------------------------------------------

class TestComputeCacheMiss:
    def test_empty_calls(self):
        result = compute_cache_miss([])
        assert result["total_turns"] == 0
        assert result["single_tool_turns"] == 0
        assert result["overall_miss_rate"] == 0.0
        assert result["overall_miss_turns"] == 0
        assert result["overall_miss_tokens"] == 0
        # stats still has all default category entries, each with zero values
        for s in result["stats"]:
            assert s.total_turns == 0
            assert s.miss_turns == 0
            assert s.miss_rate == 0.0

    def test_no_miss_turns(self):
        calls = [_call("Read", cache_creation=0) for _ in range(5)]
        result = compute_cache_miss(calls)
        assert result["overall_miss_rate"] == 0.0
        assert result["overall_miss_turns"] == 0
        read_stat = next(s for s in result["stats"] if s.category == "Read")
        assert read_stat.miss_turns == 0
        assert read_stat.miss_rate == 0.0

    def test_single_miss_turn(self):
        calls = [_call("Read", cache_creation=2048)]
        result = compute_cache_miss(calls)
        assert result["overall_miss_turns"] == 1
        assert result["overall_miss_rate"] == pytest.approx(1.0)
        read_stat = next(s for s in result["stats"] if s.category == "Read")
        assert read_stat.miss_turns == 1
        assert read_stat.total_turns == 1
        assert read_stat.miss_rate == pytest.approx(1.0)
        assert read_stat.mean_miss_tokens == pytest.approx(2048.0)
        assert read_stat.total_miss_tokens == 2048

    def test_miss_rate_calculation(self):
        # 2 misses out of 10 turns = 0.2
        calls = [_call("Read", cache_creation=1000)] * 2 + [_call("Read", cache_creation=0)] * 8
        result = compute_cache_miss(calls)
        read_stat = next(s for s in result["stats"] if s.category == "Read")
        assert read_stat.miss_rate == pytest.approx(0.2)
        assert read_stat.total_turns == 10
        assert read_stat.miss_turns == 2

    def test_mean_miss_tokens(self):
        # Two miss turns: 1000 and 3000 tokens → mean = 2000
        calls = [
            _call("Read", cache_creation=1000),
            _call("Read", cache_creation=3000),
        ]
        result = compute_cache_miss(calls)
        read_stat = next(s for s in result["stats"] if s.category == "Read")
        assert read_stat.mean_miss_tokens == pytest.approx(2000.0)

    def test_total_miss_tokens(self):
        calls = [
            _call("Read", cache_creation=500),
            _call("Read", cache_creation=1500),
        ]
        result = compute_cache_miss(calls)
        read_stat = next(s for s in result["stats"] if s.category == "Read")
        assert read_stat.total_miss_tokens == 2000

    def test_multi_tool_turns_excluded(self):
        calls = [_call("Read"), _multi_tool_call()]
        result = compute_cache_miss(calls)
        assert result["total_turns"] == 2
        assert result["single_tool_turns"] == 1

    def test_multi_category(self):
        calls = [
            _call("Read", cache_creation=1000),
            _call("Read", cache_creation=0),
            _call("mcp__jcodemunch__get_file_content", cache_creation=500),
        ]
        result = compute_cache_miss(calls)
        stats = {s.category: s for s in result["stats"]}
        assert stats["Read"].total_turns == 2
        assert stats["Read"].miss_turns == 1
        assert stats["jCodeMunch"].total_turns == 1
        assert stats["jCodeMunch"].miss_turns == 1

    def test_overall_miss_rate(self):
        # 1 miss out of 3 categorized single-tool turns
        calls = [
            _call("Read", cache_creation=1000),
            _call("Read", cache_creation=0),
            _call("mcp__jcodemunch__get_file_content", cache_creation=0),
        ]
        result = compute_cache_miss(calls)
        assert result["overall_miss_turns"] == 1
        assert result["single_tool_turns"] == 3
        assert result["overall_miss_rate"] == pytest.approx(1 / 3)

    def test_overall_miss_tokens(self):
        calls = [
            _call("Read", cache_creation=600),
            _call("mcp__jcodemunch__get_file_content", cache_creation=400),
        ]
        result = compute_cache_miss(calls)
        assert result["overall_miss_tokens"] == 1000

    def test_category_filter(self):
        calls = [
            _call("Read", cache_creation=1000),
            _call("Bash", cache_creation=500),
        ]
        result = compute_cache_miss(calls, categories=["Read"])
        categories = [s.category for s in result["stats"]]
        assert categories == ["Read"]
        assert "Bash" not in categories

    def test_uncategorized_turns_excluded_from_stats(self):
        tc = ToolCall(name="UnknownTool", tool_use_id="tu1", input={}, file_path=None, file_ext=None)
        call = ApiCall(
            request_id="r1",
            session_id="s1",
            agent_id=None,
            permission_mode=None,
            stop_reason="tool_use",
            tool_calls=(tc,),
            tool_results=(),
            usage=_usage(cache_creation=999),
        )
        result = compute_cache_miss([call])
        # The turn is counted in single_tool_turns but not in any category's miss_turns
        assert result["single_tool_turns"] == 1
        for s in result["stats"]:
            assert s.miss_turns == 0

    def test_no_turns_in_category_has_zero_stats(self):
        # Bash has turns but Read has none → Read stats should be zeros
        calls = [_call("Bash", cache_creation=0)]
        result = compute_cache_miss(calls, categories=["Read", "Bash"])
        read_stat = next(s for s in result["stats"] if s.category == "Read")
        assert read_stat.total_turns == 0
        assert read_stat.miss_turns == 0
        assert read_stat.miss_rate == 0.0
        assert read_stat.mean_miss_tokens == 0.0
        assert read_stat.total_miss_tokens == 0

    def test_returns_stats_dataclass(self):
        result = compute_cache_miss([_call("Read")])
        assert all(isinstance(s, CacheMissStats) for s in result["stats"])


# ---------------------------------------------------------------------------
# 4-category model + TTL tests
# ---------------------------------------------------------------------------

class TestCacheMiss4Category:
    def test_cache_status_hit(self):
        """cache_read > 0 AND cache_creation == 0 → hit_turns=1."""
        calls = [_call("Read", cache_read=5000, cache_creation=0)]
        result = compute_cache_miss(calls)
        read_stat = next(s for s in result["stats"] if s.category == "Read")
        assert read_stat.hit_turns == 1
        assert read_stat.partial_turns == 0
        assert read_stat.miss_turns == 0
        assert read_stat.none_turns == 0

    def test_cache_status_partial(self):
        """cache_read > 0 AND cache_creation > 0 → partial_turns=1, NOT miss."""
        calls = [_call("Read", cache_read=5000, cache_creation=1000)]
        result = compute_cache_miss(calls)
        read_stat = next(s for s in result["stats"] if s.category == "Read")
        assert read_stat.partial_turns == 1
        assert read_stat.hit_turns == 0
        assert read_stat.miss_turns == 0
        assert read_stat.none_turns == 0

    def test_cache_status_none(self):
        """cache_read == 0 AND cache_creation == 0 → none_turns=1."""
        calls = [_call("Read", cache_read=0, cache_creation=0)]
        result = compute_cache_miss(calls)
        read_stat = next(s for s in result["stats"] if s.category == "Read")
        assert read_stat.none_turns == 1
        assert read_stat.hit_turns == 0
        assert read_stat.partial_turns == 0
        assert read_stat.miss_turns == 0

    def test_partial_not_counted_as_miss(self):
        """Partial hit must NOT inflate miss_turns or overall_miss_rate."""
        calls = [_call("Read", cache_read=500, cache_creation=100)]
        result = compute_cache_miss(calls)
        read_stat = next(s for s in result["stats"] if s.category == "Read")
        assert read_stat.miss_turns == 0
        assert read_stat.partial_turns == 1
        assert result["overall_miss_turns"] == 0
        assert result["overall_miss_rate"] == pytest.approx(0.0)

    def test_ttl_5m_tracked(self):
        """ttl_5m_tokens sums cache_creation_5m_tokens across all turns."""
        calls = [_call("Read", cache_creation=1000, cache_5m=1000)]
        result = compute_cache_miss(calls)
        read_stat = next(s for s in result["stats"] if s.category == "Read")
        assert read_stat.ttl_5m_tokens == 1000

    def test_ttl_1h_tracked(self):
        """ttl_1h_tokens sums cache_creation_1h_tokens across all turns."""
        calls = [_call("Read", cache_creation=600, cache_1h=500)]
        result = compute_cache_miss(calls)
        read_stat = next(s for s in result["stats"] if s.category == "Read")
        assert read_stat.ttl_1h_tokens == 500

    def test_overall_ttl_totals(self):
        """overall_ttl_5m_tokens / overall_ttl_1h_tokens aggregate across categories."""
        calls = [
            _call("Read", cache_5m=1000),
            _call("mcp__jcodemunch__get_file_content", cache_5m=500, cache_1h=200),
        ]
        result = compute_cache_miss(calls)
        assert result["overall_ttl_5m_tokens"] == 1500
        assert result["overall_ttl_1h_tokens"] == 200

    def test_overall_category_breakdown(self):
        """overall_hit/partial/miss/none_turns aggregate across all categories."""
        calls = [
            _call("Read", cache_read=5000, cache_creation=0),          # hit
            _call("Read", cache_read=5000, cache_creation=1000),        # partial
            _call("Read", cache_creation=500),                          # miss (read=0)
            _call("Read"),                                              # none
        ]
        result = compute_cache_miss(calls)
        assert result["overall_hit_turns"] == 1
        assert result["overall_partial_turns"] == 1
        assert result["overall_miss_turns"] == 1
        assert result["overall_none_turns"] == 1

    def test_empty_calls_has_new_aggregate_keys(self):
        """Empty input returns all new aggregate keys as zero."""
        result = compute_cache_miss([])
        assert result["overall_hit_turns"] == 0
        assert result["overall_partial_turns"] == 0
        assert result["overall_none_turns"] == 0
        assert result["overall_ttl_5m_tokens"] == 0
        assert result["overall_ttl_1h_tokens"] == 0


# ---------------------------------------------------------------------------
# Parser tests — _extract_usage TTL field parsing
# ---------------------------------------------------------------------------

class TestExtractUsageTTL:
    def test_parses_ttl_buckets(self):
        """_extract_usage parses nested cache_creation.ephemeral_* fields."""
        entry = {"message": {"usage": {
            "input_tokens": 5000,
            "output_tokens": 200,
            "cache_creation_input_tokens": 12073,
            "cache_read_input_tokens": 80000,
            "cache_creation": {
                "ephemeral_5m_input_tokens": 12073,
                "ephemeral_1h_input_tokens": 0,
            },
        }}}
        u = _extract_usage(entry)
        assert u.cache_creation_5m_tokens == 12073
        assert u.cache_creation_1h_tokens == 0

    def test_missing_cache_creation_dict_defaults_to_zero(self):
        """_extract_usage defaults TTL fields to 0 when nested dict is absent."""
        entry = {"message": {"usage": {
            "input_tokens": 1000,
            "output_tokens": 100,
            "cache_creation_input_tokens": 500,
            "cache_read_input_tokens": 0,
        }}}
        u = _extract_usage(entry)
        assert u.cache_creation_5m_tokens == 0
        assert u.cache_creation_1h_tokens == 0

    def test_1h_bucket_parsed(self):
        """_extract_usage parses ephemeral_1h_input_tokens correctly."""
        entry = {"message": {"usage": {
            "input_tokens": 1000,
            "output_tokens": 100,
            "cache_creation_input_tokens": 600,
            "cache_read_input_tokens": 0,
            "cache_creation": {
                "ephemeral_5m_input_tokens": 100,
                "ephemeral_1h_input_tokens": 500,
            },
        }}}
        u = _extract_usage(entry)
        assert u.cache_creation_5m_tokens == 100
        assert u.cache_creation_1h_tokens == 500


# ---------------------------------------------------------------------------
# table_height helper
# ---------------------------------------------------------------------------

class TestTableHeight:
    def test_small_table_fits_without_cap(self):
        # 5 rows: 35 * (5+1) + 3 = 213 — well under 600
        assert table_height(5) == 213

    def test_zero_rows(self):
        # header-only: 35 * 1 + 3 = 38
        assert table_height(0) == 38

    def test_large_table_capped(self):
        # 100 rows would be 35 * 101 + 3 = 3538 — capped at 600
        assert table_height(100) == 600

    def test_boundary_row_count_just_below_cap(self):
        # find n where formula first exceeds 600: 35*(n+1)+3 > 600 → n > ~16
        # n=16: 35*17+3 = 598  → fits
        assert table_height(16) == 598

    def test_boundary_row_count_at_cap(self):
        # n=17: 35*18+3 = 633 → capped at 600
        assert table_height(17) == 600
