"""CLI entry point for transcript baseline mining.

Usage:
    python -m scripts.analyze [--output <path>] [--projects-dir <path>]

Processes ~/.claude/projects/*/ transcript JSONL files to produce a
per-tool token cost baseline report. Streams one session at a time to
keep memory usage low (corpus is ~530MB).
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

from scripts.analyze.aggregator import (
    SessionStats,
    aggregate_session,
    merge_sessions,
)
from scripts.analyze.classifiers import (
    analyze_sequences,
    classify_session_mode,
    compute_waste,
    validate_decision_tree,
)
from scripts.analyze.parser import (
    deduplicate_api_calls,
    discover_transcripts,
    extract_tool_sequence,
    parse_session,
)
from scripts.analyze.report import build_json_report, print_summary, write_report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Mine Claude Code transcripts for baseline stats.")
    parser.add_argument(
        "--output",
        default="reports/transcript-baseline.json",
        help="Output JSON file path (default: reports/transcript-baseline.json)",
    )
    parser.add_argument(
        "--projects-dir",
        default=str(Path.home() / ".claude" / "projects"),
        help="Base directory containing Claude projects (default: ~/.claude/projects)",
    )
    args = parser.parse_args(argv)

    projects_dir = Path(args.projects_dir)
    output_path = Path(args.output)

    # Discover all transcript files
    transcripts = discover_transcripts(projects_dir)
    total = len(transcripts)
    print(f"Found {total} transcript files in {projects_dir}", file=sys.stderr)

    if total == 0:
        # No transcripts — produce empty report
        global_stats = merge_sessions([])
        from scripts.analyze.classifiers import WasteReport
        waste = WasteReport(0, 0, 0.0, {}, {})
        report = build_json_report(global_stats, waste, {}, {}, {})
        write_report(report, output_path)
        print_summary(report)
        return 0

    # Process sessions lazily — one at a time to keep memory low
    sessions: list[SessionStats] = []
    all_api_calls = []
    all_tool_sequences = []
    session_modes: Counter[str] = Counter()

    for i, tf in enumerate(transcripts, 1):
        if i % 50 == 0 or i == total:
            print(f"  Processing {i}/{total}...", file=sys.stderr)

        try:
            entries = list(parse_session(tf.path))
            api_calls = deduplicate_api_calls(
                entries,
                session_id=tf.session_id,
                agent_id=tf.agent_id,
            )
        except Exception as exc:
            print(f"  Warning: failed to parse {tf.path}: {exc}", file=sys.stderr)
            continue

        if not api_calls:
            continue

        session = aggregate_session(
            api_calls,
            session_id=tf.session_id,
            is_subagent=tf.is_subagent,
            agent_type=tf.agent_type,
        )
        sessions.append(session)

        mode = classify_session_mode(session)
        session_modes[mode] += 1

        tool_seq = extract_tool_sequence(api_calls)
        all_api_calls.extend(api_calls)
        all_tool_sequences.extend(tool_seq)

    global_stats = merge_sessions(sessions)

    # Build tool_results_map for waste computation
    tool_results_map = {}
    for call in all_api_calls:
        for tr in call.tool_results:
            tool_results_map[tr.tool_use_id] = tr

    waste = compute_waste(all_api_calls, tool_results_map, all_tool_sequences)
    validations = validate_decision_tree(all_api_calls, all_tool_sequences)
    sequences = analyze_sequences(all_tool_sequences)

    report = build_json_report(
        global_stats=global_stats,
        waste=waste,
        modes=dict(session_modes),
        validations=validations,
        sequences=sequences,
    )

    write_report(report, output_path)
    print_summary(report)
    print(f"\nReport written to: {output_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
