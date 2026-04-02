"""R6 analysis CLI: estimate savings from PostToolUse/cron reindexing.

Usage:
    uv run python -m scripts.analyze.r6_main [--projects-dir PATH] [--output PATH]

Outputs:
- JSON report to --output (default: docs/findings/r6-results.json)
- Prints a markdown summary to stdout for appending to 015 findings
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from scripts.analyze.parser import deduplicate_api_calls, discover_transcripts, parse_session
from scripts.analyze.posttooluse import (
    R3_MEAN_DETOUR_COST,
    R5_MEAN_CHAIN_COST,
    build_error_map,
    compute_counterfactual,
    extract_index_calls,
    extract_write_edit_events,
)

DEFAULT_PROJECTS_DIR = Path.home() / ".claude" / "projects"
DEFAULT_OUTPUT = Path("docs/findings/r6-results.json")


def _run(projects_dir: Path, output_path: Path) -> None:
    transcripts = discover_transcripts(projects_dir)
    if not transcripts:
        print(f"No transcripts found in {projects_dir}", file=sys.stderr)
        sys.exit(1)

    all_index_calls = []
    all_write_events = []
    total_bash_creates = 0
    session_count = 0

    for tf in transcripts:
        entries = list(parse_session(tf.path))
        if not entries:
            continue
        error_map = build_error_map(entries)
        api_calls = deduplicate_api_calls(entries, session_id=tf.session_id)
        if not api_calls:
            continue
        session_count += 1
        all_index_calls.extend(extract_index_calls(api_calls, error_map, tf.session_id))
        write_events, bash_creates = extract_write_edit_events(api_calls, tf.session_id)
        all_write_events.extend(write_events)
        total_bash_creates += bash_creates

    result = compute_counterfactual(
        all_index_calls,
        all_write_events,
        total_bash_creates,
        session_count=session_count,
    )

    # Build index call breakdown
    post_deny_count = result.post_deny_index_chains
    post_ts_count = result.post_toolsearch_index_chains
    other_count = sum(1 for c in all_index_calls if c.trigger == "other")
    total_index = len(all_index_calls)

    report = {
        "sessions_analyzed": session_count,
        "transcripts_found": len(transcripts),
        "index_calls": {
            "total": total_index,
            "post_deny": post_deny_count,
            "post_toolsearch": post_ts_count,
            "other": other_count,
            "post_deny_pct": round(post_deny_count / total_index * 100, 1) if total_index else 0,
            "post_ts_pct": round(post_ts_count / total_index * 100, 1) if total_index else 0,
        },
        "savings": {
            "direct_tokens": result.post_deny_tokens_saved,
            "indirect_low_tokens": result.indirect_savings_low,
            "indirect_mid_tokens": result.indirect_savings_mid,
            "indirect_high_tokens": result.indirect_savings_high,
            "total_low": result.post_deny_tokens_saved + result.indirect_savings_low,
            "total_mid": result.post_deny_tokens_saved + result.indirect_savings_mid,
            "total_high": result.post_deny_tokens_saved + result.indirect_savings_high,
        },
        "write_activity": {
            "write_edit_count": result.write_edit_count,
            "writes_per_session": round(result.writes_per_session, 2),
            "bash_file_creation_count": result.bash_file_creation_count,
            "coverage_gap_pct": round(result.coverage_gap_pct * 100, 1),
        },
        "constants_used": {
            "R5_MEAN_CHAIN_COST": R5_MEAN_CHAIN_COST,
            "R3_MEAN_DETOUR_COST": R3_MEAN_DETOUR_COST,
        },
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2))

    _print_markdown(report)
    print(f"\nJSON report written to: {output_path}", file=sys.stderr)


def _print_markdown(r: dict) -> None:  # type: ignore[type-arg]
    s = r["savings"]
    w = r["write_activity"]
    ic = r["index_calls"]

    print("## 13. R6: PostToolUse/Cron Reindex Savings Estimate\n")
    print(f"n={r['sessions_analyzed']} sessions, {r['transcripts_found']} transcripts\n")
    print("### Index Call Breakdown\n")
    print("| Trigger | Count | % |")
    print("|---|---|---|")
    print(f"| post_deny (target) | {ic['post_deny']} | {ic['post_deny_pct']}% |")
    print(f"| post_toolsearch | {ic['post_toolsearch']} | {ic['post_ts_pct']}% |")
    print(f"| other | {ic['other']} | - |")
    print(f"| **total** | {ic['total']} | 100% |\n")
    print("### Counterfactual Savings (PostToolUse token cost ≈ 0)\n")
    direct = s["direct_tokens"]
    chain_cost = r["constants_used"]["R5_MEAN_CHAIN_COST"]
    print(f"**Direct savings** (post-deny chains eliminated): {direct:,} tokens")
    print(f"  = {ic['post_deny']} chains × {chain_cost} tok (R5 mean)\n")
    print("**Indirect savings** (post-ToolSearch index refreshes reduced):\n")
    print("| Elimination rate | Tokens saved |")
    print("|---|---|")
    print(f"| 25% (low) | {s['indirect_low_tokens']:,} |")
    print(f"| 50% (mid) | {s['indirect_mid_tokens']:,} |")
    print(f"| 75% (high) | {s['indirect_high_tokens']:,} |\n")
    print("**Net savings (direct + indirect):**\n")
    print("| Scenario | Tokens |")
    print("|---|---|")
    print(f"| Conservative (25%) | {s['total_low']:,} |")
    print(f"| Mid (50%) | {s['total_mid']:,} |")
    print(f"| Optimistic (75%) | {s['total_high']:,} |\n")
    print("### PostToolUse Trigger Volume\n")
    print("| Metric | Value |")
    print("|---|---|")
    print(f"| Write+Edit+MultiEdit total | {w['write_edit_count']:,} |")
    print(f"| Avg per session | {w['writes_per_session']} |")
    print(f"| Bash file creations | {w['bash_file_creation_count']:,} |")
    print(f"| Coverage gap | {w['coverage_gap_pct']}% |\n")
    print("### PostToolUse vs Cron: Qualitative Comparison\n")
    print("| Dimension | PostToolUse (Write/Edit) | Cron (every 2min) |")
    print("|---|---|---|")
    print("| Model token cost | ≈0 (hook outside context) | ≈0 (cron outside context) |")
    print("| Staleness window | 0ms (immediate) | 0–120s |")
    print("| Trigger precision | File-change events only | Time-based (always runs) |")
    print("| Coverage | Write+Edit+MultiEdit only | All file mutations |")
    print(f"| Avg triggers/session | {w['writes_per_session']} | ~{_est_cron_per_session()} |")
    print("| Implementation complexity | Medium (hook + MCP call) | Low (CronCreate) |")
    print(f"\n**Coverage gap:** {w['coverage_gap_pct']}% of file mutations are Bash-created — not")
    print("covered by PostToolUse:Write+Edit+MultiEdit. Cron eliminates this gap.")
    print("\n> Note: Both PostToolUse and cron execute outside the model context window.")
    print("> The savings figures above are pure reductions in model token spend.")


def _est_cron_per_session() -> str:
    # Rough estimate: typical session ~30min = 15 cron triggers at 2min interval
    return "~15 (at 2min interval)"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="R6: PostToolUse reindex savings analysis")
    parser.add_argument(
        "--projects-dir",
        type=Path,
        default=DEFAULT_PROJECTS_DIR,
        help=f"Claude projects directory (default: {DEFAULT_PROJECTS_DIR})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"JSON output path (default: {DEFAULT_OUTPUT})",
    )
    args = parser.parse_args(argv)
    _run(args.projects_dir, args.output)


if __name__ == "__main__":
    main()
