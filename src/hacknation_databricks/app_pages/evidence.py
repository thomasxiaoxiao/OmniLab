import streamlit as st

from hacknation_databricks.tracking_ui import (
    render_artifacts,
    render_environment,
    render_journal,
    selected_journal,
)

st.title("Generated artifacts")
st.caption("Inspect model outputs, simulation data, decisions and the source material behind them.")
journal = selected_journal("Evidence")
if journal:
    view = st.segmented_control(
        "Evidence view", ["Artifacts", "Decisions", "Environment"], default="Artifacts"
    )
    if view == "Artifacts":
        render_artifacts(journal)
    elif view == "Environment":
        render_environment(journal)
    elif journal.report.get("workflow_version") == "4":
        st.subheader("Investment decision journal")
        for c in reversed(journal.report.get("checkpoints", [])):
            with st.expander(f"Checkpoint {c['checkpoint']} · {c['decision']['action']}"):
                st.write(c["decision"]["result_interpretation"])
                st.write(c["decision"]["rationale"])
                st.json(c, expanded=False)
        st.download_button("Export decision ledger", journal.export(), file_name="decisions.json")
    else:
        render_journal(journal)
