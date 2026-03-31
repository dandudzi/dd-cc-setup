"""Session mode classification, waste detection, and decision tree validation.

Extension tiers are defined locally here (not imported from matchers/base.py)
because the runtime matchers use a flat set while analysis needs tier separation.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any

from scripts.analyze.parser import ApiCall, ToolCall, ToolResult
from scripts.matchers.base import (
    _UNBOUNDED_MULTI_WORD,
    _UNBOUNDED_PATTERNS,
)

# ---------------------------------------------------------------------------
# Tiered extension sets (from jCodeMunch LANGUAGE_SUPPORT.md)
# ---------------------------------------------------------------------------

# Tier 1: full tree-sitter extraction (~45 extensions)
TIER1_CODE_EXTENSIONS = {
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".go",
    ".rs",
    ".java",
    ".kt",
    ".kts",
    ".c",
    ".h",
    ".cpp",
    ".cc",
    ".hpp",
    ".cs",
    ".swift",
    ".rb",
    ".php",
    ".scala",
    ".lua",
    ".sql",
    ".sh",
    ".bash",
    ".zsh",
    ".fish",
    ".vue",
    ".svelte",
    ".elm",
    ".ex",
    ".exs",
    ".erl",
    ".hrl",
    ".hs",
    ".ml",
    ".mli",
    ".clj",
    ".cljs",
    ".r",
    ".jl",
    ".dart",
    ".groovy",
    ".gradle",
    ".tf",
    ".hcl",
}

# Tier 2: text-only extraction (~5 extensions)
TIER2_CODE_EXTENSIONS = {
    ".jsonnet",
    ".graphql",
    ".gql",
    ".proto",
    ".thrift",
}

# Tier 3: regex-based extraction (~8 extensions)
TIER3_CODE_EXTENSIONS = {
    ".css",
    ".scss",
    ".sass",
    ".less",
    ".html",
    ".xml",
    ".twig",
    ".njk",
}

# Config file extensions for decision tree validation item 4
_CONFIG_EXTENSIONS = {".json", ".yaml", ".yml", ".toml"}

# Session mode classification thresholds
_EDITING_THRESHOLD = 0.30  # Edit+Write fraction > 30% → editing
_EXPLORATION_THRESHOLD = 0.70  # Read+Grep+Glob+Bash fraction > 70% → exploration

_EDITING_TOOLS = {"Edit", "Write"}
_EXPLORATION_TOOLS = {"Read", "Grep", "Glob", "Bash"}


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class WasteReport:
    """Result of waste analysis across Read calls."""

    total_reads: int
    redirectable_reads: int
    waste_fraction: float
    # extension → {"total": int, "redirectable": int}
    by_extension: dict[str, dict[str, int]]
    # "tier1" | "tier2" | "tier3" | "other" → {"total": int, "redirectable": int}
    by_tier: dict[str, dict[str, int]]


# ---------------------------------------------------------------------------
# classify_session_mode
# ---------------------------------------------------------------------------


def classify_session_mode(stats: Any) -> str:
    """Classify a session as 'editing', 'exploration', or 'mixed'.

    - editing: Edit+Write calls > EDITING_THRESHOLD of total
    - exploration: Read+Grep+Glob+Bash > EXPLORATION_THRESHOLD of total
    - mixed: neither
    """
    counts = stats.tool_call_counts
    total = sum(counts.values())
    if total == 0:
        return "mixed"

    editing_count = sum(counts.get(t, 0) for t in _EDITING_TOOLS)
    exploration_count = sum(counts.get(t, 0) for t in _EXPLORATION_TOOLS)

    if editing_count / total > _EDITING_THRESHOLD:
        return "editing"
    if exploration_count / total > _EXPLORATION_THRESHOLD:
        return "exploration"
    return "mixed"


# ---------------------------------------------------------------------------
# compute_waste
# ---------------------------------------------------------------------------


def _get_tier(file_ext: str | None) -> str:
    if file_ext in TIER1_CODE_EXTENSIONS:
        return "tier1"
    if file_ext in TIER2_CODE_EXTENSIONS:
        return "tier2"
    if file_ext in TIER3_CODE_EXTENSIONS:
        return "tier3"
    return "other"


def compute_waste(
    api_calls: list[ApiCall],
    tool_results_map: dict[str, ToolResult],
    tool_sequence: list[ToolCall],
) -> WasteReport:
    """Detect redirectable Read calls.

    A Read is redirectable if ALL of:
    - It is a Read call
    - Not preceded immediately by an Edit or Write in the tool sequence
    - No offset or limit in the tool input

    Returns WasteReport with counts by extension and tier.
    """
    total_reads = 0
    redirectable_reads = 0
    by_extension: dict[str, dict[str, int]] = {}
    by_tier: dict[str, dict[str, int]] = {}

    # Build ordered tool sequence from all api_calls
    seq = tool_sequence

    for i, tc in enumerate(seq):
        if tc.name != "Read":
            continue
        total_reads += 1

        # Check if preceded by Edit or Write
        preceded_by_edit = i > 0 and seq[i - 1].name in _EDITING_TOOLS

        # Check for offset/limit in input
        has_slice = bool(tc.input.get("offset") or tc.input.get("limit"))

        is_redirectable = not preceded_by_edit and not has_slice

        ext = tc.file_ext
        tier = _get_tier(ext)

        # Accumulate by_extension
        ext_key = ext or "unknown"
        if ext_key not in by_extension:
            by_extension[ext_key] = {"total": 0, "redirectable": 0}
        by_extension[ext_key]["total"] += 1

        # Accumulate by_tier
        if tier not in by_tier:
            by_tier[tier] = {"total": 0, "redirectable": 0}
        by_tier[tier]["total"] += 1

        if is_redirectable:
            redirectable_reads += 1
            by_extension[ext_key]["redirectable"] += 1
            by_tier[tier]["redirectable"] += 1

    waste_fraction = redirectable_reads / total_reads if total_reads > 0 else 0.0

    return WasteReport(
        total_reads=total_reads,
        redirectable_reads=redirectable_reads,
        waste_fraction=waste_fraction,
        by_extension=by_extension,
        by_tier=by_tier,
    )


# ---------------------------------------------------------------------------
# validate_decision_tree
# ---------------------------------------------------------------------------


def validate_decision_tree(
    api_calls: list[ApiCall],
    tool_sequence: list[ToolCall],
) -> dict[str, Any]:
    """Validate the 5 calibration items from the decision tree.

    1. file_size_threshold: distribution of Read result sizes
    2. bash_unbounded_patterns: fraction of Bash calls matching unbounded patterns
    3. tier_2_3_extensions: Read calls on tier 2/3 extensions
    4. config_files: .json/.yaml/.toml Read frequency
    5. context_mode_vs_jcodemunch: co-occurrence in sessions
    """
    return {
        "file_size_threshold": _validate_file_size(api_calls),
        "bash_unbounded_patterns": _validate_bash_unbounded(tool_sequence),
        "tier_2_3_extensions": _validate_tier_extensions(tool_sequence),
        "config_files": _validate_config_files(tool_sequence),
        "context_mode_vs_jcodemunch": _validate_context_jcodemunch(api_calls, tool_sequence),
    }


def _validate_file_size(api_calls: list[ApiCall]) -> dict[str, Any]:
    """Distribution of Read result sizes using tool_result content_length."""
    sizes = []
    for call in api_calls:
        # Build a map of tool_use_id → content_length from tool_results
        tr_map = {tr.tool_use_id: tr.content_length for tr in call.tool_results}
        for tc in call.tool_calls:
            if tc.name == "Read" and tc.tool_use_id in tr_map:
                length = tr_map[tc.tool_use_id]
                if length is not None:
                    sizes.append(length)

    if not sizes:
        return {"count": 0, "sizes": [], "optimal_threshold": None}

    sizes_sorted = sorted(sizes)
    return {
        "count": len(sizes),
        "min": sizes_sorted[0],
        "max": sizes_sorted[-1],
        "median": sizes_sorted[len(sizes_sorted) // 2],
        "optimal_threshold": _suggest_threshold(sizes_sorted),
    }


def _suggest_threshold(sorted_sizes: list[int]) -> int:
    """Suggest a threshold that captures the top 20% of large reads."""
    idx = int(0.80 * len(sorted_sizes))
    return sorted_sizes[min(idx, len(sorted_sizes) - 1)]


def _validate_bash_unbounded(tool_sequence: list[ToolCall]) -> dict[str, Any]:
    """Count Bash calls matching unbounded output patterns."""
    total_bash = 0
    unbounded_count = 0

    for tc in tool_sequence:
        if tc.name != "Bash":
            continue
        total_bash += 1
        command = tc.input.get("command", "") if isinstance(tc.input, dict) else ""
        if not isinstance(command, str):
            continue
        normalized = " ".join(command.split())
        if any(p.search(normalized) for p in _UNBOUNDED_PATTERNS) or any(
            t in normalized for t in _UNBOUNDED_MULTI_WORD
        ):
            unbounded_count += 1

    return {
        "total_bash": total_bash,
        "unbounded_count": unbounded_count,
        "unbounded_fraction": unbounded_count / total_bash if total_bash > 0 else 0.0,
    }


def _validate_tier_extensions(tool_sequence: list[ToolCall]) -> dict[str, Any]:
    """Count Read calls on tier 2/3 extensions."""
    tier2_counts: Counter[str] = Counter()
    tier3_counts: Counter[str] = Counter()

    for tc in tool_sequence:
        if tc.name != "Read" or not tc.file_ext:
            continue
        ext = tc.file_ext
        if ext in TIER2_CODE_EXTENSIONS:
            tier2_counts[ext] += 1
        elif ext in TIER3_CODE_EXTENSIONS:
            tier3_counts[ext] += 1

    return {
        "tier2": dict(tier2_counts),
        "tier3": dict(tier3_counts),
        "tier2_total": sum(tier2_counts.values()),
        "tier3_total": sum(tier3_counts.values()),
    }


def _validate_config_files(tool_sequence: list[ToolCall]) -> dict[str, Any]:
    """Count Read calls on config file extensions."""
    config_counts: Counter[str] = Counter()

    for tc in tool_sequence:
        if tc.name != "Read" or not tc.file_ext:
            continue
        if tc.file_ext in _CONFIG_EXTENSIONS:
            config_counts[tc.file_ext] += 1

    return {
        "by_extension": dict(config_counts),
        "total_reads": sum(config_counts.values()),
    }


def _validate_context_jcodemunch(
    api_calls: list[ApiCall],
    tool_sequence: list[ToolCall],
) -> dict[str, Any]:
    """Count co-occurrence of context-mode and jCodeMunch tools in the session."""
    has_context_mode = any(
        tc.name.startswith("mcp__plugin_context-mode") for tc in tool_sequence
    )
    has_jcodemunch = any(
        tc.name.startswith("mcp__jcodemunch__") for tc in tool_sequence
    )
    return {
        "has_context_mode": has_context_mode,
        "has_jcodemunch": has_jcodemunch,
        "sessions_with_both": 1 if (has_context_mode and has_jcodemunch) else 0,
        "context_mode_calls": sum(
            1 for tc in tool_sequence if tc.name.startswith("mcp__plugin_context-mode")
        ),
        "jcodemunch_calls": sum(
            1 for tc in tool_sequence if tc.name.startswith("mcp__jcodemunch__")
        ),
    }


# ---------------------------------------------------------------------------
# analyze_sequences
# ---------------------------------------------------------------------------


def analyze_sequences(tool_sequence: list[ToolCall]) -> dict[str, Any]:
    """Analyze tool call sequences: Read→Edit pairs, top bigrams."""
    if not tool_sequence:
        return {"read_edit_pairs": 0, "top_bigrams": []}

    read_edit_pairs = 0
    bigram_counts: Counter[tuple[str, str]] = Counter()

    for i in range(len(tool_sequence) - 1):
        a = tool_sequence[i].name
        b = tool_sequence[i + 1].name
        bigram_counts[(a, b)] += 1
        if a == "Read" and b == "Edit":
            read_edit_pairs += 1

    top_bigrams = bigram_counts.most_common(10)

    return {
        "read_edit_pairs": read_edit_pairs,
        "top_bigrams": top_bigrams,
    }
