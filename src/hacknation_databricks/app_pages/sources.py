import streamlit as st

from hacknation_databricks.source_ui import render_sources
from hacknation_databricks.tracking_ui import render_run_setup

st.title("Source intake")
st.caption("Choose the seed. Keep its evidence. Define a bounded local experiment.")
with st.expander("Import a paper · upload or arXiv", expanded=False):
    render_sources()
render_run_setup()
