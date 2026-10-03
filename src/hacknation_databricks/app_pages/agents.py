import streamlit as st

from hacknation_databricks.activity_ui import render_activity, render_artifact_feed
from hacknation_databricks.tracking_ui import selected_journal

st.title("Agents & execution loops")


@st.fragment(run_every=5)
def live_execution():
    journal = selected_journal("Agents", compact=True)
    if journal:
        render_artifact_feed(journal)
        render_activity(journal)


live_execution()
