"""React page view composition."""


def render():
    from hacknation_databricks.activity_ui import render_activity, render_artifact_feed
    from hacknation_databricks.tracking_ui import selected_journal
    from hacknation_databricks.web import components as ui

    ui.title("Agents & execution loops")

    @ui.fragment(run_every=5)
    def live_execution():
        journal = selected_journal("Agents", compact=True)
        if journal:
            render_artifact_feed(journal)
            render_activity(journal)

    live_execution()
