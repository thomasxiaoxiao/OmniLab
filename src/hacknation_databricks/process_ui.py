"""Shared simulation player for final synthesis and checkpoint comparisons."""

import json
from pathlib import Path

from hacknation_databricks.web import components as ui

from .research.artifacts import code_digest
from .research.process_player import process_html
from .research.process_visualization import build_process, checked_process
from .research_views import saved_json
from .tracking import read_artifact


@ui.cache_data(max_entries=16, ttl=120, show_spinner=False)
def _historical_process(bundle_json, directory, manifest_fingerprint, renderer_revision):
    return build_process(
        json.loads(bundle_json),
        lambda name: read_artifact(Path(directory), name),
        run_id=Path(directory).name,
    )


def render_process(journal, bundle):
    ui.markdown("### Original and proposed worlds · simulated process")
    if journal.sealed and not journal.verified:
        ui.error("The saved run failed verification; its process visualization cannot be trusted.")
        return
    checkpoint = bundle["checkpoint"]
    prefix = f"comparisons/{checkpoint:03d}" if checkpoint is not None else "comparison"
    saved = saved_json(journal, prefix + "/process.json")
    historical = saved is None and "output_contract" not in journal.report
    if historical:
        saved = _historical_process(
            json.dumps(bundle, sort_keys=True),
            str(journal.directory),
            json.dumps(journal.artifacts, sort_keys=True),
            code_digest(),
        )
    saved = saved or {"status": "unavailable", "reason": "Process output has not been saved yet."}
    if saved.get("status") != "ready":
        ui.warning("Process visualization incomplete: " + saved.get("reason", "Invalid output."))
        ui.caption("A summary chart cannot satisfy the simulated-world output requirement.")
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
    if historical:
        ui.caption(
            "Reconstructed view from archived inputs using the current renderer. "
            "The sealed historical run is unchanged; this is not a new scientific result."
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
