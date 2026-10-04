"""React page view composition."""


def render():
    from hacknation_databricks.source_ui import render_source_progress
    from hacknation_databricks.tracking_ui import render_run_setup
    from hacknation_databricks.web import components as ui

    ui.title("Source intake")
    ui.caption("Choose the seed. Keep its evidence. Define a bounded local experiment.")
    render_run_setup()

    @ui.fragment(run_every=5)
    def live_workers():
        render_source_progress()

    live_workers()
