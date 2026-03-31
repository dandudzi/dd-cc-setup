"""Tests for scripts/analyze/report.py — JSON report building and output."""
import json
from pathlib import Path

import pytest

from scripts.analyze.aggregator import GlobalStats, aggregate_session, merge_sessions
from scripts.analyze.classifiers import WasteReport
from scripts.analyze.parser import ApiCall, TokenUsage, ToolCall
from scripts.analyze.report import build_json_report, print_summary, write_report

# ---------------------------------------------------------------------------
# Factories
# ---------------------------------------------------------------------------


def _empty_global() -> GlobalStats:
    return merge_sessions([])


def _empty_waste() -> WasteReport:
    return WasteReport(
        total_reads=0,
        redirectable_reads=0,
        waste_fraction=0.0,
        by_extension={},
        by_tier={},
    )


def _sample_global() -> GlobalStats:
    tc = ToolCall("Read", "tu-1", {"file_path": "/src/app.py"}, "/src/app.py", ".py")
    call = ApiCall(
        request_id="req-1",
        session_id="sess-1",
        agent_id=None,
        permission_mode="default",
        stop_reason="end_turn",
        tool_calls=(tc,),
        tool_results=(),
        usage=TokenUsage(100, 50, 0, 0),
    )
    session = aggregate_session([call], session_id="sess-1")
    return merge_sessions([session])


# ---------------------------------------------------------------------------
# TestBuildJsonReport
# ---------------------------------------------------------------------------


class TestBuildJsonReport:
    def test_returns_dict(self):
        report = build_json_report(
            global_stats=_empty_global(),
            waste=_empty_waste(),
            modes={},
            validations={},
            sequences={},
        )
        assert isinstance(report, dict)

    def test_has_required_sections(self):
        report = build_json_report(
            global_stats=_empty_global(),
            waste=_empty_waste(),
            modes={},
            validations={},
            sequences={},
        )
        assert "corpus" in report
        assert "per_tool_costs" in report
        assert "per_extension_costs" in report
        assert "waste_analysis" in report
        assert "session_modes" in report
        assert "decision_tree_validation" in report
        assert "sequence_analysis" in report

    def test_corpus_section_contains_session_count(self):
        g = _empty_global()
        report = build_json_report(g, _empty_waste(), {}, {}, {})
        assert "session_count" in report["corpus"]

    def test_corpus_section_tokens(self):
        g = _sample_global()
        report = build_json_report(g, _empty_waste(), {}, {}, {})
        assert report["corpus"]["total_input_tokens"] == 100
        assert report["corpus"]["total_output_tokens"] == 50

    def test_waste_analysis_included(self):
        waste = WasteReport(
            total_reads=10,
            redirectable_reads=4,
            waste_fraction=0.4,
            by_extension={".py": {"total": 10, "redirectable": 4}},
            by_tier={"tier1": {"total": 10, "redirectable": 4}},
        )
        report = build_json_report(_empty_global(), waste, {}, {}, {})
        assert report["waste_analysis"]["total_reads"] == 10
        assert report["waste_analysis"]["waste_fraction"] == pytest.approx(0.4)

    def test_modes_and_validations_and_sequences_passed_through(self):
        report = build_json_report(
            _empty_global(),
            _empty_waste(),
            modes={"editing": 5},
            validations={"file_size_threshold": {"count": 3}},
            sequences={"read_edit_pairs": 2},
        )
        assert report["session_modes"] == {"editing": 5}
        assert report["decision_tree_validation"]["file_size_threshold"]["count"] == 3
        assert report["sequence_analysis"]["read_edit_pairs"] == 2

    def test_json_serializable(self):
        report = build_json_report(_empty_global(), _empty_waste(), {}, {}, {})
        # Should not raise
        json.dumps(report)


# ---------------------------------------------------------------------------
# TestWriteReport
# ---------------------------------------------------------------------------


class TestWriteReport:
    def test_writes_json_file(self, tmp_path: Path):
        report = {"corpus": {"session_count": 0}}
        out = tmp_path / "report.json"
        write_report(report, out)
        assert out.exists()
        loaded = json.loads(out.read_text())
        assert loaded["corpus"]["session_count"] == 0

    def test_creates_parent_dirs(self, tmp_path: Path):
        report = {"corpus": {}}
        out = tmp_path / "nested" / "dir" / "report.json"
        write_report(report, out)
        assert out.exists()

    def test_overwrites_existing_file(self, tmp_path: Path):
        out = tmp_path / "report.json"
        out.write_text('{"old": true}')
        write_report({"new": True}, out)
        loaded = json.loads(out.read_text())
        assert "new" in loaded
        assert "old" not in loaded


# ---------------------------------------------------------------------------
# TestPrintSummary
# ---------------------------------------------------------------------------


class TestPrintSummary:
    def test_runs_without_error(self, capsys):
        report = build_json_report(
            _sample_global(),
            WasteReport(5, 2, 0.4, {}, {}),
            modes={"editing": 1, "exploration": 2, "mixed": 0},
            validations={},
            sequences={"read_edit_pairs": 3},
        )
        print_summary(report)  # should not raise
        captured = capsys.readouterr()
        assert len(captured.out) > 0

    def test_output_contains_key_metrics(self, capsys):
        report = build_json_report(
            _sample_global(),
            WasteReport(10, 4, 0.4, {}, {}),
            modes={},
            validations={},
            sequences={},
        )
        print_summary(report)
        out = capsys.readouterr().out
        # Should mention waste or sessions somewhere
        assert any(kw in out.lower() for kw in ["waste", "session", "read", "token"])
