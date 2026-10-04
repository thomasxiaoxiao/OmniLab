"""Concise run outcomes with the original assessment retained for inspection."""

from hacknation_databricks.tracking import Journal
from hacknation_databricks.web import components as ui


def render_run_outcome(journal: Journal) -> None:
    status = journal.report.get("status")
    if status == "repository_required":
        ui.info(
            "Add the paper's GitHub repository in Source intake to run a source-based experiment."
        )
        return
    elif status == "unsupported_source":
        ui.info(
            "No compatible experiment is available for this paper. "
            "This run stopped before simulation."
        )
        ui.caption(
            "To continue, choose a paper that matches an available experiment, "
            "or add and validate an experiment tool for this research question."
        )
        details_label = "Why this run stopped · saved agent assessment"
    elif status == "visualization_incomplete":
        ui.warning("Final output is incomplete: the required simulated-world comparison failed.")
        ui.caption(
            "Saved scientific results remain available. Add or repair the process adapter "
            "and validate it before a new run can complete."
        )
        details_label = "Missing process visualization"
    elif status == "blocked_live_backend":
        ui.warning("This run stopped because the agent runtime could not complete a request.")
        ui.caption(
            "Check the Omnigent connection before starting a new run. Saved work is retained."
        )
        details_label = "Why this run stopped · runtime details"
    elif status == "running" or not status:
        ui.info(
            "Experiment still running · agent activity and produced artifacts update automatically."
        )
        return
    elif not journal.sealed:
        ui.info("Execution ended · saving and verifying the final artifacts.")
        return
    elif status in {"goal_achieved", "candidate_discovery"}:
        ui.success("Experiment finished · the scoped research goal was reached.")
        return
    else:
        ui.warning(
            f"Experiment finished · {status.replace('_', ' ')}. Saved results remain available."
        )
        details_label = "Recorded stopping reason"
    reason = journal.report.get("reason")
    if reason:
        with ui.expander(details_label, expanded=False):
            ui.caption(f"Recorded in report.json · run {journal.run_id}")
            ui.text(reason)
