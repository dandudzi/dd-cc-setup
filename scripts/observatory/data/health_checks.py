"""Health check definitions and persistence for Observatory.

A health check is a saved comparison between two tool categories on a specific
metric, with user-defined expected value and warning/error thresholds.

Storage: ~/.claude/observatory/health_checks.json
"""
from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Literal

_DEFAULT_PATH = Path.home() / ".claude" / "observatory" / "health_checks.json"

Metric = Literal["input_delta", "content_ratio"]
HealthCheckStatus = Literal["OK", "WARNING", "ERROR", "INSUFFICIENT"]


@dataclass(frozen=True)
class HealthCheck:
    """A saved comparison between two tool categories."""

    id: str
    name: str
    category_a: str
    category_b: str
    metric: Metric
    expected: float           # baseline value (auto-measured or user-defined)
    warning_threshold: float  # |actual - expected| <= this → OK
    error_threshold: float    # |actual - expected| <= this → WARNING, else ERROR
    created_at: str

    @staticmethod
    def create(
        name: str,
        category_a: str,
        category_b: str,
        metric: Metric,
        expected: float,
        warning_threshold: float,
        error_threshold: float,
    ) -> HealthCheck:
        return HealthCheck(
            id=str(uuid.uuid4()),
            name=name,
            category_a=category_a,
            category_b=category_b,
            metric=metric,
            expected=expected,
            warning_threshold=warning_threshold,
            error_threshold=error_threshold,
            created_at=date.today().isoformat(),
        )


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def load_health_checks(path: Path | None = None) -> list[HealthCheck]:
    """Load health checks from JSON. Returns [] when file does not exist."""
    p = path or _DEFAULT_PATH
    if not p.exists():
        return []
    data = json.loads(p.read_text(encoding="utf-8"))
    return [HealthCheck(**item) for item in data]


def save_health_checks(checks: list[HealthCheck], path: Path | None = None) -> None:
    """Persist health checks to JSON, creating parent directories as needed."""
    p = path or _DEFAULT_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps([asdict(c) for c in checks], indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Mutation helpers (return new lists — never mutate in place)
# ---------------------------------------------------------------------------


def add_health_check(checks: list[HealthCheck], new: HealthCheck) -> list[HealthCheck]:
    return [*checks, new]


def remove_health_check(checks: list[HealthCheck], check_id: str) -> list[HealthCheck]:
    return [c for c in checks if c.id != check_id]


def update_health_check(checks: list[HealthCheck], updated: HealthCheck) -> list[HealthCheck]:
    """Return a new list with the check matching updated.id replaced by updated."""
    return [updated if c.id == updated.id else c for c in checks]


# ---------------------------------------------------------------------------
# Status computation
# ---------------------------------------------------------------------------


def compute_status(check: HealthCheck, actual: float | None) -> HealthCheckStatus:
    """Compare actual value against expected + thresholds.

    Returns:
        INSUFFICIENT — actual is None (not enough data)
        OK           — |actual - expected| <= warning_threshold
        WARNING      — warning_threshold < |diff| <= error_threshold
        ERROR        — |diff| > error_threshold
    """
    if actual is None:
        return "INSUFFICIENT"
    diff = abs(actual - check.expected)
    if diff <= check.warning_threshold:
        return "OK"
    if diff <= check.error_threshold:
        return "WARNING"
    return "ERROR"


def compute_actual_value(
    a_input: float | None,
    a_content: float | None,
    b_input: float | None,
    b_content: float | None,
    metric: Metric,
) -> float | None:
    """Derive the scalar value for a metric from per-category stats.

    Args:
        a_input:   category_a mean_input_tokens
        a_content: category_a mean_content_length
        b_input:   category_b mean_input_tokens
        b_content: category_b mean_content_length
        metric:    which metric to compute

    Returns:
        float value, or None when required data is missing.
    """
    if metric == "input_delta":
        if a_input is None or b_input is None:
            return None
        return a_input - b_input
    # content_ratio
    if a_content is None or b_content is None:
        return None
    return b_content / a_content
