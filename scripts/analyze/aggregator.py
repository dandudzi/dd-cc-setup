"""Token cost accumulation for task 1.4 baseline mining.

Aggregates per-session and global statistics from parsed ApiCall sequences.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Any

from scripts.analyze.parser import ApiCall, extract_tool_sequence

# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class SessionStats:
    """Accumulated statistics for a single session."""

    session_id: str
    is_subagent: bool
    agent_type: str | None
    permission_modes: set[str]
    total_input_tokens: int
    total_output_tokens: int
    total_cache_creation: int
    total_cache_read: int
    # tool name → {"samples": [{"output_tokens": int, "approximate": bool}]}
    tool_token_costs: dict[str, dict[str, Any]]
    # file extension → {"samples": [...]}
    ext_token_costs: dict[str, dict[str, Any]]
    # tool name → count
    tool_call_counts: dict[str, int]
    # ordered list of ToolCall objects
    tool_sequence: list


@dataclass
class GlobalStats:
    """Merged statistics across all sessions."""

    session_count: int
    total_input_tokens: int
    total_output_tokens: int
    total_cache_creation: int
    total_cache_read: int
    # tool name → {"samples": [...]}
    tool_token_costs: dict[str, dict[str, Any]]
    # file extension → {"samples": [...]}
    ext_token_costs: dict[str, dict[str, Any]]
    # tool name → count
    tool_call_counts: dict[str, int]


# ---------------------------------------------------------------------------
# aggregate_session
# ---------------------------------------------------------------------------


def aggregate_session(
    api_calls: list[ApiCall],
    session_id: str,
    is_subagent: bool = False,
    agent_type: str | None = None,
) -> SessionStats:
    """Accumulate token costs from a list of ApiCalls into SessionStats.

    Token attribution:
    - Single-tool API calls: exact output_tokens assigned to that tool.
    - Multi-tool API calls: output_tokens split evenly; samples tagged
      approximate=True so they can be excluded from median calculations.
    """
    total_input = 0
    total_output = 0
    total_cache_creation = 0
    total_cache_read = 0
    tool_token_costs: dict[str, dict[str, Any]] = {}
    ext_token_costs: dict[str, dict[str, Any]] = {}
    tool_call_counts: dict[str, int] = {}
    permission_modes: set[str] = set()

    for call in api_calls:
        total_input += call.usage.input_tokens
        total_output += call.usage.output_tokens
        total_cache_creation += call.usage.cache_creation_input_tokens
        total_cache_read += call.usage.cache_read_input_tokens

        if call.permission_mode:
            permission_modes.add(call.permission_mode)

        n = len(call.tool_calls)
        if n == 0:
            continue

        approximate = n > 1
        per_tool_tokens = call.usage.output_tokens // n

        for tc in call.tool_calls:
            # Count
            tool_call_counts[tc.name] = tool_call_counts.get(tc.name, 0) + 1

            # Token cost by tool name
            sample = {"output_tokens": per_tool_tokens, "approximate": approximate}
            if tc.name not in tool_token_costs:
                tool_token_costs[tc.name] = {"samples": []}
            tool_token_costs[tc.name]["samples"].append(sample)

            # Token cost by extension
            if tc.file_ext:
                if tc.file_ext not in ext_token_costs:
                    ext_token_costs[tc.file_ext] = {"samples": []}
                ext_token_costs[tc.file_ext]["samples"].append(sample)

    tool_sequence = extract_tool_sequence(api_calls)

    return SessionStats(
        session_id=session_id,
        is_subagent=is_subagent,
        agent_type=agent_type,
        permission_modes=permission_modes,
        total_input_tokens=total_input,
        total_output_tokens=total_output,
        total_cache_creation=total_cache_creation,
        total_cache_read=total_cache_read,
        tool_token_costs=tool_token_costs,
        ext_token_costs=ext_token_costs,
        tool_call_counts=tool_call_counts,
        tool_sequence=tool_sequence,
    )


# ---------------------------------------------------------------------------
# merge_sessions
# ---------------------------------------------------------------------------


def merge_sessions(sessions: list[SessionStats]) -> GlobalStats:
    """Sum statistics across all sessions into a GlobalStats."""
    total_input = 0
    total_output = 0
    total_cache_creation = 0
    total_cache_read = 0
    tool_token_costs: dict[str, dict[str, Any]] = {}
    ext_token_costs: dict[str, dict[str, Any]] = {}
    tool_call_counts: dict[str, int] = {}

    for sess in sessions:
        total_input += sess.total_input_tokens
        total_output += sess.total_output_tokens
        total_cache_creation += sess.total_cache_creation
        total_cache_read += sess.total_cache_read

        for tool, costs in sess.tool_token_costs.items():
            if tool not in tool_token_costs:
                tool_token_costs[tool] = {"samples": []}
            tool_token_costs[tool]["samples"].extend(costs["samples"])

        for ext, costs in sess.ext_token_costs.items():
            if ext not in ext_token_costs:
                ext_token_costs[ext] = {"samples": []}
            ext_token_costs[ext]["samples"].extend(costs["samples"])

        for tool, count in sess.tool_call_counts.items():
            tool_call_counts[tool] = tool_call_counts.get(tool, 0) + count

    return GlobalStats(
        session_count=len(sessions),
        total_input_tokens=total_input,
        total_output_tokens=total_output,
        total_cache_creation=total_cache_creation,
        total_cache_read=total_cache_read,
        tool_token_costs=tool_token_costs,
        ext_token_costs=ext_token_costs,
        tool_call_counts=tool_call_counts,
    )


# ---------------------------------------------------------------------------
# compute_per_extension_costs
# ---------------------------------------------------------------------------


def compute_per_extension_costs(global_stats: GlobalStats) -> dict[str, dict[str, Any]]:
    """Compute mean, median (exact-only), p95, total, count per extension.

    Approximate samples (multi-tool splits) are excluded from the median
    calculation to avoid skew.
    """
    result: dict[str, dict[str, Any]] = {}

    for ext, costs in global_stats.ext_token_costs.items():
        samples = costs["samples"]
        if not samples:
            continue

        all_tokens = [s["output_tokens"] for s in samples]
        exact_tokens = [s["output_tokens"] for s in samples if not s["approximate"]]

        mean = statistics.mean(all_tokens) if all_tokens else 0.0
        median = statistics.median(exact_tokens) if exact_tokens else statistics.median(all_tokens)
        total = sum(all_tokens)
        count = len(all_tokens)

        # p95
        if len(all_tokens) >= 2:
            sorted_tokens = sorted(all_tokens)
            idx = int(0.95 * (len(sorted_tokens) - 1))
            p95 = sorted_tokens[idx]
        else:
            p95 = all_tokens[0] if all_tokens else 0

        result[ext] = {
            "mean": mean,
            "median": median,
            "p95": p95,
            "total": total,
            "count": count,
        }

    return result
