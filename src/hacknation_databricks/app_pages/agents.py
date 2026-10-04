"""React page view composition."""


def render():
    from hacknation_databricks.activity_ui import render_activity, render_artifact_feed
    from hacknation_databricks.research_routes_ui import render_research_routes
    from hacknation_databricks.tracking_ui import selected_journal
    from hacknation_databricks.web import components as ui

    ui.title("Agents & execution loops")

    @ui.fragment(run_every=5)
    def live_execution():
        journal = selected_journal("Agents", compact=True)
        if journal:
            execution, routes, artifacts = ui.tabs(
                ["Live specialists", "Routes & decisions", "Artifacts"]
            )
            with execution:
                render_activity(journal)
            with routes:
                render_research_routes(journal)
            with artifacts:
                render_artifact_feed(journal)

    live_execution()
