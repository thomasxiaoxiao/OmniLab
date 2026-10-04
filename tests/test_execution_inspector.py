from view_test import ViewTest


def test_simulation_inspector_shows_archived_code_and_csv(tmp_path):
    import json

    (tmp_path / "code").mkdir()
    (tmp_path / "code/simulation.py").write_text("# archived implementation\nx = 1\n")
    (tmp_path / "trials.csv").write_text("seed,value\n42,0.5\n43,0.7\n")
    (tmp_path / "implementation.json").write_text(
        json.dumps({"source_sha256": "paper-hash", "files": ["code/simulation.py"]})
    )

    def page(directory):
        from pathlib import Path
        from types import SimpleNamespace

        from hacknation_databricks.activity_ui import render_simulation
        from hacknation_databricks.tracking import Journal

        render_simulation(
            Journal(
                "test", Path(directory), sources=[{"source_id": "seed", "sha256": "paper-hash"}]
            ),
            SimpleNamespace(artifacts=["trials.csv"]),
        )

    app = ViewTest.from_function(page, args=(str(tmp_path),)).run()
    assert not app.exception
    assert any("archived implementation" in c.value for c in app.code)
    assert len(app.dataframe[0].value) == 2
    assert any("derived export" in c.value for c in app.caption)


def test_failed_connection_keeps_prompt_visible(tmp_path):
    import json

    from hacknation_databricks.research.artifacts import RunStore

    store = RunStore(tmp_path / "run")
    store.write(
        "roles/01-reader-request.json",
        {
            "prompt": json.dumps(
                {"instructions": "Read this exact archived paper.", "data": {}, "output_schema": {}}
            )
        },
    )
    store.event("stage_started", {"stage": "reader"})
    details = {
        "stage": "reader",
        "role": "reader",
        "backend": "omnigent",
        "call_id": "roles/01-reader",
    }
    store.event("agent_call_started", details)
    store.event("agent_call_failed", {**details, "error_type": "ConnectError"})

    def page(directory):
        from pathlib import Path

        from hacknation_databricks.activity_ui import render_activity
        from hacknation_databricks.tracking import Journal

        render_activity(Journal("test", Path(directory), report={"backend": "omnigent"}))

    app = ViewTest.from_function(page, args=(str(store.directory),)).run()
    assert not app.exception
    assert any("Could not connect" in e.value for e in app.error)
    assert any("Read this exact archived paper." in c.value for c in app.code)
    assert app.subheader[0].value == "Complete prompt, inputs and constraints"
    assert not any(s.label == "Inspect execution step" for s in app.selectbox)
    assert not any(s.value == "Worker assignment" for s in app.subheader)


def test_unavailable_server_stops_before_reference_retrieval(tmp_path, monkeypatch):
    import httpx
    import pytest

    from hacknation_databricks import tracking_ui
    from hacknation_databricks.research.intake import register_upload

    source = register_upload("paper.md", b"A saved paper with evidence.", tmp_path / "sources")
    monkeypatch.setattr(
        tracking_ui,
        "available_sources",
        lambda: {"paper": tmp_path / "sources" / source.sha256 / "source.md"},
    )
    monkeypatch.setenv("OMNIGENT_SERVER_URL", "http://127.0.0.1:6767")

    def unavailable(*args, **kwargs):
        raise httpx.ConnectError("private provider detail")

    monkeypatch.setattr(httpx, "get", unavailable)
    from pathlib import Path

    with pytest.raises(ValueError, match="Your uploaded paper is saved"):
        tracking_ui.launch_run(Path(source.path), "Quick verification", "omnigent", lambda _: None)
    assert Path(source.path).is_file()


def test_launch_error_survives_monitor_rerun():
    def page():
        from concurrent.futures import Future

        from hacknation_databricks.tracking_ui import render_launch_monitor
        from hacknation_databricks.web import components as ui

        if "initialized" not in ui.session_state:
            future = Future()
            future.set_exception(
                ValueError("Omnigent is unavailable. Your uploaded paper is saved.")
            )
            ui.session_state["research_future"] = future
            ui.session_state["initialized"] = True
        render_launch_monitor()

    app = ViewTest.from_function(page).run()
    assert not app.exception
    assert any("Your uploaded paper is saved" in e.value for e in app.error)
