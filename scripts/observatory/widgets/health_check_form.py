"""Shared health check widget for Observatory reports.

Renders a Saved Health Checks expander section with edit/delete functionality.
Used by dashboard.py, F1 report, and F2 report.
"""
from __future__ import annotations

from typing import Callable

import streamlit as st

from scripts.observatory.data.health_checks import (
    OVERALL_CATEGORY,
    HealthCheck,
    compute_status,
    load_health_checks,
    remove_health_check,
    save_health_checks,
    update_health_check,
)


_STATUS_COLOR = {
    "OK":           "🟢",
    "WARNING":      "🟡",
    "ERROR":        "🔴",
    "INSUFFICIENT": "⚪",
}


def render_saved_checks(
    report_id: str | None,
    health_checks: list[HealthCheck],
    eval_fn: Callable[[HealthCheck], tuple[float | None, str, str]],
    expanded: bool = False,
) -> None:
    """Render the Saved Health Checks expander section.

    Args:
        report_id: The report this widget is rendering for (e.g., "f1_turn_cost", "f2_cache_miss").
                   If None, display all checks (used by dashboard). Otherwise filter by hc.report == report_id.
        health_checks: Full list of all saved health checks from load_health_checks().
        eval_fn: Callable that evaluates a single HealthCheck and returns (actual_value, status_string, samples_string).
                 The status_string must be one of: "OK", "WARNING", "ERROR", "INSUFFICIENT".
                 Example: eval_fn(hc) -> (0.1234, "OK", "1234 samples")
        expanded: Whether to expand the expander by default (default False). Dashboard uses True.
    """
    # Filter to checks matching this report (or all if report_id is None)
    if report_id is None:
        related = health_checks
        label = f"{len(related)} health check{'s' if len(related) != 1 else ''}"
    else:
        related = [hc for hc in health_checks if hc.report == report_id]
        label = f"Saved Health Checks ({len(related)})"
    with st.expander(label, expanded=expanded):
        if not related:
            st.info("No health checks saved for this report yet.")
        else:
            for hc in related:
                # Evaluate the health check
                actual, status, samples = eval_fn(hc)
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
