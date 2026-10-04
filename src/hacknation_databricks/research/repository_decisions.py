"""Decision-only AnyJev evaluation of measured results and a researcher's proposal."""

import hashlib
import math

from .artifacts import canonical
from .decision_roles import AnyJevRoles
from .repository_models import RepositoryDecision

QUESTION = "Which next action is justified by these measurements, limitations and remaining budget?"


def decision_state(plan, treatment, summary, assessment, remaining):
    return {
        "evidence_scope": "Current round measurements and researcher interpretation; no code or "
        "earlier raw trials are supplied to this closed-option evaluator.",
        "hypothesis": plan.hypothesis,
        "controls": plan.controls,
        "baseline_scope": plan.baseline_scope,
        "baseline": plan.baseline,
        "current_treatment": treatment,
        "summary": summary,
        "researcher_assessment": assessment.model_dump(),
        "remaining_budget": remaining,
        "policy": "Continue only when the proposed parameter change can resolve uncertainty. "
        "A passing sanity check or replay does not establish the hypothesis or novelty. "
        "Stop for exhausted budget, unresolvable uncertainty or a flawed experiment. "
        "Option weights are uncalibrated, not probabilities of scientific truth.",
    }


def decision_options(state):
    assessment = RepositoryDecision.model_validate(state["researcher_assessment"])
    options = {}
    treatment = assessment.next_treatment
    if assessment.action == "followup":
        if (
            not treatment
            or treatment in (state["baseline"], state["current_treatment"])
            or set(treatment) != set(state["baseline"])
            or len(canonical(treatment)) > 16_000
        ):
            raise ValueError("Researcher proposed invalid follow-up parameters")
        budget = state["remaining_budget"]
        if budget["rounds"] > 0 and budget["simulations"] >= budget["jobs_per_round"]:
            options["followup"] = assessment.model_dump()
    options["stop"] = {
        **assessment.model_dump(),
        "action": "stop",
        "next_treatment": None,
        "next_experiment": assessment.next_experiment
        if assessment.action == "stop"
        else "Stop this run and review the retained measurements and proposed follow-up before "
        "starting another bounded experiment.",
    }
    # Keep an explicit evidence-review choice when no executable follow-up is available.
    if not options.get("followup"):
        options["review"] = {
            **options["stop"],
            "next_experiment": "Stop for independent review of the evidence, assumptions and "
            "implementation before authorizing a new experiment.",
        }
    return options


def selected_decision(state, result):
    options = decision_options(state)
    choices = {key: value["next_experiment"] for key, value in options.items()}
    selected = {**options[result["answer"]]}
    selected["rationale"] = AnyJevRoles.explanation(result, choices)
    return RepositoryDecision.model_validate(selected)


def evaluate(scorer, store, prefix, state):
    options = decision_options(state)
    choices = {key: value["next_experiment"] for key, value in options.items()}
    store.write(prefix + "/evaluation-input.json", state)
    scorer.role = prefix + "/decision"
    key = prefix.replace("/", "-") + "-evaluation"
    result = scorer.choose(key, state, QUESTION, choices)
    decision = selected_decision(state, result)
    store.write(
        prefix + "/anyjev-handoff.json",
        {
            "researcher_assessment": state["researcher_assessment"],
            "decision_artifact": f"decisions/{scorer.decision_calls:02d}-{key}.json",
            "selected_action": decision.model_dump(),
            "integration": "Omnigent researcher proposal → local AnyJev decision-only evaluator",
        },
    )
    return decision


def verify_handoff(state, decision, handoff, record):
    options = decision_options(state)
    choices = {key: value["next_experiment"] for key, value in options.items()}
    request = {"state": state, "question": QUESTION, "choices": choices}
    result = record["result"]
    probabilities = result["probabilities"]
    weights = sorted(probabilities.values(), reverse=True)
    if (
        any(record[key] != value for key, value in request.items())
        or record["input_sha256"] != hashlib.sha256(canonical(request).encode()).hexdigest()
        or record["backend"] != "anyjev"
        or set(probabilities) != set(choices)
        or any(not math.isfinite(p) or not 0 <= p <= 1 for p in weights)
        or abs(sum(weights) - 1) > 1e-6
        or result["answer"] != max(probabilities, key=probabilities.get)
        or weights[0] - weights[1] < 0.05
        or result["usage"]["generated_tokens"] != 0
        or result["usage"]["prefills"] != len(choices)
        or result["level"] != "L0"
        or result["calibrated"] is not False
        or handoff["researcher_assessment"] != state["researcher_assessment"]
        or selected_decision(state, result).model_dump() != decision
        or handoff["selected_action"] != decision
    ):
        raise ValueError("AnyJev evaluation differs from its measured inputs or selected action")
