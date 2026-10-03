import streamlit as st

from hacknation_databricks.synthesis_ui import render_synthesis
from hacknation_databricks.tracking_ui import selected_journal

st.title("Final synthesis")
st.caption("Two connected views: what the simulations show, and which papers shaped the research.")
journal = selected_journal()
if journal:
    render_synthesis(journal)
