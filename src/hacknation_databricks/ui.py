"""Thin demo entry point; domain functionality will be added independently."""

import os

import streamlit as st

st.set_page_config(page_title="Rental Housing Law Navigator", page_icon="🏠")
st.title("Rental Housing Law Navigator")
st.caption("Not legal advice.")
st.info("The work environment is ready. The housing-law pipeline is not implemented yet.")
st.markdown("Automated extraction → address lookup → change tracking")
st.caption(f"Deployed revision: {os.environ.get('APP_REVISION', 'development')}")
