"""Tests for scripts/observatory/data/filters.py.

TDD: written before implementation (RED phase).
"""
from __future__ import annotations

import os
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from scripts.observatory.data.parser import TranscriptFile


# ---------------------------------------------------------------------------
# Factories
# ---------------------------------------------------------------------------


def _transcript(path: Path, session_id: str = "sess-1") -> TranscriptFile:
    return TranscriptFile(
        path=path,
        session_id=session_id,
        is_subagent=False,
        agent_id=None,
        agent_type=None,
    )


def _make_file(tmp_path: Path, project: str, session_id: str, target_date: date) -> TranscriptFile:
    """Create a real .jsonl file with a controlled mtime."""
    project_dir = tmp_path / project
    project_dir.mkdir(exist_ok=True)
    f = project_dir / f"{session_id}.jsonl"
    f.write_text("")
    # Convert date to timestamp (noon UTC to avoid timezone edge cases)
    ts = datetime(target_date.year, target_date.month, target_date.day, 12, 0, 0,
                  tzinfo=timezone.utc).timestamp()
    os.utime(f, (ts, ts))
    return _transcript(f, session_id)


# ---------------------------------------------------------------------------
# project_from_path
# ---------------------------------------------------------------------------


class TestProjectFromPath:
    def test_returns_parent_dir_name(self, tmp_path: Path) -> None:
        from scripts.observatory.data.filters import project_from_path
        p = tmp_path / "my-project" / "session.jsonl"
        assert project_from_path(p) == "my-project"

    def test_encoded_path_dir_name(self, tmp_path: Path) -> None:
        from scripts.observatory.data.filters import project_from_path
        p = tmp_path / "-Users-daniel-Repos-myrepo" / "session.jsonl"
        assert project_from_path(p) == "-Users-daniel-Repos-myrepo"


# ---------------------------------------------------------------------------
# filter_transcripts
# ---------------------------------------------------------------------------


class TestFilterTranscripts:
    def test_no_filter_returns_all(self, tmp_path: Path) -> None:
        from scripts.observatory.data.filters import FilterSpec, filter_transcripts
        t1 = _make_file(tmp_path, "proj-a", "s1", date(2026, 1, 1))
        t2 = _make_file(tmp_path, "proj-b", "s2", date(2026, 1, 2))
        result = filter_transcripts([t1, t2], FilterSpec())
        assert result == [t1, t2]

    def test_project_filter(self, tmp_path: Path) -> None:
        from scripts.observatory.data.filters import FilterSpec, filter_transcripts
        t1 = _make_file(tmp_path, "proj-a", "s1", date(2026, 1, 1))
        t2 = _make_file(tmp_path, "proj-b", "s2", date(2026, 1, 2))
        result = filter_transcripts([t1, t2], FilterSpec(projects=["proj-a"]))
        assert result == [t1]
        assert t2 not in result

    def test_session_filter(self, tmp_path: Path) -> None:
        from scripts.observatory.data.filters import FilterSpec, filter_transcripts
        t1 = _make_file(tmp_path, "proj-a", "sess-abc", date(2026, 1, 1))
        t2 = _make_file(tmp_path, "proj-a", "sess-xyz", date(2026, 1, 2))
        result = filter_transcripts([t1, t2], FilterSpec(session_ids=["sess-abc"]))
        assert result == [t1]

    def test_date_start_excludes_older(self, tmp_path: Path) -> None:
        from scripts.observatory.data.filters import FilterSpec, filter_transcripts
        old = _make_file(tmp_path, "proj-a", "s1", date(2025, 12, 31))
        new = _make_file(tmp_path, "proj-a", "s2", date(2026, 1, 15))
        result = filter_transcripts([old, new], FilterSpec(date_start=date(2026, 1, 1)))
        assert result == [new]
        assert old not in result

    def test_date_end_excludes_newer(self, tmp_path: Path) -> None:
        from scripts.observatory.data.filters import FilterSpec, filter_transcripts
        old = _make_file(tmp_path, "proj-a", "s1", date(2025, 12, 15))
        new = _make_file(tmp_path, "proj-a", "s2", date(2026, 2, 1))
        result = filter_transcripts([old, new], FilterSpec(date_end=date(2025, 12, 31)))
        assert result == [old]

    def test_date_range_inclusive(self, tmp_path: Path) -> None:
        from scripts.observatory.data.filters import FilterSpec, filter_transcripts
        t_start = _make_file(tmp_path, "proj-a", "s1", date(2026, 1, 1))
        t_mid = _make_file(tmp_path, "proj-a", "s2", date(2026, 1, 15))
        t_end = _make_file(tmp_path, "proj-a", "s3", date(2026, 1, 31))
        t_out = _make_file(tmp_path, "proj-a", "s4", date(2026, 2, 5))
        result = filter_transcripts(
            [t_start, t_mid, t_end, t_out],
            FilterSpec(date_start=date(2026, 1, 1), date_end=date(2026, 1, 31)),
        )
        assert set(result) == {t_start, t_mid, t_end}
        assert t_out not in result

    def test_combined_project_and_date(self, tmp_path: Path) -> None:
        from scripts.observatory.data.filters import FilterSpec, filter_transcripts
        keep = _make_file(tmp_path, "proj-a", "s1", date(2026, 1, 10))
        wrong_proj = _make_file(tmp_path, "proj-b", "s2", date(2026, 1, 10))
        too_old = _make_file(tmp_path, "proj-a", "s3", date(2025, 6, 1))
        result = filter_transcripts(
            [keep, wrong_proj, too_old],
            FilterSpec(projects=["proj-a"], date_start=date(2026, 1, 1)),
        )
        assert result == [keep]

    def test_empty_input(self) -> None:
        from scripts.observatory.data.filters import FilterSpec, filter_transcripts
        assert filter_transcripts([], FilterSpec()) == []


# ---------------------------------------------------------------------------
# get_available_projects
# ---------------------------------------------------------------------------


class TestGetAvailableProjects:
    def test_returns_unique_sorted(self, tmp_path: Path) -> None:
        from scripts.observatory.data.filters import get_available_projects
        t1 = _transcript(tmp_path / "proj-b" / "s1.jsonl", "s1")
        t2 = _transcript(tmp_path / "proj-a" / "s2.jsonl", "s2")
        t3 = _transcript(tmp_path / "proj-b" / "s3.jsonl", "s3")  # duplicate
        assert get_available_projects([t1, t2, t3]) == ["proj-a", "proj-b"]

    def test_empty_returns_empty(self) -> None:
        from scripts.observatory.data.filters import get_available_projects
        assert get_available_projects([]) == []


# ---------------------------------------------------------------------------
# get_available_sessions
# ---------------------------------------------------------------------------


class TestGetAvailableSessions:
    def test_all_sessions_when_no_project(self, tmp_path: Path) -> None:
        from scripts.observatory.data.filters import get_available_sessions
        t1 = _transcript(tmp_path / "proj-a" / "s1.jsonl", "s1")
        t2 = _transcript(tmp_path / "proj-b" / "s2.jsonl", "s2")
        assert get_available_sessions([t1, t2]) == ["s1", "s2"]

    def test_filtered_by_project(self, tmp_path: Path) -> None:
        from scripts.observatory.data.filters import get_available_sessions
        t1 = _transcript(tmp_path / "proj-a" / "s1.jsonl", "s1")
        t2 = _transcript(tmp_path / "proj-b" / "s2.jsonl", "s2")
        assert get_available_sessions([t1, t2], project="proj-a") == ["s1"]
