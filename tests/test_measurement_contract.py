import json

import pytest
from legacy.adaptive_experiments import (
    MEASUREMENT_CONTRACTS,
    summarize_branch,
)

from hacknation_databricks.research.hybrid_roles import (
    NUMERICAL_DECISION_POLICY,
    investment_options,
    investment_state,
)
from hacknation_databricks.research.models import RunConfig


def test_astrosat_rates_use_truth_denominators_not_alert_denominators():
    rows = []
    for scenario in ("fresh", "stale"):
        rows.extend(
            {
                "scenario": scenario,
                "truth": truth,
                "control_alert": control,
                "treatment_alert": treatment,
            }
            for truth, control, treatment in [
                (True, True, True),
                (True, False, True),
                (False, True, True),
                (False, False, True),
                (False, False, False),
                (False, False, False),
            ]
        )
    summary = summarize_branch("astrosat", rows, RunConfig(), 2)
    for check in summary["checks"]:
        assert check["positive_transits"] == 2
        assert check["negative_candidates"] == 4
        assert check["control"] == 0.5
        assert check["treatment"] == 0
        assert check["control_false_alert_rate"] == 0.25
        assert check["false_alert_rate"] == 0.5
        # False discovery proportion for the control would be 1 / 2, not 1 / 4.
        assert check["control_false_alert_rate"] != pytest.approx(1 / 2)


def test_metric_contract_reaches_specialists_checkpoint_and_local_scorer(tmp_path, monkeypatch):
    from test_adaptive import AdaptiveFixture, make_run

    seen = []
    original = AdaptiveFixture.ask

    def capture(self, role, payload, contract):
        seen.append((role, payload.copy()))
        return original(self, role, payload, contract)

    monkeypatch.setattr(AdaptiveFixture, "ask", capture)
    report = make_run(tmp_path)
    assert report["status"] == "goal_achieved"
    expected = MEASUREMENT_CONTRACTS["astrosat"]
    assert {r for r, _ in seen} >= {
        "researcher",
        "consolidator",
        "branch_planner",
        "decision_agent",
        "validator",
    }
    assert all(p["measurement_contract"] == expected for _, p in seen)
    for path in (tmp_path / "run" / "checkpoints").glob("*/input.json"):
        payload = json.loads(path.read_text())
        assert payload["measurement_contract"] == expected
        from hacknation_databricks.research.models import InvestmentDecision

        assessment = InvestmentDecision.model_validate_json(
            path.with_name("decision.json").read_text()
        )
        assert investment_state(payload, assessment)["measurement_contract"] == expected
        assert investment_state(payload, assessment)["decision_policy"] == NUMERICAL_DECISION_POLICY
        options = investment_options(payload, assessment)
        assert {"stop", "review"} <= set(options)
        assert "cannot repair" in options["review"]["next_experiment"]
        # Archives without this policy retain their exact recorded action text.
        payload.pop("decision_policy")
        assert "decision_policy" not in investment_state(payload, assessment)
        assert investment_options(payload, assessment)["review"]["next_experiment"] == (
            "Review unresolved evidence before designing another bounded run."
        )
