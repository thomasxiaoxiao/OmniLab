import streamlit as st

from hacknation_databricks.activity_ui import render_activity
from hacknation_databricks.tracking_ui import selected_journal

st.title("Agents & execution loops")
st.caption("See which specialists ran, how work moved between them, and what they generated.")


@st.fragment(run_every=5)
def live_execution():
    journal = selected_journal()
    if journal:
        render_activity(journal)


live_execution()
