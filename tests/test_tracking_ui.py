import json
from pathlib import Path

from fixture_roles import run_fixture as run_research
from view_test import ViewTest

from hacknation_databricks.research.cli import fixture_source as default_source
from hacknation_databricks.research.models import RunConfig
from hacknation_databricks.research.sources import read_source
from hacknation_databricks.tracking_ui import launch_run

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "src/hacknation_databricks/ui.py"
TRACKING = ROOT / "src/hacknation_databricks/tracking_ui.py"


def test_main_entry_shows_empty_control_room(monkeypatch, tmp_path):
    monkeypatch.setenv("RESEARCH_RUNS_DIR", str(tmp_path))
    monkeypatch.setenv("APP_REVISION", "tracking-test")
    app = ViewTest.from_file(str(UI)).run(timeout=15)
    assert not app.exception
    assert app.title[0].value == "Source intake"
    assert not any(s.label == "Research example" for s in app.selectbox)
    assert any(
        item.value == "Research prototype · scientific conclusions require further validation."
        for item in app.caption
    )
    assert any("tracking-test" in item.value for item in app.caption)
    assert not app.text_area


def test_run_button_journal_filter_and_reload(monkeypatch, tmp_path):
    # Exercise historical archive rendering with an explicitly test-only engine.
    from legacy.workflow import run_research as historical_fixture

    monkeypatch.setattr("hacknation_databricks.tracking_ui.run_research", historical_fixture)
    from fixture_roles import DecisionWorkerFixture

    from hacknation_databricks.research import decision_roles
    from hacknation_databricks.research.cli import fixture_source

    monkeypatch.setattr(decision_roles, "DecisionProcess", DecisionWorkerFixture)
    monkeypatch.setenv("RESEARCH_PAPER_PATH", str(fixture_source()))
    monkeypatch.setenv("RESEARCH_RUNS_DIR", str(tmp_path))
    monkeypatch.delenv("OMNIGENT_SERVER_URL", raising=False)
    app = ViewTest.from_file(str(UI)).run(timeout=15)
    app.switch_page("app_pages/sources.py").run()
    launch_run(fixture_source(), "Quick verification", "anyjev", lambda _: None)
    app.run(timeout=30)
    assert not app.exception
    runs = list(tmp_path.glob("*/report.json"))
    assert len(runs) == 1
    assert json.loads(runs[0].read_text())["backend"] == "anyjev"
    app.switch_page("app_pages/evidence.py").run()
    app.segmented_control[0].set_value("Decisions").run()
    assert len([e for e in app.expander if e.label.startswith("Inspect D-")]) == 7
    next(s for s in app.selectbox if s.label == "Show").select("Needs attention").run()
    assert len([e for e in app.expander if e.label.startswith("Inspect D-")]) == 1
    assert not app.exception
    app.text_input[0].set_value("no-matching-evidence").run()
    assert any("No decisions match" in item.value for item in app.info)
    fresh = ViewTest.from_file(str(UI)).run(timeout=15)
    fresh.switch_page("app_pages/evidence.py").run()
    fresh.segmented_control[0].set_value("Decisions").run()
    assert not fresh.exception
    assert len([e for e in fresh.expander if e.label.startswith("Inspect D-")]) == 7


def test_corrupt_run_is_quarantined_without_crashing(monkeypatch, tmp_path):
    monkeypatch.setenv("RESEARCH_RUNS_DIR", str(tmp_path))
    directory = tmp_path / "bad-run"
    run_research(
        read_source(default_source()),
        directory,
        RunConfig(sizes=[8, 16], trials=32, max_seconds=60),
    )
    (directory / "proposals.json").write_text('{"proposals": []}')
    app = ViewTest.from_file(str(UI)).run(timeout=15)
    app.switch_page("app_pages/overview.py").run()
    assert not app.exception
    assert any("quarantined" in item.value for item in app.error)
    assert not app.tabs


def test_launch_boundary_rejects_unregistered_input(monkeypatch, tmp_path):
    import pytest

    monkeypatch.setenv("RESEARCH_RUNS_DIR", str(tmp_path / "runs"))
    with pytest.raises(ValueError, match="registered"):
        launch_run(tmp_path / "arbitrary.txt", "Quick verification", "scripted", lambda _: None)
    monkeypatch.setenv("RESEARCH_PAPER_PATH", str(default_source()))
    with pytest.raises(ValueError, match="profile"):
        launch_run(default_source(), "unlimited", "scripted", lambda _: None)
    assert not (tmp_path / "runs").exists()
