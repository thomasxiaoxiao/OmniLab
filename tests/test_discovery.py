"""V3 orchestration decisions must change execution, not only presentation."""

import json

import pytest
from fixture_roles import FixtureRoles
from legacy.workflow import run_research

from hacknation_databricks.research.cli import fixture_source
from hacknation_databricks.research.models import RunConfig
from hacknation_databricks.research.sources import read_source
from hacknation_databricks.tracking import load_journal


class PrecisionRoles(FixtureRoles):
    name = "omnigent"

    def _respond(self, role, payload):
        result = super()._respond(role, payload)
        if role == "critic":
            result["selected_proposal_id"] = payload["proposals"][-1]["id"]
        if role == "planner":
            assert len(payload["test_options"]) == 2
            result["selected_test_id"] = "precision"
        if role == "next_decision":
            assert payload["effect"]["checks"]
            result["action"] = "stop"
        return result


def test_selection_precision_and_stop_are_executed(tmp_path):
    root = tmp_path / "run"
    report = run_research(
        read_source(fixture_source()),
        root,
        RunConfig(sizes=[8, 16], trials=32),
        roles_factory=PrecisionRoles,
    )
    assert report["backend"] == "omnigent"
    assert report["selected_proposal"]["id"] == "resistor_diode"
    assert report["rounds"][0]["trials_per_size"] == 64
    assert len(report["rounds"]) == 1
    assert report["status"] == "research_stopped"
    assert report["next_decision"]["action"] == "stop"
    assert report["acceleration"]["multiplier"] is None
    assert not report["acceptance"]["live_agents_executed"]  # test double
    journal = load_journal(root)
    assert journal.verified, journal.issues


def test_unaffordable_precision_test_stops_before_followup(tmp_path):
    root = tmp_path / "run"
    report = run_research(
        read_source(fixture_source()),
        root,
        RunConfig(sizes=[8, 16], trials=32, max_simulations=280),
        roles_factory=PrecisionRoles,
    )
    assert report["status"] == "budget_exhausted"
    assert not report["acceptance"]["followup_implemented"]
    assert not (root / "rounds/01/trials.csv").exists()


def test_duplicate_test_comparison_is_rejected(tmp_path):
    class Invalid(PrecisionRoles):
        def _respond(self, role, payload):
            result = super()._respond(role, payload)
            if role == "planner":
                result["tests"][1] = result["tests"][0]
            return result

    with pytest.raises(ValueError, match="exactly once"):
        run_research(
            read_source(fixture_source()),
            tmp_path / "run",
            RunConfig(sizes=[8, 16], trials=32),
            roles_factory=Invalid,
        )
    assert json.loads((tmp_path / "run/report.json").read_text())["status"] == "failed"


def test_discovery_frontend_shows_actual_choice_and_next_action(tmp_path, monkeypatch):
    from pathlib import Path

    from view_test import ViewTest

    run_research(
        read_source(fixture_source()),
        tmp_path / "run",
        RunConfig(sizes=[8, 16], trials=32),
        roles_factory=PrecisionRoles,
    )
    monkeypatch.setenv("RESEARCH_RUNS_DIR", str(tmp_path))
    ui = Path(__file__).resolve().parents[1] / "src/hacknation_databricks/ui.py"
    app = ViewTest.from_file(str(ui)).run(timeout=15)
    assert not app.exception
    app.switch_page("app_pages/overview.py").run()
    assert app.title[0].value == "Discovery overview"
    assert any("Supervisor action: stop" in item.value for item in app.markdown)
    assert any(
        metric.label == "Acceleration multiplier" and metric.value == "Unverified"
        for metric in app.metric
    )
    assert not app.error


def test_repeat_recommendation_cannot_override_missing_literature(tmp_path):
    class RepeatRoles(PrecisionRoles):
        def _respond(self, role, payload):
            result = super()._respond(role, payload)
            if role == "next_decision":
                result["action"] = "repeat"
            return result

    report = run_research(
        read_source(fixture_source()),
        tmp_path / "run",
        RunConfig(sizes=[8, 16], trials=32),
        roles_factory=RepeatRoles,
    )
    assert report["status"] == "needs_literature_review"
    transition = report["rounds"][0]["transition"]
    assert transition["requested_action"] == "repeat"
    assert transition["applied_action"] == "literature"
    journal = load_journal(tmp_path / "run")
    assert journal.verified, journal.issues
