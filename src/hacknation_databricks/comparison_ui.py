"""Present measured original/follow-up contrasts beside grounded agent assessments."""

import json
from pathlib import Path

from hacknation_databricks.research.comparison import synthesis_dataset
from hacknation_databricks.synthesis_ui import render_comparison_outputs
from hacknation_databricks.tracking import load_journal
from hacknation_databricks.web import components as ui


def render_comparison(directory: Path, report: dict) -> None:
    ui.subheader("Original → follow-up")
    ui.caption(
        "Same observable, recorded seeds, fixed parameters. "
        "Agent review is scoped to the saved references."
    )
    render_comparison_outputs(load_journal(directory), synthesis_dataset(report))
    selected = report.get("selected_proposal", {})
    if selected:
        ui.markdown(f"**{selected['title']}**")
        ui.write(selected["hypothesis"])
    if not report.get("rounds"):
        ui.info("The comparison appears once a follow-up and its evaluation finish.")
        return
    evaluation = report.get("automated_review")
    if not evaluation:
        ui.info(
            "This saved run predates the reference-grounded evaluator. "
            "No automated novelty verdict is available."
        )
        return
    ui.markdown(f"### Evaluator verdict: {evaluation['verdict'].replace('_', ' ')}")
    ui.write(evaluation["rationale"])
    sources = {s["source_id"]: s for s in json.loads((directory / "sources.json").read_text())}
    for index, comparison in enumerate(evaluation["comparisons"], 1):
        with ui.container(border=True):
            original, followup = ui.columns(2)
            original.markdown("**Original / prior work**")
            original.write(comparison["original_work"])
            followup.markdown("**This follow-up**")
            followup.write(comparison["followup_work"])
            ui.markdown(f"**Added value:** {comparison['added_value']}")
            with ui.expander(f"Evidence for comparison {index}"):
                for evidence in comparison["evidence"]:
                    source = sources[evidence["source_id"]]
                    ui.caption(
                        f"{source['title']} · page {evidence['page']} · {source['source_id']}"
                    )
                    ui.text(evidence["quote"])
                    if source.get("url", "").startswith("https://"):
                        ui.link_button("Open cited paper", source["url"])
    ui.markdown("**What remains unresolved**")
    for limitation in evaluation["limitations"]:
        ui.write(f"• {limitation}")
    ui.markdown("**Evaluator’s next experiment**")
    ui.write(evaluation["next_experiment"])
    path = directory / "reference_retrieval.json"
    if path.exists():
        retrieval = json.loads(path.read_text())
        with ui.expander("Reference coverage and retrieval audit"):
            ui.write(retrieval["scope"])
            ui.dataframe(retrieval["records"], hide_index=True)
    ui.download_button(
        "Download automated review",
        json.dumps(evaluation, indent=2),
        "novelty-review.json",
        "application/json",
    )
