from pathlib import Path

from view_test import ViewTest


def test_demo_renders_notice_and_revision(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_REVISION", "abc123")
    monkeypatch.setenv("RESEARCH_OUTPUT_DIR", str(tmp_path))
    ui = Path(__file__).resolve().parents[1] / "src/hacknation_databricks/research_ui.py"
    result = ViewTest.from_file(str(ui)).run(timeout=15)
    assert not result.exception
    assert result.title[0].value == "Research & Validation Lab"
    assert (
        result.caption[0].value
        == "Research prototype · scientific conclusions require further validation."
    )
    assert result.caption[1].value == "Deployed revision: abc123"


def test_local_ui_run_renders_baseline_and_followup(monkeypatch, tmp_path):
    from fixture_roles import DecisionWorkerFixture

    from hacknation_databricks.research import decision_roles, decision_runtime
    from hacknation_databricks.research.cli import fixture_source

    monkeypatch.setattr(decision_roles, "DecisionProcess", DecisionWorkerFixture)
    monkeypatch.setattr(decision_runtime, "runtime_status", lambda: {"ready": True})
    monkeypatch.setenv("RESEARCH_PAPER_PATH", str(fixture_source()))
    monkeypatch.setenv("RESEARCH_OUTPUT_DIR", str(tmp_path))
    ui = Path(__file__).resolve().parents[1] / "src/hacknation_databricks/research_ui.py"
    result = ViewTest.from_file(str(ui)).run(timeout=15)
    next(s for s in result.selectbox if s.label == "Agent runner").select("anyjev").run()
    result.button[0].click().run(timeout=30)
    assert not result.exception
    assert result.metric[0].value == "Pass"
    assert result.metric[1].value == "Executed"
    assert result.metric[2].value == "Unverified"
    assert len(list(tmp_path.glob("*/report.json"))) == 1
