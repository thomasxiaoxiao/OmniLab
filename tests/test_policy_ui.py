from concurrent.futures import Future
from pathlib import Path

from view_test import ViewTest

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "src/hacknation_databricks/ui.py"


def test_next_run_policy_reaches_fixed_launch_and_redirects(monkeypatch, tmp_path, launch_source):
    from hacknation_databricks import tracking_ui

    monkeypatch.setenv("RESEARCH_RUNS_DIR", str(tmp_path))
    launched = []
    monkeypatch.setattr(
        tracking_ui, "launch_run", lambda *args, **kwargs: launched.append((args, kwargs))
    )

    class Executor:
        def submit(self, function, *args, **kwargs):
            function(*args, **kwargs)
            return Future()

    monkeypatch.setattr(tracking_ui, "background_executor", lambda: Executor())
    app = ViewTest.from_file(str(UI)).run(timeout=15)
    app.switch_page("app_pages/policies.py").run()
    assert not app.exception
    app.segmented_control[0].set_value("Next-run controls").run()
    app.selectbox(key="policy_profile").select("Standard exploration").run()
    next(n for n in app.number_input if n.label == "Agent request budget").set_value(40)
    next(b for b in app.button if b.label == "Save next-run policy").click().run()
    app.switch_page("app_pages/sources.py").run()
    assert next(n for n in app.number_input if n.label == "Agent request budget").value == 40
    assert not any(s.label == "Decision backend" for s in app.selectbox)
    next(b for b in app.button if b.label == "Start bounded run").click().run()
    assert launched[0][0][2] == "omnigent"
    assert launched[0][0][5]["max_agent_calls"] == 40
    assert launched[0][1]["run_name"] == app.session_state["research_active_run"]
    assert app.title[0].value == "Agents & execution loops"
    assert any("Run starting" in item.value for item in app.info)
    assert not app.exception


def test_saved_policy_evidence_is_read_only(monkeypatch, tmp_path):
    from test_adaptive import make_run

    make_run(tmp_path)
    monkeypatch.setenv("RESEARCH_RUNS_DIR", str(tmp_path))
    app = ViewTest.from_file(str(UI)).run(timeout=15)
    app.switch_page("app_pages/policies.py").run(timeout=15)
    assert not app.exception
    assert any(m.label == "Recorded Omnigent sessions" for m in app.metric)
    assert any("not attested" in c.value for c in app.caption)
    assert not app.number_input
    assert any("No Omnigent requests recorded" in i.value for i in app.info)
