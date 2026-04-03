"""Turn Cost Asymmetry — Streamlit page.

Pick any two tool categories, compare their per-turn token cost,
and optionally save the comparison as a tracked health check.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

from scripts.observatory.data.filters import FilterSpec, get_available_projects, get_available_sessions
from scripts.observatory.data.health_checks import (
    HealthCheck,
    add_health_check,
    compute_actual_value,
    compute_status,
    load_health_checks,
    save_health_checks,
)
from scripts.observatory.data.parser import ApiCall, discover_transcripts
from scripts.observatory.data.tool_categories import CATEGORIES
from scripts.observatory.data.transcript_loader import get_base_dir, load_api_calls
from scripts.observatory.reports.f1_turn_cost.compute import TurnCostStats, compute_turn_cost
from scripts.observatory.widgets.health_check_form import render_saved_checks

_CATEGORY_KEYS = list(CATEGORIES.keys())
_STATUS_COLOR = {
    "OK":           "🟢",
    "WARNING":      "🟡",
    "ERROR":        "🔴",
    "INSUFFICIENT": "⚪",
}
_METRIC_LABELS = {
    "input_delta": "Input token delta  (cat_a − cat_b)",
    "content_ratio": "Content size ratio  (cat_b ÷ cat_a)",
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


if load_btn or "tca_api_calls" not in st.session_state:
    st.session_state["tca_api_calls"] = _load((
        tuple(spec.projects or []),
        tuple(spec.session_ids or []),
        str(spec.date_start),
        str(spec.date_end),
    ))

api_calls: list[ApiCall] = st.session_state.get("tca_api_calls", [])
session_ids = {c.session_id for c in api_calls if c.session_id}
st.sidebar.caption(f"{len(api_calls):,} turns · {len(session_ids):,} sessions")

# ---------------------------------------------------------------------------
# Page header
# ---------------------------------------------------------------------------

st.title("Turn Cost Asymmetry")

with st.expander("How to read this report"):
    st.markdown(
        """
**What is a turn?**
Each time Claude calls a tool, that is one API turn. Token counts belong to
the entire turn — not to the individual tool call.

**mean input\\_tokens**
How many tokens Claude had to process as input on that turn. Includes the full
conversation history. Large tool responses inflate `input_tokens` on every
subsequent turn — smaller responses keep future turns cheaper.

**mean content\\_length**
Character-length of what the tool returned. This is the leading indicator:
large content now → higher input\\_tokens on every future turn.

**Why compare categories?**
A category with lower input\\_tokens *and* shorter content\\_length is cheaper
both immediately and cumulatively across the session.
        """
    )

if not api_calls:
    st.info("Click **Load Data** in the sidebar to begin.")
    st.stop()

# ---------------------------------------------------------------------------
# Category pickers
# ---------------------------------------------------------------------------

st.divider()
col_a, col_b, col_m = st.columns([2, 2, 3])

cat_a = col_a.selectbox("Category A", _CATEGORY_KEYS, index=0)
cat_b_options = [c for c in _CATEGORY_KEYS if c != cat_a]
cat_b = col_b.selectbox("Category B", cat_b_options, index=0)
metric = col_m.radio(
    "Metric",
    list(_METRIC_LABELS.keys()),
    format_func=lambda x: _METRIC_LABELS[x],
    horizontal=False,
)

# ---------------------------------------------------------------------------
# Compute
# ---------------------------------------------------------------------------

result = compute_turn_cost(api_calls, [cat_a, cat_b])
stats: list[TurnCostStats] = result["stats"]
stats_a = next(s for s in stats if s.category == cat_a)
stats_b = next(s for s in stats if s.category == cat_b)

actual = compute_actual_value(
    stats_a.mean_input_tokens if stats_a.n > 0 else None,
    stats_a.mean_content_length,
    stats_b.mean_input_tokens if stats_b.n > 0 else None,
    stats_b.mean_content_length,
    metric,
)

# ---------------------------------------------------------------------------
# Key metrics
# ---------------------------------------------------------------------------

st.divider()
m1, m2, m3, m4 = st.columns(4)
m1.metric(
    "Total turns",
    f"{result['total_turns']:,}",
    help="All API turns in the loaded data (single-tool and multi-tool combined).",
)
m2.metric(
    "Single-tool turns",
    f"{result['single_tool_turns']:,}",
    help=(
        "Turns where exactly one tool was called. "
        "Only these are used for per-category stats — multi-tool turns "
        "cannot be attributed to a single category."
    ),
)
m3.metric(
    "Single-tool %",
    f"{result['single_tool_fraction']:.1%}",
    help="Single-tool turns as a percentage of all turns.",
)
m4.metric(
    _METRIC_LABELS[metric],
    f"{actual:+.3f}" if actual is not None else "n/a",
    delta_color="inverse",
    help=(
        "Current value of the selected comparison metric between Category A and Category B. "
        "Positive means A > B, negative means A < B."
    ),
)

# ---------------------------------------------------------------------------
# Table + charts
# ---------------------------------------------------------------------------

st.divider()
st.subheader("Per-category stats (single-tool turns only)")

rows = [
    {
        "Category": s.category,
        "n": s.n,
        "mean input_tokens": round(s.mean_input_tokens, 1),
        "mean content_length": round(s.mean_content_length, 0) if s.mean_content_length is not None else None,
    }
    for s in stats
]
st.dataframe(
    pd.DataFrame(rows),
    use_container_width=True,
    hide_index=True,
    column_config={
        "Category": st.column_config.TextColumn(
            "Category ℹ",
            help="Tool category (e.g. Read, Bash, jCodeMunch).",
        ),
        "n": st.column_config.NumberColumn(
            "n ℹ",
            help="Number of single-tool turns attributed to this category.",
        ),
        "mean input_tokens": st.column_config.NumberColumn(
            "mean input_tokens ℹ",
            help=(
                "Average total input tokens per turn for this category "
                "(includes prompt, history, cached tokens, and tool definitions)."
            ),
        ),
        "mean content_length": st.column_config.NumberColumn(
            "mean content_length ℹ",
            help="Average character length of the tool result content returned on each turn.",
        ),
    },
)

# Plain-English interpretation
if actual is not None and stats_a.n > 0 and stats_b.n > 0:
    if metric == "input_delta":
        direction = "more" if actual > 0 else "fewer"
        st.info(
            f"**Input cost:** A **{cat_a}** turn processes **{abs(actual):.0f} {direction} input tokens** "
            f"on average than a **{cat_b}** turn "
            f"({stats_a.mean_input_tokens:.0f} vs {stats_b.mean_input_tokens:.0f}). "
            f"Over 100 turns that is ~{abs(actual) * 100:,.0f} extra tokens of context."
        )
    else:
        size_word = "smaller" if actual < 1 else "larger"
        st.info(
            f"**Response size:** **{cat_b}** responses are **{actual:.0%} the size** of {cat_a} responses "
            f"({stats_b.mean_content_length:.0f} vs {stats_a.mean_content_length:.0f} chars) — "
            f"{abs(1 - actual):.0%} {size_word}."
        )

col_left, col_right = st.columns(2)
with col_left:
    st.subheader("mean input_tokens")
    chart_df = pd.DataFrame({
        "Category": [s.category for s in stats if s.n > 0],
        "mean input_tokens": [round(s.mean_input_tokens, 1) for s in stats if s.n > 0],
    }).set_index("Category")
    if not chart_df.empty:
        st.bar_chart(chart_df)

with col_right:
    st.subheader("mean content_length")
    chart_df2 = pd.DataFrame({
        "Category": [s.category for s in stats if s.n > 0 and s.mean_content_length is not None],
        "mean content_length": [
            round(s.mean_content_length, 0)  # type: ignore[arg-type]
            for s in stats if s.n > 0 and s.mean_content_length is not None
        ],
    }).set_index("Category")
    if not chart_df2.empty:
        st.bar_chart(chart_df2)
    else:
        st.caption("No content_length data for selected categories.")

# ---------------------------------------------------------------------------
# Save as health check
# ---------------------------------------------------------------------------

st.divider()
with st.expander("Save as Health Check"):
    if actual is None:
        st.warning("Insufficient data to calibrate — load data and select two categories first.")
    else:
        default_name = f"{cat_a} vs {cat_b} — {_METRIC_LABELS[metric].split('  ')[0]}"
        hc_name = st.text_input("Name", value=default_name)

        default_expected = round(actual, 4)
        if metric == "input_delta":
            default_warn, default_err = 50.0, 150.0
        else:
            default_warn, default_err = 0.10, 0.25

        c1, c2, c3 = st.columns(3)
        hc_expected = c1.number_input("Expected value", value=default_expected, format="%.4f")
        hc_warn = c2.number_input("Warning threshold (±)", value=default_warn, format="%.4f",
                                   help="Distance from expected before a warning is raised")
        hc_err = c3.number_input("Error threshold (±)", value=default_err, format="%.4f",
                                  help="Distance from expected before an error is raised")

        if st.button("Save Health Check", type="primary"):
            if not hc_name.strip():
                st.error("Name is required.")
            elif hc_warn >= hc_err:
                st.error("Warning threshold must be less than error threshold.")
            else:
                hc = HealthCheck.create(
                    name=hc_name.strip(),
                    category_a=cat_a,
                    category_b=cat_b,
                    metric=metric,
                    expected=hc_expected,
                    warning_threshold=hc_warn,
                    error_threshold=hc_err,
                    report="f1_turn_cost",
                )
                checks = load_health_checks()
                save_health_checks(add_health_check(checks, hc))
                st.success(f"Health check **{hc_name}** saved. View it on the Dashboard.")

# ---------------------------------------------------------------------------
# Related health checks for this report
# ---------------------------------------------------------------------------

st.divider()


def _eval_f1_check(hc: HealthCheck) -> tuple[float | None, str, str]:
    """Evaluate an F1 health check. Returns (actual, status, samples)."""
    if not api_calls:
        return None, "INSUFFICIENT", "no data"
    _res = compute_turn_cost(api_calls, [hc.category_a, hc.category_b])
    _sts = _res["stats"]
    _sa = next(s for s in _sts if s.category == hc.category_a)
    _sb = next(s for s in _sts if s.category == hc.category_b)
    _act = compute_actual_value(
        _sa.mean_input_tokens if _sa.n > 0 else None,
        _sa.mean_content_length,
        _sb.mean_input_tokens if _sb.n > 0 else None,
        _sb.mean_content_length,
        hc.metric,
    )
    _status = compute_status(hc, _act)
    n_a = _sa.n if _sa else 0
    n_b = _sb.n if _sb else 0
    _samples = f"{n_a + n_b:,} turns"
    return _act, _status, _samples


render_saved_checks("f1_turn_cost", load_health_checks(), _eval_f1_check)
