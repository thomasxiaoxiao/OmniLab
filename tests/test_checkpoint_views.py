"""Protect causality and enforcement claims in the decision story."""

import json

import pytest
from streamlit.testing.v1 import AppTest
from test_adaptive import make_run

from hacknation_databricks.checkpoint_views import checkpoint_story
from hacknation_databricks.research.activity import Activity, load_activity
from hacknation_databricks.tracking import load_journal


@pytest.fixture
def journal(tmp_path):
    make_run(tmp_path)
    result = load_journal(tmp_path / "run")
    assert result.verified, result.issues
    return result


def test_checkpoint_uses_available_evidence_and_explicit_parent_handoffs(journal):
    nodes = load_activity(journal)
    for checkpoint in journal.report["checkpoints"]:
        number = checkpoint["checkpoint"]
        story = checkpoint_story(journal, number)
        payload = json.loads((journal.directory / checkpoint["input"]).read_text())
        assert story["input"]["latest_result"] == payload["latest_result"]
        expected = {
            n.stage.rsplit("/", 1)[0]
            for n in nodes
            if n.stage.startswith("branches/")
            and n.stage.endswith("/planner")
            and f"checkpoints/{number:03d}/decision" in (n.parents or [])
        }
        assert {a["prefix"] for a in story["actions"]} == expected
        if checkpoint.get("observation_after_stop") or checkpoint.get("goal_accepted"):
            assert not story["actions"]
    # A later cumulative result cannot change the earlier scientific story.
    original = checkpoint_story(journal, 1)["input"]["latest_result"]
    for branch in journal.report["branches"].values():
        branch["checks"] = [{"difference": 999}]
    assert checkpoint_story(journal, 1)["input"]["latest_result"] == original


def test_recommendation_and_specification_do_not_establish_dispatch(journal, monkeypatch):
    nodes = load_activity(journal)
    selected = next(
        c["checkpoint"]
        for c in journal.report["checkpoints"]
        if checkpoint_story(journal, c["checkpoint"])["actions"]
    )
    for node in nodes:
        node.events = [
            e for e in node.events if e["event"] not in {"tool_dispatched", "tool_result"}
        ]
    monkeypatch.setattr("hacknation_databricks.checkpoint_views.load_activity", lambda _: nodes)
    story = checkpoint_story(journal, selected)
    assert all(a["specification"] for a in story["actions"])
    assert all(not a["dispatched"] for a in story["actions"])
    assert story["outcome"] == "Started planning; no simulation dispatch recorded"


def test_auxiliary_and_quarantined_runs_cannot_claim_omnigent_evidence(journal):
    story = checkpoint_story(journal, 1)
    assert not story["shared_agent"]
    assert not story["sessions"]
    assert story["decision_node"] is None
    journal.issues.append("Tampered evidence")
    with pytest.raises(ValueError, match="Unverified history"):
        checkpoint_story(journal, 1)


def test_common_runtime_evidence_requires_matching_ids_and_archived_constraints(
    journal, monkeypatch
):
    journal.sealed = False
    nodes = []
    for index in (1, 2):
        node = Activity(
            f"sources/{index}/researcher",
            "researcher",
            0,
            "omnigent",
            "",
            session_id=f"fixture-session-{index}",
            agent_id="fixture-agent",
            call_id=f"fixture-{index}",
        )
        nodes.append(node)
        (journal.directory / f"fixture-{index}-request.json").write_text(
            json.dumps(
                {
                    "prompt_version": "fixture",
                    "prompt": json.dumps({"constraints": "Same contract"}),
                }
            )
        )
    monkeypatch.setattr("hacknation_databricks.checkpoint_views.load_activity", lambda _: nodes)
    story = checkpoint_story(journal, 1)
    assert story["shared_agent"]
    assert story["common_constraints"] == "Same contract"
    assert not any(s["Response saved"] for s in story["sessions"])
    nodes[1].agent_id = "other-agent"
    (journal.directory / "fixture-2-request.json").unlink()
    story = checkpoint_story(journal, 1)
    assert not story["shared_agent"]
    assert story["common_constraints"] is None


def test_checkpoint_ui_selects_acceptance_and_can_inspect_earlier_evidence(journal):
    script = (
        "from pathlib import Path\n"
        "from hacknation_databricks.tracking import load_journal\n"
        "from hacknation_databricks.checkpoint_ui import render_checkpoint_story\n"
        f"render_checkpoint_story(load_journal(Path({str(journal.directory)!r})))\n"
    )
    app = AppTest.from_string(script).run(timeout=15)
    assert not app.exception
    accepted = next(c["checkpoint"] for c in journal.report["checkpoints"] if c["goal_accepted"])
    picker = next(s for s in app.selectbox if s.label == "Decision checkpoint")
    assert picker.value == accepted
    assert any("scoped numerical result" in s.value for s in app.success)
    picker.set_value(1).run()
    assert not app.exception
    assert not app.success
    assert any("No validated Omnigent session recorded" in s.value for s in app.caption)
    assert any("later results are excluded" in s.value for s in app.caption)
