"""Shared navigation and persistent run context for the scientific discovery lab."""

import streamlit as st

from hacknation_databricks.tracking_ui import CSS, markup, render_sidebar

st.set_page_config(
    page_title="Omnigent · Scientific discovery lab",
    page_icon="◈",
    layout="wide",
    initial_sidebar_state="expanded",
)
markup(CSS)
page = st.navigation(
    {
        "Research": [
            st.Page(
                "app_pages/sources.py",
                title="Source intake",
                icon=":material/library_books:",
                default=True,
            ),
            st.Page(
                "app_pages/overview.py",
                title="Discovery overview",
                icon=":material/science:",
            ),
            st.Page("app_pages/agents.py", title="Agents & loops", icon=":material/account_tree:"),
            st.Page(
                "app_pages/comparison.py",
                title="Original → follow-up",
                icon=":material/compare_arrows:",
            ),
            st.Page("app_pages/synthesis.py", title="Final synthesis", icon=":material/insights:"),
        ],
        "Audit": [
            st.Page(
                "app_pages/evidence.py", title="Generated artifacts", icon=":material/inventory_2:"
            ),
        ],
    },
    position="sidebar",
)
render_sidebar()
page.run()
