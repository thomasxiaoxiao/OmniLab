"""Omnigent evidence assessments handed to a bounded local AnyJev decision tool."""

import hashlib

from .agents import OmnigentRoles
from .artifacts import canonical
from .decision_roles import AnyJevRoles
from .models import InvestmentDecision

NUMERICAL_DECISION_POLICY = {
    "scope": "Resolve the declared numerical comparison within the existing finite budgets.",
    "invest_when": "An interval is too wide or independent batches are missing, and the "
    "allowed fresh samples can resolve that uncertainty. An unresolved first batch is "
    "expected screening evidence, not an evidence defect.",
    "finalize_when": "The branch is goal_eligible; request independent validation rather "
    "than declaring success from the scorer alone.",
    "review_when": "A concrete source, measurement, implementation or contract defect "
    "makes further allowed simulation unable to answer the numerical question.",
    "stop_when": "The allowed tests cannot resolve the goal or remaining budgets cannot "
    "support useful work. Retain negative and inconclusive results.",
    "limitations": "Missing real-world calibration or global novelty evidence limits "
    "external claims; it does not itself block this explicitly synthetic numerical goal. "
    "Pending independent validation is expected before eligibility, not a reason to stop.",
}


def investment_options(payload: dict, assessment: InvestmentDecision) -> dict:
    """Only existing branches with remaining work or eligible results are selectable."""
    options = {}
    base = assessment.model_dump()
    for key, branch in payload["branches"].items():
        if branch["batches"] < payload["max_batches_per_branch"]:
            options[f"invest_{key}"] = {
                **base,
                "action": "invest",
                "invest": [key],
                "goal_branch_id": None,
                "next_experiment": f"Run the next bounded simulation batch for branch {key}.",
            }
        if branch.get("goal_eligible"):
            options[f"finalize_{key}"] = {
                **base,
                "action": "finalize",
                "invest": [],
                "goal_branch_id": key,
                "next_experiment": f"Submit branch {key} to independent final validation.",
            }
    options["stop"] = {
        **base,
        "action": "stop",
        "invest": [],
        "goal_branch_id": None,
        "next_experiment": "Stop new simulation allocations and review the retained evidence.",
    }
    # Always retain the safe abstention alternative, even when all branches are exhausted.
    options["review"] = {
        **options["stop"],
        "next_experiment": "Review unresolved evidence before designing another bounded run.",
    }
    if "decision_policy" in payload:
        options["review"]["next_experiment"] = (
            "Stop for a concrete evidence or implementation defect that more allowed "
            "samples cannot repair; identify the defect in the assessment."
        )
        options["stop"]["next_experiment"] = (
            "Stop because allowed tests cannot resolve the numerical goal or the "
            "remaining budget cannot support useful work."
        )
    return options


def investment_state(payload, assessment):
    """Complete bounded measurement context used by the local scorer."""
    return {
        "goal": payload["goal"],
        "remaining_budget": payload["remaining_budget"],
        "in_flight": payload["in_flight"],
        "assessment": assessment.model_dump(),
        **(
            {"measurement_contract": payload["measurement_contract"]}
            if "measurement_contract" in payload
            else {}
        ),
        **({"decision_policy": payload["decision_policy"]} if "decision_policy" in payload else {}),
        "branches": {
            key: {k: branch.get(k) for k in ("batches", "checks", "goal_eligible", "status")}
            for key, branch in payload["branches"].items()
        },
    }


def verify_investment_handoff(payload, decision, handoff, record):
    """Reject a selection detached from the archived bounded question or measurements."""
    assessment = InvestmentDecision.model_validate(handoff["omnigent_assessment"])
    options = investment_options(payload, assessment)
    choices = {key: value["next_experiment"] for key, value in options.items()}
    request = {k: record[k] for k in ("state", "question", "choices")}
    result = record["result"]
    weights = sorted(result["probabilities"].values(), reverse=True)
    if (
        choices != record["choices"]
        or record["state"] != investment_state(payload, assessment)
        or record["input_sha256"] != hashlib.sha256(canonical(request).encode()).hexdigest()
        or set(result["probabilities"]) != set(choices)
        or result["answer"] != max(result["probabilities"], key=result["probabilities"].get)
        or len(weights) < 2
        or weights[0] - weights[1] < 0.05
    ):
        raise ValueError("Invalid AnyJev selection evidence")
    expected = options[result["answer"]]
    expected["rationale"] = AnyJevRoles.explanation(result, choices)
    if decision != expected or handoff["selected_action"] != decision:
        raise ValueError("AnyJev action differs from the executed decision")


class HybridOmnigentRoles(OmnigentRoles):
    """Codex supplies scientific interpretation; AnyJev selects the execution action.

    AnyJev runs as a supervisor tool attached to an Omnigent handoff, not as a
    natively hosted Omnigent harness. Both outputs are kept without relabeling.
    """

    required_harness = "codex"

    def __init__(self, sources, store, config):
        super().__init__(sources, store, config)
        self.scorer = AnyJevRoles(sources, store, config)

    @property
    def decision_calls(self):
        return self.scorer.decision_calls

    def ask(self, role, payload, contract):
        assessment = super().ask(role, payload, contract)
        if role != "decision_agent":
            return assessment
        options = investment_options(payload, assessment)
        choices = {key: value["next_experiment"] for key, value in options.items()}
        stage = f"checkpoints/{payload['checkpoint']:03d}/decision"
        self.scorer.role = stage
        self.scorer.deadline = self.deadline
        state = investment_state(payload, assessment)
        result = self.scorer.choose(
            f"checkpoint-{payload['checkpoint']:03d}",
            state,
            "Which bounded next action is justified by the measurements, assessment and budget?",
            choices,
        )
        selected = options[result["answer"]]
        selected["rationale"] = self.scorer.explanation(result, choices)
        decision = contract.model_validate(selected)
        self.store.write(
            f"checkpoints/{payload['checkpoint']:03d}/anyjev-handoff.json",
            {
                "omnigent_assessment": assessment.model_dump(),
                "decision_artifact": f"decisions/{self.scorer.decision_calls:02d}-"
                f"checkpoint-{payload['checkpoint']:03d}.json",
                "selected_action": decision.model_dump(),
                "integration": "Local AnyJev tool following the Omnigent assessment session",
            },
        )
        return decision

    def close(self):
        try:
            self.scorer.close()
        finally:
            super().close()
