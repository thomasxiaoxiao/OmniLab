"""Concise run outcomes with the original assessment retained for inspection."""

import streamlit as st

from hacknation_databricks.tracking import Journal


def render_run_outcome(journal: Journal) -> None:
    status = journal.report.get("status")
    if status == "unsupported_source":
        st.info(
            "No compatible experiment is available for this paper. "
            "This run stopped before simulation."
        )
        st.caption(
            "To continue, choose a paper that matches an available experiment, "
            "or add and validate an experiment tool for this research question."
        )
        details_label = "Why this run stopped · saved agent assessment"
    elif status == "blocked_live_backend":
        st.warning("This run stopped because the agent runtime could not complete a request.")
        st.caption(
            "Check the Omnigent connection before starting a new run. Saved work is retained."
        )
        details_label = "Why this run stopped · runtime details"
    elif status == "running" or not status:
        st.info(
            "Experiment still running · agent activity and produced artifacts update automatically."
        )
        return
    elif not journal.sealed:
        st.info("Execution ended · saving and verifying the final artifacts.")
        return
    elif status in {"goal_achieved", "candidate_discovery"}:
        st.success("Experiment finished · the scoped research goal was reached.")
        return
    else:
        st.warning(
            f"Experiment finished · {status.replace('_', ' ')}. Saved results remain available."
        )
        details_label = "Recorded stopping reason"
    reason = journal.report.get("reason")
    if reason:
        with st.expander(details_label, expanded=False):
            st.caption(f"Recorded in report.json · run {journal.run_id}")
            st.text(reason)
