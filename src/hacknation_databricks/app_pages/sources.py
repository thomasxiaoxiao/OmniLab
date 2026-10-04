import streamlit as st

from hacknation_databricks.source_ui import render_source_progress
from hacknation_databricks.tracking_ui import render_run_setup

st.title("Source intake")
st.caption("Choose the seed. Keep its evidence. Define a bounded local experiment.")
render_run_setup()


@st.fragment(run_every=5)
def live_workers():
    render_source_progress()


live_workers()
