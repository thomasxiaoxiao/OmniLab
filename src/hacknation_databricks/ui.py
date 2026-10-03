"""App navigation; keep research results alongside the decision control room."""

import streamlit as st

st.navigation(
    [
        st.Page(
            "tracking_ui.py",
            title="Decision control room",
            icon=":material/account_tree:",
            default=True,
        ),
        st.Page("research_ui.py", title="Research results", icon=":material/science:"),
    ],
    position="top",
).run()
