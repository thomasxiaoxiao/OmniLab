"""Boundary tests use protocol doubles; real-model results live in the run audit."""

import json

import pytest
from fixture_roles import DecisionWorkerFixture
from legacy.workflow import run_research as run_workflow

from hacknation_databricks.research import decision_roles
from hacknation_databricks.research.agents import AgentUnavailable
from hacknation_databricks.research.artifacts import verify_artifacts
from hacknation_databricks.research.cli import fixture_source, parser
from hacknation_databricks.research.decision_roles import passages
from hacknation_databricks.research.models import RunConfig
from hacknation_databricks.research.sources import read_source
from hacknation_databricks.tracking import decision_contract, load_journal


def run_research(*args, **kwargs):
    kwargs.setdefault("backend", "anyjev")
    return run_workflow(*args, **kwargs)


@pytest.fixture
def setup(monkeypatch, tmp_path):
    monkeypatch.setattr(decision_roles, "DecisionProcess", DecisionWorkerFixture)
    return read_source(fixture_source()), tmp_path / "run", RunConfig(sizes=[8, 16], trials=32)


def test_default_is_model_inference_and_scripted_execution_is_unavailable(tmp_path):
    assert parser().parse_args(["run"]).backend == "omnigent"
    with pytest.raises(ValueError, match="Backend"):
        run_research(read_source(fixture_source()), tmp_path, backend="scripted")
    with pytest.raises(ValueError, match="Backend"):
        run_research(read_source(fixture_source()), tmp_path, backend="fixture")


def test_model_selects_direction_instead_of_first_accepted_and_audits_each_choice(setup):
    source, root, config = setup
    report = run_research(source, root, config)
    assert report["backend"] == "anyjev"
    assert report["selected_proposal"]["id"] == "resistor_diode"
    assert report["acceptance"]["followup_implemented"]
    assert report["decision_calls"] == 13
    assert report["decision_usage"]["generated_tokens"] == 0
    journal = load_journal(root)
    assert journal.verified, journal.issues
    contract = decision_contract(journal.decisions[1])
    assert contract["answers"]["select-direction"] == "resistor_diode"
    assert contract["probabilities"]["select-direction"]["resistor_diode"] == 1
    assert "uncalibrated" in contract["provenance"]
    assert not verify_artifacts(root)


def test_ambiguous_decisions_stop_before_simulation_and_release_model(setup, monkeypatch):
    workers = []

    class Ambiguous(DecisionWorkerFixture):
        def __init__(self, *args):
            super().__init__(*args)
            workers.append(self)

        def decide(self, **kwargs):
            result = super().decide(**kwargs)
            result["probabilities"] = {k: 1 / len(kwargs["choices"]) for k in kwargs["choices"]}
            return result

    monkeypatch.setattr(decision_roles, "DecisionProcess", Ambiguous)
    _, root, _ = setup
    report = run_research(*setup)
    assert report["status"] == "needs_decision_review"
    assert report["computed_simulations"] == 0
    assert workers[0].closed
    assert load_journal(root).verified


def test_model_unavailable_has_no_scripted_fallback(setup, monkeypatch):
    def unavailable(*args):
        raise AgentUnavailable("Missing local model")

    monkeypatch.setattr(decision_roles, "DecisionProcess", unavailable)
    report = run_research(*setup)
    assert report["status"] == "blocked_live_backend"
    assert report["computed_simulations"] == report["decision_calls"] == 0
    assert not report["acceptance"]["live_agents_executed"]


def test_decision_budget_stops_before_critic_can_start_simulations(setup):
    source, root, config = setup
    report = run_research(source, root, config.model_copy(update={"max_decision_calls": 3}))
    assert report["status"] == "budget_exhausted"
    assert report["decision_calls"] == 3
    assert report["computed_simulations"] == 0


def test_model_stop_does_not_fall_back_to_first_proposal(setup, monkeypatch):
    class Stop(DecisionWorkerFixture):
        def decide(self, **kwargs):
            result = super().decide(**kwargs)
            if "stop" in kwargs["choices"]:
                result["answer"] = "stop"
                result["probabilities"] = {k: float(k == "stop") for k in kwargs["choices"]}
            return result

    monkeypatch.setattr(decision_roles, "DecisionProcess", Stop)
    report = run_research(*setup)
    assert report["status"] == "needs_decision_review"
    assert report["computed_simulations"] == 0


def test_audit_projection_cannot_replace_model_selection_even_without_manifest(setup):
    _, root, _ = setup
    run_research(*setup)
    (root / "manifest.json").unlink()
    path = root / "critiques.json"
    record = json.loads(path.read_text())
    record["selected_proposal_id"] = "random_manhattan"
    path.write_text(json.dumps(record))
    assert load_journal(root).issues


def test_retrieval_scans_last_page_and_preserves_exact_source_quotes():
    from dataclasses import replace

    source = read_source(fixture_source())
    text = "A future experiment could explore the unusual zebra lattice arrangement."
    source = replace(source, pages=("Introduction: familiar unrelated geometry.", text))
    picked, scope = passages(source, "zebra lattice")
    assert scope["pages_scanned"] == 2
    assert picked[0]["page"] == 2
    assert all(item["quote"] in source.pages[item["page"] - 1] for item in picked)


def test_related_topic_rejection_cannot_reach_feasibility_or_experiment(setup, monkeypatch):
    class Unrelated(DecisionWorkerFixture):
        def decide(self, **kwargs):
            result = super().decide(**kwargs)
            if "topic_only" in kwargs["choices"]:
                result["answer"] = "topic_only"
                result["probabilities"] = {k: float(k == "topic_only") for k in kwargs["choices"]}
            return result

    monkeypatch.setattr(decision_roles, "DecisionProcess", Unrelated)
    report = run_research(*setup)
    assert report["status"] == "all_proposals_rejected"
    assert report["computed_simulations"] == 0
    assert report["decision_calls"] == 6
    assert load_journal(setup[1]).verified


def test_model_gap_claim_cannot_spend_more_rounds_without_second_source(setup, monkeypatch):
    class GapClaim(DecisionWorkerFixture):
        def decide(self, **kwargs):
            result = super().decide(**kwargs)
            if "candidate_gap" in kwargs["choices"]:
                result["answer"] = "candidate_gap"
                result["probabilities"] = {
                    k: float(k == "candidate_gap") for k in kwargs["choices"]
                }
            return result

    monkeypatch.setattr(decision_roles, "DecisionProcess", GapClaim)
    report = run_research(*setup)
    assert report["status"] == "needs_literature_review"
    assert len(report["rounds"]) == 1
    assert not report["rounds"][0]["gate"]["criteria"]["multiple_sources_reviewed"]


def test_context_limit_rejects_instead_of_truncating_or_loading_metal():
    from types import SimpleNamespace

    from hacknation_databricks.research.decision_worker import MLXLogitsBackend

    backend = MLXLogitsBackend.__new__(MLXLogitsBackend)
    backend.mx = None
    backend.tokenizer = SimpleNamespace(encode=lambda *a, **k: [0] * 4097)
    with pytest.raises(ValueError, match="no truncation"):
        backend.next_token_logprobs(["oversized source"], [[1, 2]])
