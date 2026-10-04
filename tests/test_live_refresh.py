"""Live view lifecycle: saved events drive refreshes, including final sealing."""

import pytest
from fastapi.testclient import TestClient
from test_web_api import event, nodes
from view_test import ViewTest

from hacknation_databricks.research.artifacts import RunStore
from hacknation_databricks.research.models import RunConfig
from hacknation_databricks.web import components as ui
from hacknation_databricks.web import server


def live_fixture(directory):
    """UI-only fixture; no model execution or scientific result is claimed."""
    store = RunStore(directory)
    store.write("config.json", RunConfig().model_dump())
    store.write("environment.json", {})
    store.write("sources.json", [])
    report = {
        "workflow_version": "5",
        "workflow": "repository",
        "backend": "fixture",
        "status": "running",
        "rounds": [],
        "role_calls": 0,
        "computed_simulations": 0,
        "acceptance": {"followup_implemented": False},
    }
    store.write("report.json", report)
    store.event("stage_started", {"stage": "reader", "parents": []})
    return store, report


@pytest.mark.parametrize("terminal_status", ["research_stopped", "blocked_live_backend"])
def test_fresh_view_follows_appended_steps_until_final_seal(tmp_path, monkeypatch, terminal_status):
    monkeypatch.setenv("RESEARCH_RUNS_DIR", str(tmp_path))
    monkeypatch.setattr(server, "_sessions", {})
    store, report = live_fixture(tmp_path / "live-ui-fixture")
    with TestClient(server.app) as client:
        initial = client.get("/api/view?page=agents").json()
        assert initial["refresh"] == 5
        assert "research_future" not in next(iter(server._sessions.values())).state
        graph = next(n for n in nodes(initial) if n["type"] == "execution_graph")
        selected = graph["graph"]["selected"]
        # Inspecting an earlier step disables following, not live polling.
        inspected = event(client, initial, values={graph["widget"]: selected}).json()
        assert inspected["refresh"] == 5

        store.event("stage_completed", {"stage": "reader", "seconds": 1})
        store.event("stage_started", {"stage": "critic", "parents": ["reader"]})
        polled = client.get("/api/view").json()
        graph = next(n for n in nodes(polled) if n["type"] == "execution_graph")
        assert any("critic · running" in label for label in graph["graph"]["labels"].values())
        assert graph["graph"]["selected"] == selected
        assert polled["refresh"] == 5

        store.event("stage_completed", {"stage": "critic", "seconds": 1})
        report["status"] = terminal_status
        store.write("report.json", report)
        # Terminal report alone is not enough: final artifacts may still be writing.
        assert client.get("/api/view").json()["refresh"] == 5
        store.event("run_finished", {"status": terminal_status})
        store.seal()
        finished = client.get("/api/view").json()
        assert finished["refresh"] is None
        assert any("produced artifacts · saved run" in str(n.get("value")) for n in nodes(finished))
        assert not any(
            n["type"] == "error" and "quarantined" in n["value"] for n in nodes(finished)
        )
        graph = next(n for n in nodes(finished) if n["type"] == "execution_graph")
        assert all("completed" in label for label in graph["graph"]["labels"].values())


def test_sealing_during_render_still_requests_one_final_snapshot(tmp_path, monkeypatch):
    monkeypatch.setenv("RESEARCH_RUNS_DIR", str(tmp_path))
    run = tmp_path / "live-ui-fixture"
    run.mkdir()

    @ui.fragment(run_every=5)
    def render_live():
        sealed = (run / "manifest.json").exists()
        ui.text("Finished" if sealed else "Running")
        # A worker finishes after the view reads its snapshot.
        (run / "manifest.json").write_text("{}")

    app = ViewTest.from_function(render_live)
    app.session_state["run_selection"] = run.name
    app.run()
    assert app.text[0].value == "Running"
    assert app.snapshot["refresh"] == 5
    app.run()
    assert app.text[0].value == "Finished"
    assert app.snapshot["refresh"] is None
