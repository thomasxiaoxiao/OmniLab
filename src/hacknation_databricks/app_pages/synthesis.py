import streamlit as st

from hacknation_databricks.synthesis_ui import render_synthesis
from hacknation_databricks.tracking_ui import selected_journal

st.title("Final synthesis")
st.caption("The paper result, proposed simulation, measured evidence and next scientific decision.")
journal = selected_journal("Synthesis")
if journal:
    render_synthesis(journal)
