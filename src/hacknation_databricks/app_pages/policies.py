import streamlit as st

from hacknation_databricks.policy_ui import render_policy_draft, render_policy_evidence
from hacknation_databricks.tracking_ui import selected_journal

st.title("Omnigent & policies")
st.caption("Manage next-run boundaries and trace how specialist context governs recorded work.")
view = st.segmented_control(
    "Policy workspace", ["Recorded run", "Next-run controls"], default="Recorded run"
)
if view == "Next-run controls":
    render_policy_draft()
else:
    journal = selected_journal()
    if journal:
        render_policy_evidence(journal)
