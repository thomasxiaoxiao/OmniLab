"""Present measured original/follow-up contrasts beside grounded agent assessments."""

import json
from pathlib import Path

import streamlit as st

from hacknation_databricks.research.comparison import synthesis_dataset
from hacknation_databricks.synthesis_ui import render_comparison_outputs
from hacknation_databricks.tracking import load_journal


def render_comparison(directory: Path, report: dict) -> None:
    st.subheader("Original → follow-up")
    st.caption(
        "Same observable, recorded seeds, fixed parameters. "
        "Agent review is scoped to the saved references."
    )
    render_comparison_outputs(load_journal(directory), synthesis_dataset(report))
    selected = report.get("selected_proposal", {})
    if selected:
        st.markdown(f"**{selected['title']}**")
        st.write(selected["hypothesis"])
    if not report.get("rounds"):
        st.info("The comparison appears once a follow-up and its evaluation finish.")
        return
    evaluation = report.get("automated_review")
    if not evaluation:
        st.info(
            "This saved run predates the reference-grounded evaluator. "
            "No automated novelty verdict is available."
        )
        return
    st.markdown(f"### Evaluator verdict: {evaluation['verdict'].replace('_', ' ')}")
    st.write(evaluation["rationale"])
    sources = {s["source_id"]: s for s in json.loads((directory / "sources.json").read_text())}
    for index, comparison in enumerate(evaluation["comparisons"], 1):
        with st.container(border=True):
            original, followup = st.columns(2)
            original.markdown("**Original / prior work**")
            original.write(comparison["original_work"])
            followup.markdown("**This follow-up**")
            followup.write(comparison["followup_work"])
            st.markdown(f"**Added value:** {comparison['added_value']}")
            with st.expander(f"Evidence for comparison {index}"):
                for evidence in comparison["evidence"]:
                    source = sources[evidence["source_id"]]
                    st.caption(
                        f"{source['title']} · page {evidence['page']} · {source['source_id']}"
                    )
                    st.text(evidence["quote"])
                    if source.get("url", "").startswith("https://"):
                        st.link_button("Open cited paper", source["url"])
    st.markdown("**What remains unresolved**")
    for limitation in evaluation["limitations"]:
        st.write(f"• {limitation}")
    st.markdown("**Evaluator’s next experiment**")
    st.write(evaluation["next_experiment"])
    path = directory / "reference_retrieval.json"
    if path.exists():
        retrieval = json.loads(path.read_text())
        with st.expander("Reference coverage and retrieval audit"):
            st.write(retrieval["scope"])
            st.dataframe(retrieval["records"], hide_index=True)
    st.download_button(
        "Download automated review",
        json.dumps(evaluation, indent=2),
        "novelty-review.json",
        "application/json",
    )
