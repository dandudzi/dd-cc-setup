"""JSON report building and output for task 1.4 baseline mining."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.analyze.aggregator import GlobalStats, compute_per_extension_costs
from scripts.analyze.classifiers import WasteReport


def build_json_report(
    global_stats: GlobalStats,
    waste: WasteReport,
    modes: dict[str, Any],
    validations: dict[str, Any],
    sequences: dict[str, Any],
) -> dict[str, Any]:
    """Assemble the full JSON report from all analysis components."""
    per_ext = compute_per_extension_costs(global_stats)

    return {
        "corpus": {
            "session_count": global_stats.session_count,
            "total_input_tokens": global_stats.total_input_tokens,
            "total_output_tokens": global_stats.total_output_tokens,
            "total_cache_creation_tokens": global_stats.total_cache_creation,
            "total_cache_read_tokens": global_stats.total_cache_read,
            "total_tool_calls": sum(global_stats.tool_call_counts.values()),
        },
        "per_tool_costs": {
            tool: {
                "call_count": global_stats.tool_call_counts.get(tool, 0),
                "samples_count": len(costs["samples"]),
            }
            for tool, costs in global_stats.tool_token_costs.items()
        },
        "per_extension_costs": per_ext,
        "waste_analysis": {
            "total_reads": waste.total_reads,
            "redirectable_reads": waste.redirectable_reads,
            "waste_fraction": waste.waste_fraction,
            "by_extension": waste.by_extension,
            "by_tier": waste.by_tier,
        },
        "session_modes": modes,
        "decision_tree_validation": validations,
        "sequence_analysis": sequences,
    }


def print_summary(report: dict[str, Any]) -> None:
    """Print a human-readable summary of the report to stdout."""
    corpus = report.get("corpus", {})
    waste = report.get("waste_analysis", {})
    modes = report.get("session_modes", {})
    seq = report.get("sequence_analysis", {})

    print("=" * 60)
    print("Transcript Baseline Report — Summary")
    print("=" * 60)
    print(f"Sessions analyzed:    {corpus.get('session_count', 0)}")
    print(f"Total input tokens:   {corpus.get('total_input_tokens', 0):,}")
    print(f"Total output tokens:  {corpus.get('total_output_tokens', 0):,}")
    print(f"Total tool calls:     {corpus.get('total_tool_calls', 0):,}")
    print()
    print("Waste Analysis:")
    print(f"  Total reads:        {waste.get('total_reads', 0)}")
    print(f"  Redirectable reads: {waste.get('redirectable_reads', 0)}")
    frac = waste.get("waste_fraction", 0.0)
    print(f"  Waste fraction:     {frac:.1%}")
    print()
    if modes:
        print("Session Modes:")
        for mode, count in sorted(modes.items()):
            print(f"  {mode:15s}: {count}")
        print()
    re_pairs = seq.get("read_edit_pairs", 0)
    print(f"Read→Edit pairs:      {re_pairs}")
    print("=" * 60)


def write_report(report: dict[str, Any], path: Path) -> None:
    """Write the JSON report to a file, creating parent directories as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
