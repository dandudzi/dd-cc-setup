"""Cache Miss Distribution — analysis logic.

IMPORTANT: Turn-level analysis only. cache_creation_input_tokens belongs to
the entire API turn. Multi-tool turns cannot be cleanly attributed — excluded.
Only single-tool turns are used.

Cache misses are structural (context window changes), not caused by tool choice.
This module measures *where* misses land across tool categories.

4-category cache model:
  hit     — cache_read > 0, cache_creation == 0  (fully cached, no cost)
  partial — cache_read > 0, cache_creation > 0   (reuse + new write, most common)
  miss    — cache_read == 0, cache_creation > 0   (no benefit, full write cost)
  none    — cache_read == 0, cache_creation == 0  (no caching at all, rare)
"""
from __future__ import annotations

from dataclasses import dataclass
from statistics import mean
from typing import Literal

from scripts.observatory.data.parser import ApiCall, TokenUsage, ToolCall
from scripts.observatory.data.tool_categories import CATEGORIES, classify_tool

_DEFAULT_CATEGORIES = list(CATEGORIES.keys())

CacheStatus = Literal["hit", "partial", "miss", "none"]


def _classify_cache(usage: TokenUsage) -> CacheStatus:
    has_read = usage.cache_read_input_tokens > 0
    has_create = usage.cache_creation_input_tokens > 0
    if has_read and not has_create:
        return "hit"
    if has_read and has_create:
        return "partial"
    if not has_read and has_create:
        return "miss"
    return "none"


@dataclass(frozen=True)
class CacheMissStats:
    """Per-category cache miss statistics from single-tool turns."""

    category: str
    total_turns: int         # single-tool turns attributed to this category
    hit_turns: int           # cache_read > 0 AND cache_creation == 0
    partial_turns: int       # cache_read > 0 AND cache_creation > 0
    miss_turns: int          # cache_read == 0 AND cache_creation > 0
    none_turns: int          # cache_read == 0 AND cache_creation == 0
    miss_rate: float         # miss_turns / total_turns (0.0 when total_turns == 0)
    mean_miss_tokens: float  # mean cache_creation_input_tokens across miss turns only
    total_miss_tokens: int   # sum cache_creation_input_tokens across miss turns
    ttl_5m_tokens: int       # sum cache_creation_5m_tokens across all turns
    ttl_1h_tokens: int       # sum cache_creation_1h_tokens across all turns


@dataclass
class _CategoryAccumulator:
    hit: int = 0
    partial: int = 0
    miss: int = 0
    none: int = 0
    miss_token_samples: list = None  # type: ignore[assignment]
    ttl_5m: int = 0
    ttl_1h: int = 0

    def __post_init__(self) -> None:
        if self.miss_token_samples is None:
            self.miss_token_samples = []

    @property
    def total(self) -> int:
        return self.hit + self.partial + self.miss + self.none

    def to_stats(self, category: str) -> CacheMissStats:
        miss_rate = self.miss / self.total if self.total > 0 else 0.0
        mean_miss = mean(self.miss_token_samples) if self.miss_token_samples else 0.0
        return CacheMissStats(
            category=category,
            total_turns=self.total,
            hit_turns=self.hit,
            partial_turns=self.partial,
            miss_turns=self.miss,
            none_turns=self.none,
            miss_rate=miss_rate,
            mean_miss_tokens=mean_miss,
            total_miss_tokens=sum(self.miss_token_samples),
            ttl_5m_tokens=self.ttl_5m,
            ttl_1h_tokens=self.ttl_1h,
        )


def compute_cache_miss(
    api_calls: list[ApiCall],
    categories: list[str] | None = None,
) -> dict:  # type: ignore[type-arg]
    """Compute cache miss stats for the given categories.

    Filters to single-tool turns only. Returns a dict with:
    - 'stats': list[CacheMissStats] — one entry per requested category
    - 'total_turns': int
    - 'single_tool_turns': int
    - 'overall_miss_rate': float   — miss_turns / single_tool_turns
    - 'overall_miss_turns': int
    - 'overall_miss_tokens': int
    - 'overall_hit_turns': int
    - 'overall_partial_turns': int
    - 'overall_none_turns': int
    - 'overall_ttl_5m_tokens': int
    - 'overall_ttl_1h_tokens': int
    """
    cats = categories if categories is not None else _DEFAULT_CATEGORIES
    accumulators: dict[str, _CategoryAccumulator] = {c: _CategoryAccumulator() for c in cats}

    total_turns = len(api_calls)
    single_tool_turns = 0
    overall_hit = 0
    overall_partial = 0
    overall_miss = 0
    overall_none = 0
    overall_miss_tokens = 0
    overall_ttl_5m = 0
    overall_ttl_1h = 0

    for call in api_calls:
        if len(call.tool_calls) != 1:
            continue
        single_tool_turns += 1

        tc: ToolCall = call.tool_calls[0]
        status = _classify_cache(call.usage)

        if status == "hit":
            overall_hit += 1
        elif status == "partial":
            overall_partial += 1
        elif status == "miss":
            overall_miss += 1
            overall_miss_tokens += call.usage.cache_creation_input_tokens
        else:
            overall_none += 1

        overall_ttl_5m += call.usage.cache_creation_5m_tokens
        overall_ttl_1h += call.usage.cache_creation_1h_tokens

        category = classify_tool(tc.name)
        if category is None or category not in accumulators:
            continue

        acc = accumulators[category]
        if status == "hit":
            acc.hit += 1
        elif status == "partial":
            acc.partial += 1
        elif status == "miss":
            acc.miss += 1
            acc.miss_token_samples.append(call.usage.cache_creation_input_tokens)
        else:
            acc.none += 1

        acc.ttl_5m += call.usage.cache_creation_5m_tokens
        acc.ttl_1h += call.usage.cache_creation_1h_tokens

    stats = [acc.to_stats(cat) for cat, acc in accumulators.items()]

    overall_miss_rate = overall_miss / single_tool_turns if single_tool_turns > 0 else 0.0

    return {
        "stats": stats,
        "total_turns": total_turns,
        "single_tool_turns": single_tool_turns,
        "overall_miss_rate": overall_miss_rate,
        "overall_miss_turns": overall_miss,
        "overall_miss_tokens": overall_miss_tokens,
        "overall_hit_turns": overall_hit,
        "overall_partial_turns": overall_partial,
        "overall_none_turns": overall_none,
        "overall_ttl_5m_tokens": overall_ttl_5m,
        "overall_ttl_1h_tokens": overall_ttl_1h,
    }


_TABLE_ROW_PX = 35
_TABLE_MAX_PX = 600


def table_height(n_rows: int) -> int:
    """Return the pixel height for a stats dataframe with n_rows data rows.

    Sized to fit content up to _TABLE_MAX_PX, keeping both scrollbars
    visible within the table frame.
    """
    return min(_TABLE_ROW_PX * (n_rows + 1) + 3, _TABLE_MAX_PX)
