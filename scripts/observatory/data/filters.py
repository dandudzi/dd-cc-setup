"""Transcript filtering for the Observatory analysis tool.

Provides FilterSpec and functions to filter TranscriptFile lists by
project, session ID, and date range.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

from scripts.observatory.data.parser import TranscriptFile


@dataclass(frozen=True)
class FilterSpec:
    """Immutable filter parameters for transcript selection."""

    projects: list[str] | None = None     # None = all projects
    session_ids: list[str] | None = None  # None = all sessions
    date_start: date | None = None
    date_end: date | None = None


def project_from_path(path: Path) -> str:
    """Extract project name from a transcript path (parent directory name)."""
    return path.parent.name


def mtime_date(path: Path) -> date:
    """Return file modification date. Uses UTC noon to avoid tz edge cases."""
    ts = path.stat().st_mtime
    return datetime.fromtimestamp(ts, tz=timezone.utc).date()


def filter_transcripts(
    transcripts: list[TranscriptFile], spec: FilterSpec
) -> list[TranscriptFile]:
    """Return transcripts matching all criteria in spec."""
    result: list[TranscriptFile] = []
    for t in transcripts:
        if spec.projects is not None:
            if project_from_path(t.path) not in spec.projects:
                continue
        if spec.session_ids is not None:
            if t.session_id not in spec.session_ids:
                continue
        if spec.date_start is not None or spec.date_end is not None:
            try:
                mdate = mtime_date(t.path)
            except OSError:
                continue
            if spec.date_start is not None and mdate < spec.date_start:
                continue
            if spec.date_end is not None and mdate > spec.date_end:
                continue
        result.append(t)
    return result


def get_available_projects(transcripts: list[TranscriptFile]) -> list[str]:
    """Return sorted unique project names from transcript list."""
    return sorted({project_from_path(t.path) for t in transcripts})


def get_available_sessions(
    transcripts: list[TranscriptFile],
    project: str | None = None,
) -> list[str]:
    """Return sorted unique session IDs, optionally filtered to one project."""
    if project is not None:
        transcripts = [t for t in transcripts if project_from_path(t.path) == project]
    return sorted({t.session_id for t in transcripts})
