"""Turn Cost Asymmetry — analysis logic.

IMPORTANT: Turn-level analysis only. input_tokens belongs to the entire API
turn. Multi-tool turns cannot be cleanly attributed — excluded.
Only single-tool turns are used.
"""
from __future__ import annotations

from dataclasses import dataclass
from statistics import mean

from scripts.observatory.data.parser import ApiCall, ToolCall
from scripts.observatory.data.tool_categories import CATEGORIES, classify_tool

_DEFAULT_CATEGORIES = list(CATEGORIES.keys())


@dataclass(frozen=True)
class TurnCostStats:
    """Per-category token cost statistics from single-tool turns."""

    category: str
    n: int
    mean_input_tokens: float
    mean_content_length: float | None  # None when no tool results with content


def compute_turn_cost(
    api_calls: list[ApiCall],
    categories: list[str] | None = None,
) -> dict:  # type: ignore[type-arg]
    """Compute turn cost stats for the given categories.

    Filters to single-tool turns only. Returns a dict with:
    - 'stats': list[TurnCostStats] — one entry per requested category
    - 'total_turns': int
    - 'single_tool_turns': int
    - 'single_tool_fraction': float

    Args:
        api_calls:  turns to analyse.
        categories: which categories to bucket. Defaults to all CATEGORIES keys.
                    Any turn whose single tool does not match a requested category
                    is counted in single_tool_turns but not in any bucket.
    """
    cats = categories if categories is not None else _DEFAULT_CATEGORIES
    buckets: dict[str, list[tuple[int, int | None]]] = {c: [] for c in cats}

    total_turns = len(api_calls)
    single_tool_turns = 0

    for call in api_calls:
        if len(call.tool_calls) != 1:
            continue
        single_tool_turns += 1

        tc: ToolCall = call.tool_calls[0]
        category = classify_tool(tc.name)
        if category is None or category not in buckets:
            continue

        content_len: int | None = None
        if call.tool_results:
            content_len = call.tool_results[0].content_length

        buckets[category].append((call.usage.input_tokens, content_len))

    stats: list[TurnCostStats] = []
    for category, samples in buckets.items():
        if not samples:
            stats.append(TurnCostStats(
                category=category,
                n=0,
                mean_input_tokens=0.0,
                mean_content_length=None,
            ))
            continue

        content_lens = [s[1] for s in samples if s[1] is not None]
        stats.append(TurnCostStats(
            category=category,
            n=len(samples),
            mean_input_tokens=mean(s[0] for s in samples),
            mean_content_length=mean(content_lens) if content_lens else None,
        ))

    single_fraction = single_tool_turns / total_turns if total_turns > 0 else 0.0

    return {
        "stats": stats,
        "total_turns": total_turns,
        "single_tool_turns": single_tool_turns,
        "single_tool_fraction": single_fraction,
    }
