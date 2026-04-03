"""Cache Miss Distribution — Streamlit page.

Shows the distribution of cache misses across tool categories.
Cache misses are structural (context window changes), not caused by tool choice.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

from scripts.observatory.data.filters import FilterSpec, get_available_projects, get_available_sessions
from scripts.observatory.data.health_checks import (
    OVERALL_CATEGORY,
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
from scripts.observatory.reports.f2_cache_miss.compute import CacheMissStats, compute_cache_miss, table_height
from scripts.observatory.widgets.health_check_form import render_saved_checks

_CATEGORY_KEYS = list(CATEGORIES.keys())
_STATUS_COLOR = {
    "OK":           "🟢",
    "WARNING":      "🟡",
    "ERROR":        "🔴",
    "INSUFFICIENT": "⚪",
}
_ABS_METRIC_LABELS = {
    "miss_rate":        "Miss rate  (single value)",
    "mean_miss_tokens": "Mean miss tokens  (single value)",
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


if load_btn or "f2_api_calls" not in st.session_state:
    st.session_state["f2_api_calls"] = _load((
        tuple(spec.projects or []),
        tuple(spec.session_ids or []),
        str(spec.date_start),
        str(spec.date_end),
    ))

api_calls: list[ApiCall] = st.session_state.get("f2_api_calls", [])
session_ids = {c.session_id for c in api_calls if c.session_id}
st.sidebar.caption(f"{len(api_calls):,} turns · {len(session_ids):,} sessions")

# ---------------------------------------------------------------------------
# Page header
# ---------------------------------------------------------------------------

st.title("Cache Miss Distribution")

with st.expander("What is a cache miss?", expanded=False):
    st.markdown(
        """
Each API turn is classified into one of four cache categories based on
`cache_read_input_tokens` and `cache_creation_input_tokens`:

| Category | cache_read | cache_creation | Meaning |
|---|---|---|---|
| **Hit** | > 0 | 0 | Fully cached — no new write cost |
| **Partial** | > 0 | > 0 | Cache reuse + new write (most common, ~94% of turns) |
| **Miss** | 0 | > 0 | No cache benefit — full write cost |
| **None** | 0 | 0 | No caching at all (rare) |

**miss rate** = miss turns ÷ total single-tool turns for that category

**mean miss tokens** = average `cache_creation_input_tokens` across **miss turns only**
(where `cache_read == 0`) — not across all turns.

**Important**: Cache misses are **not caused by tool choice**. They are structural,
driven by context window changes (new turns, file snapshots, progress events).
This report shows *where* true misses land across tool categories.
        """
    )

if not api_calls:
    st.info("Click **Load Data** in the sidebar to begin.")
    st.stop()

# ---------------------------------------------------------------------------
# Compute
# ---------------------------------------------------------------------------

result = compute_cache_miss(api_calls)
stats: list[CacheMissStats] = result["stats"]
stats_by_cat = {s.category: s for s in stats}

# Migration warning: existing F2 health checks were calibrated to the old
# definition where miss_rate ≈ 100%. Warn if any look stale.
_f2_checks = [hc for hc in load_health_checks() if hc.report == "f2_cache_miss"]
_stale = [hc for hc in _f2_checks if hc.metric == "miss_rate" and hc.expected > 0.5]
if _stale:
    st.warning(
        "⚠ **Health check calibration needed.** "
        f"{len(_stale)} saved miss_rate health check(s) have `expected > 50%`, "
        "which was calibrated to the old definition (any cache write counted as a miss). "
        "The new definition counts only true misses (cache_read == 0). "
        "Please re-calibrate: open **Save as Health Check**, load fresh data, and save updated thresholds.",
        icon=None,
    )

# ---------------------------------------------------------------------------
# Category filter
# ---------------------------------------------------------------------------

st.divider()
selected_cats = st.multiselect(
    "Show categories",
    options=_CATEGORY_KEYS,
    default=_CATEGORY_KEYS,
)
visible_stats = [s for s in stats if s.category in selected_cats]

# ---------------------------------------------------------------------------
# Key metrics
# ---------------------------------------------------------------------------

m1, m2, m3, m4, m5 = st.columns(5)
m1.metric(
    "Hits",
    f"{result['overall_hit_turns']:,}",
    help="Turns where cache_read > 0 AND cache_creation == 0 — fully cached, no write cost.",
)
m2.metric(
    "Partial hits",
    f"{result['overall_partial_turns']:,}",
    help=(
        "Turns where cache_read > 0 AND cache_creation > 0 — cache reuse plus a new write. "
        "The most common case (~94% of turns in typical Claude Code sessions)."
    ),
)
m3.metric(
    "True misses",
    f"{result['overall_miss_turns']:,}",
    help=(
        "Turns where cache_read == 0 AND cache_creation > 0 — no cache benefit, full write cost. "
        "This is the expensive case. ~5% of turns in typical sessions."
    ),
)
m4.metric(
    "No caching",
    f"{result['overall_none_turns']:,}",
    help="Turns where both cache_read == 0 AND cache_creation == 0 — no caching at all (rare).",
)
m5.metric(
    "Miss rate",
    f"{result['overall_miss_rate']:.2%}",
    help=(
        "True misses ÷ single-tool turns. "
        "Unlike the old definition, this only counts turns where there was zero cache benefit "
        "(cache_read == 0). Partial hits are NOT counted as misses."
    ),
)

# ---------------------------------------------------------------------------
# Charts
# ---------------------------------------------------------------------------

st.divider()
col_left, col_right = st.columns(2)

with col_left:
    st.subheader("Cache status distribution by category")
    st.caption("Correlation only — tool choice does not cause cache misses.")
    dist_rows = [s for s in visible_stats if s.total_turns > 0]
    if dist_rows:
        dist_df = pd.DataFrame({
            "Category": [s.category for s in dist_rows],
            "Hit": [s.hit_turns for s in dist_rows],
            "Partial": [s.partial_turns for s in dist_rows],
            "Miss": [s.miss_turns for s in dist_rows],
            "None": [s.none_turns for s in dist_rows],
        }).set_index("Category")
        st.bar_chart(dist_df)
    else:
        st.caption("No data for selected categories.")

with col_right:
    st.subheader("Miss token volume by category")
    vol_df = pd.DataFrame({
        "Category": [s.category for s in visible_stats if s.miss_turns > 0],
        "Total miss tokens": [s.total_miss_tokens for s in visible_stats if s.miss_turns > 0],
    }).set_index("Category")
    if not vol_df.empty:
        st.bar_chart(vol_df)
    else:
        st.caption("No miss tokens in selected categories.")

# ---------------------------------------------------------------------------
# Per-category stats table
# ---------------------------------------------------------------------------

st.divider()
st.subheader("Per-category stats (single-tool turns only)")
rows = [
    {
        "Category": s.category,
        "Total turns": s.total_turns,
        "Hit": s.hit_turns,
        "Partial": s.partial_turns,
        "Miss": s.miss_turns,
        "None": s.none_turns,
        "Miss rate": f"{s.miss_rate:.2%}",
        "Mean miss tokens": round(s.mean_miss_tokens, 1) if s.miss_turns > 0 else "—",
        "Total miss tokens": s.total_miss_tokens,
        "TTL 5m tokens": s.ttl_5m_tokens,
        "TTL 1h tokens": s.ttl_1h_tokens,
    }
    for s in visible_stats
]
st.dataframe(
    pd.DataFrame(rows),
    use_container_width=True,
    hide_index=True,
    height=table_height(len(rows)),
    column_config={
        "Category": st.column_config.TextColumn(
            "Category ℹ",
            help="Tool category (e.g. Read, Bash, jCodeMunch).",
        ),
        "Total turns": st.column_config.NumberColumn(
            "Total turns ℹ",
            help="Single-tool turns attributed to this category.",
        ),
        "Hit": st.column_config.NumberColumn(
            "Hit ℹ",
            help="Turns where cache_read > 0 AND cache_creation == 0 — fully cached, no write cost.",
        ),
        "Partial": st.column_config.NumberColumn(
            "Partial ℹ",
            help="Turns where cache_read > 0 AND cache_creation > 0 — cache reuse plus a new write.",
        ),
        "Miss": st.column_config.NumberColumn(
            "Miss ℹ",
            help="Turns where cache_read == 0 AND cache_creation > 0 — no cache benefit, full write cost.",
        ),
        "None": st.column_config.NumberColumn(
            "None ℹ",
            help="Turns where cache_read == 0 AND cache_creation == 0 — no caching at all.",
        ),
        "Miss rate": st.column_config.TextColumn(
            "Miss rate ℹ",
            help="True miss turns ÷ total turns. Only counts turns with zero cache benefit (cache_read == 0).",
        ),
        "Mean miss tokens": st.column_config.TextColumn(
            "Mean miss tokens ℹ",
            help=(
                "Average cache_creation_input_tokens on true miss turns only. "
                "Higher means more tokens re-cached per miss turn for this category."
            ),
        ),
        "Total miss tokens": st.column_config.NumberColumn(
            "Total miss tokens ℹ",
            help="Sum of cache_creation_input_tokens across true miss turns for this category.",
        ),
        "TTL 5m tokens": st.column_config.NumberColumn(
            "TTL 5m tokens ℹ",
            help="Sum of ephemeral_5m_input_tokens (5-minute TTL cache writes) across all turns.",
        ),
        "TTL 1h tokens": st.column_config.NumberColumn(
            "TTL 1h tokens ℹ",
            help="Sum of ephemeral_1h_input_tokens (1-hour TTL cache writes) across all turns.",
        ),
    },
)

# ---------------------------------------------------------------------------
# Save as health check
# ---------------------------------------------------------------------------

st.divider()
with st.expander("Save as Health Check"):
    check_type = st.radio("Check type", ["Absolute", "Pairwise"], horizontal=True)

    if check_type == "Absolute":
        abs_cat_options = ["Overall"] + _CATEGORY_KEYS
        abs_cat = st.selectbox("Category", abs_cat_options)
        abs_metric = st.selectbox("Metric", list(_ABS_METRIC_LABELS.keys()),
                                  format_func=lambda x: _ABS_METRIC_LABELS[x])

        # Compute current actual value for default
        if abs_cat == "Overall":
            _cat_key = OVERALL_CATEGORY
            if abs_metric == "miss_rate":
                _default_actual: float = result["overall_miss_rate"]
                _has_abs_data = True
            else:
                _ct = result["overall_miss_tokens"]
                _cm = result["overall_miss_turns"]
                _has_abs_data = _cm > 0
                _default_actual = _ct / _cm if _has_abs_data else 0.0
        else:
            _s = stats_by_cat.get(abs_cat)
            if _s and _s.total_turns > 0:
                _has_abs_data = True
                if abs_metric == "miss_rate":
                    _default_actual = _s.miss_rate
                else:
                    _default_actual = _s.mean_miss_tokens
            else:
                _has_abs_data = False
                _default_actual = 0.0
            _cat_key = abs_cat

        if not _has_abs_data:
            st.warning("Insufficient data to calibrate — no turns for this category.")
        else:
            default_name = f"{abs_cat} — {_ABS_METRIC_LABELS[abs_metric].split('  ')[0]}"
            hc_name = st.text_input("Name", value=default_name, key="abs_name")

            c1, c2, c3 = st.columns(3)
            hc_expected = c1.number_input("Expected value", value=round(_default_actual, 6), format="%.6f")
            hc_warn = c2.number_input("Warning threshold (±)", value=0.005, format="%.6f")
            hc_err = c3.number_input("Error threshold (±)", value=0.015, format="%.6f")

            if st.button("Save Absolute Health Check", type="primary"):
                if not hc_name.strip():
                    st.error("Name is required.")
                elif hc_warn >= hc_err:
                    st.error("Warning threshold must be less than error threshold.")
                else:
                    hc = HealthCheck.create(
                        name=hc_name.strip(),
                        category_a=_cat_key,
                        category_b=None,
                        metric=abs_metric,
                        expected=hc_expected,
                        warning_threshold=hc_warn,
                        error_threshold=hc_err,
                        report="f2_cache_miss",
                    )
                    save_health_checks(add_health_check(load_health_checks(), hc))
                    st.success(f"Health check **{hc_name}** saved.")

    else:  # Pairwise
        col_a, col_b = st.columns(2)
        pair_a = col_a.selectbox("Category A", _CATEGORY_KEYS, index=0, key="pair_a")
        pair_b_opts = [c for c in _CATEGORY_KEYS if c != pair_a]
        pair_b = col_b.selectbox("Category B", pair_b_opts, index=0, key="pair_b")

        _sa = stats_by_cat.get(pair_a)
        _sb = stats_by_cat.get(pair_b)
        _has_pair_data = bool(_sa and _sb and _sa.total_turns > 0 and _sb.total_turns > 0)
        _actual_delta: float = (
            (_sa.miss_rate - _sb.miss_rate) if _has_pair_data else 0.0  # type: ignore[union-attr]
        )

        if not _has_pair_data:
            st.warning("Insufficient data to calibrate — one or both categories have no turns.")
        else:
            default_name_pair = f"{pair_a} vs {pair_b} — miss rate delta"
            hc_name_pair = st.text_input("Name", value=default_name_pair, key="pair_name")

            pc1, pc2, pc3 = st.columns(3)
            hc_exp_pair = pc1.number_input("Expected value", value=round(_actual_delta, 6), format="%.6f", key="pair_exp")
            hc_warn_pair = pc2.number_input("Warning threshold (±)", value=0.01, format="%.6f", key="pair_warn")
            hc_err_pair = pc3.number_input("Error threshold (±)", value=0.03, format="%.6f", key="pair_err")

            if st.button("Save Pairwise Health Check", type="primary"):
                if not hc_name_pair.strip():
                    st.error("Name is required.")
                elif hc_warn_pair >= hc_err_pair:
                    st.error("Warning threshold must be less than error threshold.")
                else:
                    hc = HealthCheck.create(
                        name=hc_name_pair.strip(),
                        category_a=pair_a,
                        category_b=pair_b,
                        metric="miss_rate_delta",
                        expected=hc_exp_pair,
                        warning_threshold=hc_warn_pair,
                        error_threshold=hc_err_pair,
                        report="f2_cache_miss",
                    )
                    save_health_checks(add_health_check(load_health_checks(), hc))
                    st.success(f"Health check **{hc_name_pair}** saved.")

# ---------------------------------------------------------------------------
# Related health checks for this report
# ---------------------------------------------------------------------------

st.divider()


def _eval_f2_check(hc: HealthCheck) -> tuple[float | None, str, str]:
    """Evaluate an F2 health check. Returns (actual, status, samples)."""
    # Compute current actual value
    if hc.metric == "miss_rate":
        if hc.category_a == OVERALL_CATEGORY:
            _a_rate = result["overall_miss_rate"]
        else:
            _s = stats_by_cat.get(hc.category_a)
            _a_rate = _s.miss_rate if _s and _s.total_turns > 0 else None
        _act = compute_actual_value(
            None, None, None, None, hc.metric,
            a_miss_rate=_a_rate,
        )
    elif hc.metric == "miss_rate_delta":
        _sa2 = stats_by_cat.get(hc.category_a or "")
        _sb2 = stats_by_cat.get(hc.category_b or "")
        _act = compute_actual_value(
            None, None, None, None, hc.metric,
            a_miss_rate=_sa2.miss_rate if _sa2 and _sa2.total_turns > 0 else None,
            b_miss_rate=_sb2.miss_rate if _sb2 and _sb2.total_turns > 0 else None,
        )
    elif hc.metric == "mean_miss_tokens":
        if hc.category_a == OVERALL_CATEGORY:
            _mt = result["overall_miss_tokens"]
            _mc = result["overall_miss_turns"]
            _a_mt = _mt / _mc if _mc > 0 else None
        else:
            _s3 = stats_by_cat.get(hc.category_a)
            _a_mt = _s3.mean_miss_tokens if _s3 and _s3.miss_turns > 0 else None
        _act = compute_actual_value(
            None, None, None, None, hc.metric,
            a_mean_miss_tokens=_a_mt,
        )
    else:
        _act = None

    _status = compute_status(hc, _act)
    _samples = f"{result['single_tool_turns']:,} turns"
    return _act, _status, _samples


render_saved_checks("f2_cache_miss", load_health_checks(), _eval_f2_check)
