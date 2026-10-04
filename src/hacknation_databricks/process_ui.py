"""Shared simulation player for final synthesis and checkpoint comparisons."""

import json

from hacknation_databricks.web import components as ui

from .research.process_player import process_html
from .research.process_visualization import checked_process
from .research_views import saved_json


def render_process(journal, bundle):
    if journal.report.get("workflow_version") != "5":
        ui.info(
            "Historical preset experiment. Its saved artifacts remain available for "
            "audit; start a new run for an agent-designed simulation and "
            "visualization."
        )
        return
    ui.markdown("### Original and proposed worlds · simulated process")
    if journal.sealed and not journal.verified:
        ui.error("The saved run failed verification; its process visualization cannot be trusted.")
        return
    checkpoint = bundle["checkpoint"]
    prefix = f"comparisons/{checkpoint:03d}" if checkpoint is not None else "comparison"
    saved = saved_json(journal, prefix + "/process.json")
    saved = saved or {"status": "unavailable", "reason": "Process output has not been saved yet."}
    if saved.get("status") != "ready":
        ui.warning("Process visualization incomplete: " + saved.get("reason", "Invalid output."))
        return
    try:
        process = checked_process(saved["process"])
        graphic = process_html(process)
    except (ValueError, KeyError, TypeError):
        ui.error("The process artifact does not satisfy the visualization contract.")
        return
    # Regenerate from validated data and a trusted template. Never execute archived
    # HTML or any markup returned by an agent, paper, or uploaded source.
    ui.iframe(
        graphic, height="content", alt="Synchronized original and proposed simulated processes"
    )
    with ui.container(horizontal=True):
        ui.download_button(
            "Download playable simulation",
            graphic,
            file_name=f"{journal.run_id}-process.html",
            mime="text/html",
        )
        ui.download_button(
            "Download simulation states",
            json.dumps(saved, indent=2),
            file_name=f"{journal.run_id}-process.json",
            mime="application/json",
        )
