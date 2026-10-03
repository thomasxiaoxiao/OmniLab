import streamlit as st

from hacknation_databricks.synthesis_ui import render_comparison_page
from hacknation_databricks.tracking_ui import selected_journal

st.title("Original → follow-up")
journal = selected_journal()
if journal:
    render_comparison_page(journal)
