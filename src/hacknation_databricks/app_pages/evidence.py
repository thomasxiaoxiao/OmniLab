"""React page view composition."""


def render():
    from hacknation_databricks.tracking_ui import (
        render_artifacts,
        render_environment,
        render_journal,
        selected_journal,
    )
    from hacknation_databricks.web import components as ui

    ui.title("Generated artifacts")
    ui.caption(
        "Inspect model outputs, simulation data, decisions and the source material behind them."
    )
    journal = selected_journal("Evidence")
    if journal:
        view = ui.segmented_control(
            "Evidence view", ["Artifacts", "Decisions", "Environment"], default="Artifacts"
        )
        if view == "Artifacts":
            render_artifacts(journal)
        elif view == "Environment":
            render_environment(journal)
        elif journal.report.get("workflow_version") == "4":
            ui.subheader("Investment decision journal")
            for c in reversed(journal.report.get("checkpoints", [])):
                with ui.expander(f"Checkpoint {c['checkpoint']} · {c['decision']['action']}"):
                    ui.write(c["decision"]["result_interpretation"])
                    ui.write(c["decision"]["rationale"])
                    ui.json(c, expanded=False)
            ui.download_button(
                "Export decision ledger", journal.export(), file_name="decisions.json"
            )
        else:
            render_journal(journal)
