from copy import deepcopy

from test_repository_execution import RepositoryRoles, make_repository_run
from view_test import ViewTest

from hacknation_databricks.repository_ui import render_repository_result
from hacknation_databricks.research_routes_ui import route_ledger
from hacknation_databricks.tracking import load_journal


def test_routes_keep_rejected_and_unselected_ideas_and_full_stop_reason(tmp_path):
    interpretation = "The measured effect remains limited to this numerical model. " * 12
    reason = "Stop because further treatment changes cannot resolve missing external evidence. " * 8

    class MultipleRoutes(RepositoryRoles):
        def ask(self, role, payload, contract):
            value = super().ask(role, payload, contract)
            if role == "repository_reader":
                for identity in ["secondary", "unsupported"]:
                    candidate = deepcopy(value.directions[0])
                    candidate.id = identity
                    candidate.title = identity.capitalize() + " direction"
                    value.directions.append(candidate)
            if role == "repository_critic":
                for identity, decision in [("secondary", "accept"), ("unsupported", "reject")]:
                    critique = deepcopy(value.critiques[0])
                    critique.proposal_id, critique.decision = identity, decision
                    value.critiques.append(critique)
            if role == "repository_evaluator":
                value.result_interpretation = interpretation
                value.rationale = reason
            return value

    output, _ = make_repository_run(tmp_path, roles_factory=MultipleRoutes)
    journal = load_journal(output)
    assert journal.verified, journal.issues
    routes = {r["id"]: r for r in route_ledger(journal)}
    assert routes["decay"]["status"] == "Executed"
    assert routes["secondary"]["status"] == "Accepted · not selected"
    assert routes["unsupported"]["status"] == "Rejected before execution"
    app = ViewTest.from_function(render_repository_result, args=(journal,)).run()
    assert not app.exception
    texts = [n.value for n in app.markdown]
    assert interpretation in texts
    assert reason in texts
    assert any("Experiment 1 → followup" == n.label for n in app.expander)
    assert any("Experiment 2 → stop" == n.label for n in app.expander)
