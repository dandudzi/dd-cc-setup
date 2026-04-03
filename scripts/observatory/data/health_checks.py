"""Health check definitions and persistence for Observatory.

A health check is a saved comparison between two tool categories on a specific
metric, with user-defined expected value and warning/error thresholds.

Storage: ~/.claude/observatory/health_checks.json
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

logger = logging.getLogger(__name__)
from typing import Literal


def _default_health_check_path() -> Path:
    """Return health checks path, respecting OBSERVATORY_HEALTH_DIR env override (used in E2E tests)."""
    override = os.environ.get("OBSERVATORY_HEALTH_DIR")
    if override:
        return Path(override) / "health_checks.json"
    return Path.home() / ".claude" / "observatory" / "health_checks.json"

# Sentinel used in category_a to request the aggregate (overall) value instead
# of a per-category value. Only valid for F2 absolute metrics.
OVERALL_CATEGORY = "_overall"

Metric = Literal[
    "input_delta",
    "content_ratio",
    "miss_rate",
    "miss_rate_delta",
    "mean_miss_tokens",
]
HealthCheckStatus = Literal["OK", "WARNING", "ERROR", "INSUFFICIENT"]


@dataclass(frozen=True)
class HealthCheck:
    """A saved comparison between two tool categories (or an absolute check)."""

    id: str
    name: str
    category_a: str
    category_b: str | None    # None → absolute check (single-category or overall)
    metric: Metric
    expected: float           # baseline value (auto-measured or user-defined)
    warning_threshold: float  # |actual - expected| <= this → OK
    error_threshold: float    # |actual - expected| <= this → WARNING, else ERROR
    created_at: str
    report: str               # which report owns this check; used for dashboard dispatch

    @staticmethod
    def create(
        name: str,
        category_a: str,
        metric: Metric,
        expected: float,
        warning_threshold: float,
        error_threshold: float,
        category_b: str | None = None,
        report: str = "f1_turn_cost",
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
            report=report,
        )


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def _backfill(item: dict) -> dict:  # type: ignore[type-arg]
    """Add missing fields from older JSON files for backward compatibility."""
    if "report" not in item:
        item = {**item, "report": "f1_turn_cost"}
    if "category_b" not in item:
        item = {**item, "category_b": None}
    return item


def load_health_checks(path: Path | None = None) -> list[HealthCheck]:
    """Load health checks from JSON. Returns [] when file does not exist or is corrupt."""
    p = path or _default_health_check_path()
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        logger.warning("health_checks: invalid JSON in %s — returning []: %s", p, exc)
        return []
    if not isinstance(data, list):
        logger.warning("health_checks: expected list in %s, got %s — returning []", p, type(data).__name__)
        return []
    results: list[HealthCheck] = []
    for i, item in enumerate(data):
        try:
            results.append(HealthCheck(**_backfill(item)))
        except Exception as exc:
            logger.warning("health_checks: skipping entry %d in %s — %s", i, p, exc)
    return results


def save_health_checks(checks: list[HealthCheck], path: Path | None = None) -> None:
    """Persist health checks to JSON atomically (write-then-rename)."""
    p = path or _default_health_check_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps([asdict(c) for c in checks], indent=2), encoding="utf-8")
    os.rename(tmp, p)


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
    *,
    a_miss_rate: float | None = None,
    b_miss_rate: float | None = None,
    a_mean_miss_tokens: float | None = None,
) -> float | None:
    """Derive the scalar value for a metric from per-category stats.

    F1 metrics use a_input / a_content / b_input / b_content.
    F2 metrics use a_miss_rate / b_miss_rate / a_mean_miss_tokens / b_mean_miss_tokens.
    For absolute checks, the 'b_*' args are ignored; a_* carries the single value.
    OVERALL_CATEGORY callers should pass the overall aggregate in the a_* slot.

    Returns:
        float value, or None when required data is missing.
    """
    if metric == "input_delta":
        if a_input is None or b_input is None:
            return None
        return a_input - b_input

    if metric == "content_ratio":
        if a_content is None or b_content is None:
            return None
        if a_content == 0.0:
            return None
        return b_content / a_content

    if metric == "miss_rate":
        # Absolute: a_miss_rate holds the value (per-category or overall).
        return a_miss_rate  # None propagates naturally

    if metric == "miss_rate_delta":
        if a_miss_rate is None or b_miss_rate is None:
            return None
        return a_miss_rate - b_miss_rate

    # mean_miss_tokens — absolute: a_mean_miss_tokens holds the value.
    return a_mean_miss_tokens
