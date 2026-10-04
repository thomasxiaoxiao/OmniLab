"""AnyJev owns the action; researcher proposals cannot bypass the decision or its audit."""

import json

import pytest
from test_repository_execution import RepositoryRoles, fixture_execute, fixture_repository

from hacknation_databricks.research.agents import AgentUnavailable
from hacknation_databricks.research.artifacts import verify_artifacts
from hacknation_databricks.research.models import RunConfig
from hacknation_databricks.research.repository_audit import verify_repository_outputs
from hacknation_databricks.research.repository_workflow import run_repository
from hacknation_databricks.research.sources import read_source
from hacknation_databricks.tracking import load_journal


def decision_run(
    tmp_path, monkeypatch, *, answer="followup", error=None, precision=False, **limits
):
    seen, closed, roles = [], [], []

    class Worker:
        manifest = {"model": "test fixture, no live inference"}

        def __init__(self, *args):
            pass

        def decide(self, state, question, choices):
            seen.append({"state": state, "choices": choices})
            if error:
                raise error
            chosen = answer if answer in choices else "stop"
            return {
                "answer": chosen,
                "probabilities": {
                    k: (0.5 if answer == "ambiguous" else 0.9 if k == chosen else 0.1)
                    for k in choices
                },
                "usage": {"generated_tokens": 0, "prefills": len(choices), "input_tokens": 123},
                "level": "L0",
                "calibrated": False,
            }

        def close(self):
            closed.append(True)

    class Researchers(RepositoryRoles):
        def ask(self, role, payload, contract):
            roles.append(role)
            assert role != "repository_evaluator"
            value = super().ask(role, payload, contract)
            if precision and role == "repository_assessor" and value.action == "followup":
                value.action = "precision"
                value.next_treatment = None
                value.next_experiment = "Run the preregistered eight-pair precision test."
            return value

    monkeypatch.setattr("hacknation_databricks.research.decision_roles.DecisionProcess", Worker)
    paper = tmp_path / "paper.md"
    paper.write_text("Compare decay rates with a reproducible numerical model.")
    config = RunConfig(
        workflow="repository",
        decision_backend="anyjev",
        repository_url="https://github.com/example/science",
        max_rounds=2,
        **limits,
    )
    output = tmp_path / "run"
    report = run_repository(
        read_source(paper),
        output,
        config,
        backend="fixture",
        roles_factory=Researchers,
        repository_fetcher=fixture_repository,
        code_executor=fixture_execute,
    )
    assert closed == [True]
    assert not verify_artifacts(output)
    assert load_journal(output).verified
    return output, report, seen, roles


@pytest.mark.parametrize("answer,rounds", [("followup", 2), ("stop", 1)])
def test_anyjev_controls_execution_and_has_distinct_activity(tmp_path, monkeypatch, answer, rounds):
    from hacknation_databricks.research.activity import load_activity

    output, report, seen, roles = decision_run(tmp_path, monkeypatch, answer=answer)
    assert report["status"] == "research_stopped"
    assert report["decision_calls"] == rounds
    assert len(report["rounds"]) == rounds
    assert roles.count("repository_assessor") == rounds
    assert seen[0]["state"]["researcher_assessment"]["action"] == "followup"
    assert report["rounds"][0]["next_decision"]["action"] == answer
    if rounds == 2:
        assert report["rounds"][1]["treatment"] == {"rate": 0.8}
        assert set(seen[-1]["choices"]) == {"stop", "review"}
    nodes = load_activity(load_journal(output))
    decisions = [node for node in nodes if node.kind == "anyjev"]
    assert len(decisions) == rounds
    assert decisions[0].parents == ["rounds/01/assessment"]
    assert decisions[0].session_id is None
    assert any(path.startswith("decisions/") for path in decisions[0].artifacts)


@pytest.mark.parametrize("failure", ["ambiguous", "unavailable", "budget"])
def test_evaluation_failure_preserves_evidence_without_codex_fallback(
    tmp_path, monkeypatch, failure
):
    output, report, seen, _ = decision_run(
        tmp_path,
        monkeypatch,
        answer="ambiguous" if failure == "ambiguous" else "followup",
        error=AgentUnavailable("Fixture missing model") if failure == "unavailable" else None,
        **({"max_decision_calls": 1} if failure == "budget" else {}),
    )
    assert (
        report["status"]
        == {
            "ambiguous": "research_stopped",
            "unavailable": "blocked_live_backend",
            "budget": "budget_exhausted",
        }[failure]
    )
    assert report["final_experiment"] is None
    assert "next_decision" not in report["rounds"][-1]
    assert (output / "rounds/01/assessment.json").is_file()
    assert seen


@pytest.mark.parametrize("tamper", ["measurements", "action", "generated_tokens"])
def test_handoff_audit_rejects_changed_inputs_or_action_even_if_resealed(
    tmp_path, monkeypatch, tamper
):
    output, report, _, _ = decision_run(tmp_path, monkeypatch)
    artifacts = json.loads((output / "manifest.json").read_text())["artifacts"]
    if tamper == "measurements":
        path = output / "rounds/01/evaluation-input.json"
        value = json.loads(path.read_text())
        value["summary"]["difference"] = 999
    elif tamper == "action":
        path = output / "rounds/01/decision.json"
        value = json.loads(path.read_text())
        value["action"] = "stop"
        report["rounds"][0]["next_decision"] = value
    else:
        path = next((output / "decisions").glob("01-*.json"))
        value = json.loads(path.read_text())
        value["result"]["usage"]["generated_tokens"] = 1
    path.write_text(json.dumps(value))
    assert verify_repository_outputs(output, report, artifacts)


def test_live_workflow_rejects_codex_evaluator_before_spending_calls(tmp_path):
    with pytest.raises(ValueError, match="decision_backend='anyjev'"):
        run_repository(None, tmp_path / "run", RunConfig(workflow="repository"))
    assert not (tmp_path / "run").exists()


def test_precision_runs_more_fresh_pairs_without_changing_arms(tmp_path, monkeypatch):
    output, report, seen, _ = decision_run(
        tmp_path, monkeypatch, precision=True, answer="precision"
    )
    assert len(report["rounds"]) == 2
    assert report["rounds"][0]["next_decision"]["action"] == "precision"
    assert [r["summary"]["samples_per_arm"] for r in report["rounds"]] == [4, 8]
    assert report["rounds"][0]["treatment"] == report["rounds"][1]["treatment"]
    first = json.loads((output / "rounds/01/specification.json").read_text())
    second = json.loads((output / "rounds/02/specification.json").read_text())
    assert set(first["seeds"]).isdisjoint(second["seeds"])
    assert report["computed_simulations"] == 4 + 10 + 18
    assert "precision" in seen[0]["choices"]
    assert "precision" not in seen[1]["choices"]
    assert load_journal(output).verified


def test_precision_cannot_exceed_simulation_budget(tmp_path, monkeypatch):
    _, report, seen, _ = decision_run(
        tmp_path, monkeypatch, precision=True, answer="precision", max_simulations=16
    )
    assert len(report["rounds"]) == 1
    assert "precision" not in seen[0]["choices"]
    assert report["next_decision"]["action"] == "stop"
