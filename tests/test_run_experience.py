"""Launch identity, live artifacts, terminal status and fixed hybrid handoffs."""

import hashlib
import json
from concurrent.futures import Future
from pathlib import Path

import pytest
from view_test import ViewTest

from hacknation_databricks.research.agents import OmnigentRoles
from hacknation_databricks.research.artifacts import RunStore, canonical
from hacknation_databricks.research.decision_roles import AnyJevRoles, DecisionAbstained
from hacknation_databricks.research.hybrid_roles import (
    HybridOmnigentRoles,
    investment_options,
    investment_state,
    verify_investment_handoff,
)
from hacknation_databricks.research.models import InvestmentDecision, RunConfig

UI = Path(__file__).resolve().parents[1] / "src/hacknation_databricks/ui.py"


def test_launch_follows_exact_run_then_reports_completion(monkeypatch, tmp_path, launch_source):
    from test_adaptive import make_run

    from hacknation_databricks import tracking_ui

    monkeypatch.setenv("RESEARCH_RUNS_DIR", str(tmp_path))
    future = Future()
    submitted = {}

    class Executor:
        def submit(self, function, *args, **kwargs):
            submitted.update(kwargs)
            return future

    monkeypatch.setattr(tracking_ui, "background_executor", lambda: Executor())
    app = ViewTest.from_file(str(UI)).run(timeout=15)
    next(b for b in app.button if b.label == "Start bounded run").click().run()
    assert app.title[0].value == "Agents & execution loops"
    assert any("Run starting" in i.value for i in app.info)
    name = submitted["run_name"]
    make_run(tmp_path)
    directory = tmp_path / name
    (tmp_path / "run").rename(directory)
    # Another completed run must not steal the newly launched run's selection.
    make_run(tmp_path)
    app.switch_page("app_pages/agents.py").run(timeout=15)
    assert app.session_state["run_selection"] == name
    assert any("produced artifacts" in c.value for c in app.caption)
    future.set_result(directory)
    app.switch_page("app_pages/agents.py").run(timeout=15)
    assert any("Experiment finished" in s.value for s in app.success)
    assert app.session_state["run_selection"] == name
    assert not app.exception


def test_preflight_failure_never_displays_previous_experiment(monkeypatch, tmp_path, launch_source):
    from test_adaptive import make_run

    from hacknation_databricks import tracking_ui

    make_run(tmp_path)
    monkeypatch.setenv("RESEARCH_RUNS_DIR", str(tmp_path))
    future = Future()

    class Executor:
        def submit(self, *args, **kwargs):
            return future

    monkeypatch.setattr(tracking_ui, "background_executor", lambda: Executor())
    app = ViewTest.from_file(str(UI)).run(timeout=15)
    next(b for b in app.button if b.label == "Start bounded run").click().run()
    future.set_exception(ValueError("Omnigent is unavailable"))
    app.switch_page("app_pages/agents.py").run(timeout=15)
    assert any("Run could not start" in e.value for e in app.error)
    assert not app.success
    assert not any("produced artifacts" in c.value for c in app.caption)
    assert not app.exception


def assessment():
    return InvestmentDecision(
        action="invest",
        invest=["b1_1"],
        result_interpretation="The observed interval still includes zero.",
        rationale="Another independent batch can resolve the uncertainty.",
        next_experiment="Repeat the existing bounded experiment.",
        missing_evidence=[],
    )


def payload():
    return {
        "checkpoint": 1,
        "goal": {},
        "remaining_budget": {},
        "in_flight": [],
        "max_batches_per_branch": 4,
        "branches": {
            "b1_1": {"batches": 1, "goal_eligible": False},
            "b1_2": {"batches": 4, "goal_eligible": True},
        },
    }


def test_hybrid_options_do_not_finalize_ineligible_or_repeat_exhausted_branch():
    options = investment_options(payload(), assessment())
    assert "finalize_b1_1" not in options
    assert "invest_b1_2" not in options
    assert {"invest_b1_1", "finalize_b1_2", "stop", "review"} == set(options)
    assert all(InvestmentDecision.model_validate(o) for o in options.values())


def test_handoff_audit_rejects_changed_measurements_and_action():
    context, original = payload(), assessment()
    options = investment_options(context, original)
    choices = {k: v["next_experiment"] for k, v in options.items()}
    request = {
        "state": investment_state(context, original),
        "question": "Choose",
        "choices": choices,
    }
    result = {"answer": "stop", "probabilities": {k: 0.7 if k == "stop" else 0.1 for k in choices}}
    record = {
        **request,
        "result": result,
        "input_sha256": hashlib.sha256(canonical(request).encode()).hexdigest(),
    }
    selected = options["stop"]
    selected["rationale"] = AnyJevRoles.explanation(result, choices)
    handoff = {"omnigent_assessment": original.model_dump(), "selected_action": selected}
    verify_investment_handoff(context, selected, handoff, record)
    with pytest.raises(ValueError):
        verify_investment_handoff(context, {**selected, "action": "invest"}, handoff, record)
    context["remaining_budget"] = {"seconds": 999}
    with pytest.raises(ValueError):
        verify_investment_handoff(context, selected, handoff, record)


@pytest.mark.parametrize("abstain", [False, True])
def test_hybrid_preserves_both_outputs_and_closes_worker(monkeypatch, tmp_path, abstain):
    store = RunStore(tmp_path / "run")
    roles = HybridOmnigentRoles([], store, RunConfig())
    monkeypatch.setattr(OmnigentRoles, "ask", lambda *args: assessment())
    seen = []

    def choose(key, state, question, choices):
        seen.append(state)
        if abstain:
            raise DecisionAbstained("Ambiguous model choice")
        return {"answer": "stop", "probabilities": {"stop": 0.9}}

    monkeypatch.setattr(roles.scorer, "choose", choose)
    closed = []
    monkeypatch.setattr(roles.scorer, "close", lambda: closed.append(True))
    try:
        if abstain:
            with pytest.raises(DecisionAbstained):
                roles.ask("decision_agent", payload(), InvestmentDecision)
            assert not (store.directory / "checkpoints/001/anyjev-handoff.json").exists()
        else:
            result = roles.ask("decision_agent", payload(), InvestmentDecision)
            assert result.action == "stop"  # AnyJev's selection overrides the assessment.
            saved = json.loads(
                (store.directory / "checkpoints/001/anyjev-handoff.json").read_text()
            )
            assert saved["omnigent_assessment"]["action"] == "invest"
            assert saved["selected_action"]["action"] == "stop"
        assert seen[0]["assessment"] == assessment().model_dump()
    finally:
        roles.close()
    assert closed == [True]
