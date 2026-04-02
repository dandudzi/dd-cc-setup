"""Observatory — Claude Code Token Economics Analysis Tool.

Run: uv run streamlit run scripts/observatory/app.py
"""
from __future__ import annotations

import streamlit as st

st.set_page_config(page_title="Observatory", layout="wide")

pg = st.navigation(
    [
        st.Page("pages/dashboard.py", title="Dashboard", default=True),
        st.Page("reports/f1_turn_cost/page.py", title="Turn Cost Asymmetry"),
    ],
    position="sidebar",
    expanded=True,
)
pg.run()
