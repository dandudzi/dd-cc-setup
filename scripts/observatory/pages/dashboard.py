"""Observatory — Dashboard.

Shows all saved health checks with their live status computed against
the currently loaded session data.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import streamlit as st

from scripts.observatory.data.filters import FilterSpec, get_available_projects, get_available_sessions
from scripts.observatory.data.health_checks import (
    OVERALL_CATEGORY,
    HealthCheck,
    compute_actual_value,
    compute_status,
    load_health_checks,
    remove_health_check,
    save_health_checks,
    update_health_check,
)
from scripts.observatory.data.parser import ApiCall, discover_transcripts
from scripts.observatory.data.transcript_loader import get_base_dir, load_api_calls
from scripts.observatory.reports.f1_turn_cost.compute import compute_turn_cost
from scripts.observatory.reports.f2_cache_miss.compute import compute_cache_miss
from scripts.observatory.widgets.health_check_form import render_saved_checks


_STATUS_COLOR = {
    "OK":           "🟢",
    "WARNING":      "🟡",
    "ERROR":        "🔴",
    "INSUFFICIENT": "⚪",
}

# ---------------------------------------------------------------------------
# Sidebar — filters
# ---------------------------------------------------------------------------

st.sidebar.title("Filters")


@st.cache_data(show_spinner=False)
def _all_transcripts() -> list:
    return discover_transcripts(get_base_dir())


all_tf = _all_transcripts()

selected_projects = st.sidebar.multiselect(
    "Projects",
    options=get_available_projects(all_tf),
    default=None,
    placeholder="All projects",
)
project_filter = selected_projects or None

selected_sessions = st.sidebar.multiselect(
    "Sessions",
    options=get_available_sessions(
        all_tf,
        project=selected_projects[0] if len(selected_projects) == 1 else None,
    ),
    default=None,
    placeholder="All sessions",
)
session_filter = selected_sessions or None

col1, col2 = st.sidebar.columns(2)
date_start = col1.date_input("From", value=None, format="YYYY-MM-DD")
date_end = col2.date_input("To", value=None, format="YYYY-MM-DD")

load_btn = st.sidebar.button("Load Data", type="primary", use_container_width=True)

# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

spec = FilterSpec(
    projects=project_filter,
    session_ids=session_filter,
    date_start=date_start if isinstance(date_start, date) else None,
    date_end=date_end if isinstance(date_end, date) else None,
)


@st.cache_data(show_spinner="Loading transcripts…")
def _load(spec_key: tuple) -> list[ApiCall]:  # noqa: ARG001
    return load_api_calls(spec)


if load_btn or "dash_api_calls" not in st.session_state:
    st.session_state["dash_api_calls"] = _load((
        tuple(spec.projects or []),
        tuple(spec.session_ids or []),
        str(spec.date_start),
        str(spec.date_end),
    ))

api_calls: list[ApiCall] = st.session_state.get("dash_api_calls", [])
session_ids = {c.session_id for c in api_calls if c.session_id}
st.sidebar.caption(f"{len(api_calls):,} turns · {len(session_ids):,} sessions")

# ---------------------------------------------------------------------------
# Report dispatch helpers
# ---------------------------------------------------------------------------


def _eval_f1_check(
    calls: list[ApiCall],
    hc: HealthCheck,
) -> tuple[float | None, str, str]:
    """Evaluate an F1 (turn cost) health check. Returns (actual, status, samples)."""
    cats = [hc.category_a]
    if hc.category_b is not None:
        cats.append(hc.category_b)
    result = compute_turn_cost(calls, cats)
    stats = result["stats"]
    sa = next((s for s in stats if s.category == hc.category_a), None)
    sb = next((s for s in stats if s.category == hc.category_b), None) if hc.category_b else None
    actual = compute_actual_value(
        sa.mean_input_tokens if sa and sa.n > 0 else None,
        sa.mean_content_length if sa else None,
        sb.mean_input_tokens if sb and sb.n > 0 else None,
        sb.mean_content_length if sb else None,
        hc.metric,
    )
    status = compute_status(hc, actual)
    n_a = sa.n if sa else 0
    n_b = sb.n if sb else 0
    samples = f"{n_a + n_b:,} turns"
    return actual, status, samples


def _eval_f2_check(
    calls: list[ApiCall],
    hc: HealthCheck,
) -> tuple[float | None, str, str]:
    """Evaluate an F2 (cache miss) health check. Returns (actual, status, samples)."""
    cats = []
    if hc.category_a != OVERALL_CATEGORY:
        cats.append(hc.category_a)
    if hc.category_b is not None and hc.category_b != OVERALL_CATEGORY:
        cats.append(hc.category_b)
    result = compute_cache_miss(calls, cats if cats else None)
    stats_by = {s.category: s for s in result["stats"]}

    if hc.metric == "miss_rate":
        if hc.category_a == OVERALL_CATEGORY:
            a_rate = result["overall_miss_rate"]
        else:
            s = stats_by.get(hc.category_a)
            a_rate = s.miss_rate if s and s.total_turns > 0 else None
        actual = compute_actual_value(None, None, None, None, hc.metric, a_miss_rate=a_rate)

    elif hc.metric == "miss_rate_delta":
        sa = stats_by.get(hc.category_a or "")
        sb = stats_by.get(hc.category_b or "")
        actual = compute_actual_value(
            None, None, None, None, hc.metric,
            a_miss_rate=sa.miss_rate if sa and sa.total_turns > 0 else None,
            b_miss_rate=sb.miss_rate if sb and sb.total_turns > 0 else None,
        )

    elif hc.metric == "mean_miss_tokens":
        if hc.category_a == OVERALL_CATEGORY:
            mt = result["overall_miss_tokens"]
            mc = result["overall_miss_turns"]
            a_mt: float | None = mt / mc if mc > 0 else None
        else:
            s = stats_by.get(hc.category_a)
            a_mt = s.mean_miss_tokens if s and s.miss_turns > 0 else None
        actual = compute_actual_value(
            None, None, None, None, hc.metric, a_mean_miss_tokens=a_mt
        )

    else:
        actual = None

    status = compute_status(hc, actual)
    samples = f"{result['single_tool_turns']:,} turns"
    return actual, status, samples


_REPORT_COMPUTE = {
    "f1_turn_cost": _eval_f1_check,
    "f2_cache_miss": _eval_f2_check,
}

# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

st.title("Dashboard")

with st.expander("Status Legend", expanded=False):
    st.markdown(
        "| Status | Meaning |\n"
        "|--------|----------|\n"
        "| 🟢 **OK** | Actual value is within the warning threshold of expected |\n"
        "| 🟡 **WARNING** | Actual value is between warning and error threshold |\n"
        "| 🔴 **ERROR** | Actual value exceeds the error threshold |\n"
        "| ⚪ **INSUFFICIENT** | Not enough data loaded to compute the metric |"
    )

health_checks = load_health_checks()

if not health_checks:
    st.info(
        "No health checks saved yet. "
        "Go to **Turn Cost Asymmetry** or **Cache Miss Distribution**, "
        "run a comparison, and click **Save as Health Check**."
    )
    st.stop()

# ---------------------------------------------------------------------------
# Health check grid
# ---------------------------------------------------------------------------

def _eval_dashboard_check(hc: HealthCheck) -> tuple[float | None, str, str]:
    """Evaluate a health check using the dashboard's live api_calls data."""
    if api_calls:
        eval_fn = _REPORT_COMPUTE.get(hc.report)
        if eval_fn is None:
            return None, "INSUFFICIENT", f"unknown report '{hc.report}'"
        actual, status, samples = eval_fn(api_calls, hc)
    else:
        actual = None
        status = "INSUFFICIENT"
        samples = "no data"
    return actual, status, samples


# Render with an optional warning if data is not loaded
_label = f"{len(health_checks)} health check{'s' if len(health_checks) != 1 else ''}"
with st.expander(_label, expanded=True):
    if not api_calls:
        st.warning("Load data from the sidebar to see live status.")
    for hc in health_checks:
        actual, status, samples = _eval_dashboard_check(hc)
        if api_calls and hc.report not in _REPORT_COMPUTE:
            st.warning(f"Unknown report type '{hc.report}' for health check '{hc.name}' — cannot evaluate.")
        actual_str = f"{actual:.4f}" if actual is not None else "—"

        badge = _STATUS_COLOR[status]
        _edit_key = f"hc_editing_{hc.id}"

        with st.container(border=True):
            head_col, edit_col, remove_col = st.columns([10, 1, 1])
            with head_col:
                st.markdown(f"### {badge} {hc.name}")
            with edit_col:
                if st.button("✏", key=f"hc_edit_{hc.id}", help="Edit this health check"):
                    st.session_state[_edit_key] = not st.session_state.get(_edit_key, False)
                    st.rerun()
            with remove_col:
                if st.button("✕", key=f"hc_rm_{hc.id}", help="Remove this health check"):
                    fresh_checks = load_health_checks()
                    save_health_checks(remove_health_check(fresh_checks, hc.id))
                    st.rerun()

            if st.session_state.get(_edit_key, False):
                with st.form(key=f"hc_form_{hc.id}"):
                    e_name = st.text_input("Name", value=hc.name)
                    ef1, ef2, ef3 = st.columns(3)
                    e_expected = ef1.number_input("Expected value", value=hc.expected, format="%.4f")
                    e_warn = ef2.number_input("Warning threshold (±)", value=hc.warning_threshold, format="%.4f")
                    e_err = ef3.number_input("Error threshold (±)", value=hc.error_threshold, format="%.4f")
                    save_col, cancel_col = st.columns([1, 5])
                    submitted = save_col.form_submit_button("Save", type="primary")
                    cancelled = cancel_col.form_submit_button("Cancel")

                if submitted:
                    if not e_name.strip():
                        st.error("Name is required.")
                    elif e_warn >= e_err:
                        st.error("Warning threshold must be less than error threshold.")
                    else:
                        import dataclasses
                        updated = dataclasses.replace(
                            hc,
                            name=e_name.strip(),
                            expected=e_expected,
                            warning_threshold=e_warn,
                            error_threshold=e_err,
                        )
                        fresh_checks = load_health_checks()
                        save_health_checks(update_health_check(fresh_checks, updated))
                        st.session_state.pop(_edit_key, None)
                        st.rerun()
                elif cancelled:
                    st.session_state.pop(_edit_key, None)
                    st.rerun()
            else:
                # Display row — handle optional category_b and OVERALL_CATEGORY sentinel
                cat_a_label = "Overall" if hc.category_a == OVERALL_CATEGORY else hc.category_a
                cat_b_label = (
                    "Overall" if hc.category_b == OVERALL_CATEGORY
                    else hc.category_b if hc.category_b
                    else "—"
                )
                c1, c2, c3, c4, c5 = st.columns(5)
                c1.metric("Category A", cat_a_label)
                c2.metric("Category B", cat_b_label)
                c3.metric("Metric", hc.metric.replace("_", " "))
                c4.metric("Actual", actual_str)
                c5.metric("Expected", f"{hc.expected:.4f}")

                st.caption(
                    f"Thresholds: warn ±{hc.warning_threshold:.4f} · error ±{hc.error_threshold:.4f} · "
                    f"{samples} · saved {hc.created_at}"
                )
