import json

import pytest
from fixture_roles import run_fixture as run_research

from hacknation_databricks.research.cli import fixture_source as default_source
from hacknation_databricks.research.models import RunConfig
from hacknation_databricks.research.sources import read_source
from hacknation_databricks.tracking import (
    artifact_path,
    decision_contract,
    load_journal,
    validate_trace,
)


@pytest.fixture
def tracked_run(tmp_path):
    directory = tmp_path / "run"
    run_research(
        read_source(default_source()),
        directory,
        RunConfig(sizes=[8, 16], trials=32, max_seconds=60),
    )
    return directory


def event(kind, stage):
    return {"event": kind, "time": "2026-10-03T19:00:00Z", "data": {"stage": stage}}


def test_real_run_has_evidence_for_every_closed_decision(tracked_run):
    journal = load_journal(tracked_run)
    assert journal.verified, journal.issues
    assert len(journal.decisions) == 7
    assert journal.decisions[-1].choice == "Novelty gate held"
    assert journal.decisions[-1].status == "review"
    assert all(record.evidence for record in journal.decisions)
    for record in journal.decisions:
        contract = decision_contract(record)
        assert contract["probabilities"] is None
        for key, answer in contract["answers"].items():
            assert answer in contract["questions"][key]["criteria"]
    assert journal.export() == load_journal(tracked_run).export()


@pytest.mark.parametrize(
    "trace",
    [
        [event("stage_started", "baseline")],
        [event("stage_started", "shell")],
        [event("stage_completed", "reader")],
        [event("stage_started", "reader"), event("stage_started", "critic")],
        [
            event("stage_started", "reader"),
            event("stage_completed", "reader"),
            event("stage_started", "reader"),
        ],
        [
            event("stage_started", "reader"),
            event("stage_failed", "reader"),
            event("stage_started", "critic"),
        ],
        [event("run_finished", ""), event("stage_started", "reader")],
    ],
)
def test_free_form_skipped_duplicate_and_post_stop_stages_rejected(trace):
    with pytest.raises(ValueError):
        validate_trace(trace, 2)


def test_in_progress_stage_is_not_a_completed_decision():
    states = validate_trace([event("stage_started", "reader")], 2)
    assert states["reader"][0] == "running"


def test_tampered_evidence_is_not_verified(tracked_run):
    path = tracked_run / "rounds/01/validation.json"
    value = json.loads(path.read_text())
    value["reasoning"] = "This changed after the run was sealed."
    path.write_text(json.dumps(value))
    journal = load_journal(tracked_run)
    assert not journal.verified
    assert "Artifact changed: rounds/01/validation.json" in journal.issues


@pytest.mark.parametrize(
    "target,mutate",
    [
        (
            "proposals.json",
            lambda v: v["proposals"][0]["evidence"].update(quote="fabricated quotation"),
        ),
        ("rounds/01/plan.json", lambda v: v.update(experiment="resistor_diode")),
        ("rounds/01/gate.json", lambda v: v.update(met=True)),
        ("report.json", lambda v: v.update(role_calls=1000)),
    ],
)
def test_contract_evidence_and_budget_violations_quarantined(tracked_run, target, mutate):
    path = tracked_run / target
    value = json.loads(path.read_text())
    mutate(value)
    path.write_text(json.dumps(value))
    journal = load_journal(tracked_run)
    assert not journal.verified
    assert journal.issues


def test_manifest_cannot_escape_run_or_omit_decision_inputs(tracked_run):
    path = tracked_run / "manifest.json"
    manifest = json.loads(path.read_text())
    del manifest["artifacts"]["proposals.json"]
    path.write_text(json.dumps(manifest))
    assert not load_journal(tracked_run).verified
    with pytest.raises(ValueError):
        artifact_path(tracked_run, "../outside.json")
    (tracked_run / "escape").symlink_to(tracked_run.parent)
    with pytest.raises(ValueError):
        artifact_path(tracked_run, "escape/outside.json")


def test_missing_and_malformed_runs_fail_closed(tmp_path):
    assert load_journal(tmp_path).issues
    (tmp_path / "config.json").write_text("null")
    assert load_journal(tmp_path).issues


def test_fabricated_novelty_criteria_fail_even_when_internally_consistent(tracked_run):
    path = tracked_run / "rounds/01/gate.json"
    value = json.loads(path.read_text())
    value["criteria"] = dict.fromkeys(value["criteria"], True)
    value["met"] = True
    path.write_text(json.dumps(value))
    journal = load_journal(tracked_run)
    assert not journal.verified
    assert any("contract" in issue for issue in journal.issues)


def test_planner_choices_cannot_switch_to_another_recipe(tracked_run):
    journal = load_journal(tracked_run)
    record = next(d for d in journal.decisions if d.step == "planner")
    contract = decision_contract(record)
    assert set(contract["questions"]["planner"]["criteria"]) == {"random_manhattan", "stop"}
