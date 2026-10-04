"""Reject uninformative plans and verbose agent summaries before executing them."""

import json

import pytest
from pydantic import ValidationError
from test_repository_execution import RepositoryRoles, make_repository_run

from hacknation_databricks.research.repository_models import (
    AgentRepositoryDecision,
    AgentRepositoryPlan,
    RepositoryDecision,
    RepositoryPlan,
)
from hacknation_databricks.research_views import next_experiment_summary
from hacknation_databricks.tracking import load_journal


@pytest.mark.parametrize("problem", ["identity", "missing_followup", "same_treatment", "partial"])
def test_uninformative_plan_gets_one_repair_before_execution(tmp_path, problem):
    repaired = []

    class RepairedPlan(RepositoryRoles):
        def ask(self, role, payload, contract):
            value = super().ask(role, payload, contract)
            if role == "repository_planner":
                if "contract_repair" in payload:
                    repaired.append(payload["contract_repair"])
                else:
                    raw = value.model_dump()
                    design = raw["learning_design"]
                    if problem == "identity":
                        design["verification_only"] = True
                    elif problem == "missing_followup":
                        design["followups"] = []
                    else:
                        design["followups"][0]["treatment"] = (
                            raw["treatment"] if problem == "same_treatment" else {"wrong_key": 1}
                        )
                    return contract.model_validate(raw)
            return value

    output, report = make_repository_run(tmp_path, roles_factory=RepairedPlan)
    assert len(repaired) == 1
    assert report["status"] == "research_stopped"
    assert (output / "planner_contract_failure.json").is_file()
    assert load_journal(output).verified


def test_old_plans_and_decisions_remain_readable(tmp_path):
    output, _ = make_repository_run(tmp_path)
    plan = json.loads((output / "planner.json").read_text())
    del plan["learning_design"]
    assert RepositoryPlan.model_validate(plan)
    with pytest.raises(ValidationError):
        AgentRepositoryPlan.model_validate(plan)
    decision = json.loads((output / "rounds/01/decision.json").read_text())
    decision["next_experiment"] = (
        "Run another bounded trial after considering all recorded conditions. " * 6
    )
    assert RepositoryDecision.model_validate(decision)
    with pytest.raises(ValidationError):
        AgentRepositoryDecision.model_validate(decision)
    short = next_experiment_summary(decision["next_experiment"])
    assert len(short) <= 140 and len(short.split()) <= 20
    assert short.endswith("…")


@pytest.mark.parametrize(
    "verbose", ["Go " * 21, "First test. Second test.", "Test\nwith more seeds."]
)
def test_next_experiment_constraints_trigger_agent_repair(tmp_path, verbose):
    repaired = []

    class ConciseAssessor(RepositoryRoles):
        def ask(self, role, payload, contract):
            value = super().ask(role, payload, contract)
            if role == "repository_evaluator":
                if "contract_repair" not in payload:
                    return contract.model_validate(
                        {**value.model_dump(), "next_experiment": verbose}
                    )
                repaired.append(True)
            return value

    output, report = make_repository_run(tmp_path, roles_factory=ConciseAssessor)
    assert len(repaired) == 2
    assert report["status"] == "research_stopped"
    assert load_journal(output).verified
    for row in report["rounds"]:
        assert len(row["next_decision"]["next_experiment"].split()) <= 20


def test_overview_keeps_complete_legacy_next_step_in_details(tmp_path):
    from view_test import ViewTest

    from hacknation_databricks.repository_ui import render_repository_result

    output, _ = make_repository_run(tmp_path)
    journal = load_journal(output)
    original = "Run the precision experiment with unchanged arms and fresh seeds. " * 4
    journal.report["rounds"][-1]["next_decision"]["next_experiment"] = original
    app = ViewTest.from_function(render_repository_result, args=(journal,)).run()
    assert not app.exception
    assert next_experiment_summary(original) in [node.value for node in app.markdown]
    assert original in [node.value for node in app.markdown]
    assert "Full recorded next experiment" in [node.label for node in app.expander]


def test_diagnostics_preserve_bad_outcomes_and_disclose_large_omissions():
    from hacknation_databricks.research.assessment_evidence import assessment_evidence

    result = {
        "trials": [
            {
                "arm": arm,
                "seed": seed,
                "output": {
                    "metric": 0.1,
                    "measurements": {
                        "accuracy_passed": False,
                        "missed_events": seed,
                        "raw_cases": [0] * 10000,
                    },
                },
            }
            for seed in [1, 2]
            for arm in ["control", "proposed"]
        ]
    }
    evidence = assessment_evidence(result, "rounds/01/trials.json", limit=2000)
    assert len(evidence["trials"]) == 4
    for trial in evidence["trials"]:
        assert trial["measurements"] == {"accuracy_passed": False, "missed_events": trial["seed"]}
        assert trial["omitted_field_count"] == 1
        assert trial["omitted_fields_preview"] == ["raw_cases"]


def test_researcher_receives_secondary_results_and_audit_binds_them(tmp_path):
    from test_repository_execution import fixture_execute

    from hacknation_databricks.research.repository_audit import verify_repository_outputs

    assessments = []

    def execute_with_diagnostics(store, *args, **kwargs):
        result = fixture_execute(store, *args, **kwargs)
        for trial in result["trials"]:
            trial["output"]["measurements"] = {"missed_events": 7, "accuracy_passed": False}
        store.write(kwargs["stage"] + "/trials.json", result)
        return result

    class InformedResearcher(RepositoryRoles):
        def ask(self, role, payload, contract):
            if role == "repository_evaluator":
                diagnostics = payload["diagnostics"]
                assert all(
                    t["measurements"]["accuracy_passed"] is False for t in diagnostics["trials"]
                )
                assert payload["remaining_budget"]["simulations"] > 0
                assessments.append(diagnostics)
            return super().ask(role, payload, contract)

    output, report = make_repository_run(
        tmp_path, roles_factory=InformedResearcher, code_executor=execute_with_diagnostics
    )
    assert len(assessments) == 2
    assert load_journal(output).verified
    path = output / "rounds/01/assessment-evidence.json"
    value = json.loads(path.read_text())
    value["trials"][0]["measurements"]["accuracy_passed"] = True
    path.write_text(json.dumps(value))
    artifacts = json.loads((output / "manifest.json").read_text())["artifacts"]
    assert verify_repository_outputs(output, report, artifacts)
