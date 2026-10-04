"""Read-only checks on historical ledgers; contains no experiment runner or kernel."""

from statistics import NormalDist

import numpy as np

from .models import LiteratureReview, NoveltyReview, ValidationReview
from .process_visualization import checked_process
from .scientific_statistics import wilson


def novelty_gate(
    baseline: dict,
    numerical: dict,
    effect: dict,
    literature: LiteratureReview,
    review: ValidationReview,
    backend: str,
    evaluation: NoveltyReview | None = None,
) -> dict:
    criteria = {
        "baseline_consistent": baseline["passed"],
        "numerical_validation": numerical["passed"],
        "detectable_effect": effect["passed"],
        "independent_review_supports": review.decision == "supported"
        and backend in {"anyjev", "omnigent"},
        "literature_candidate_gap": literature.assessment == "candidate_gap",
        "multiple_sources_reviewed": len({e.source_id for e in literature.sources}) >= 2,
    }
    if evaluation is not None:
        criteria["reference_evaluator_supports"] = evaluation.verdict == "candidate_contribution"
    return {
        "met": all(criteria.values()),
        "criteria": criteria,
        "meaning": "Automated evidence gate within reviewed literature; no global discovery claim.",
        "scientific_novelty": "unverified",
    }


def discovery_transition(decision, gate, validation, review, remaining_rounds):
    """A specialist recommendation cannot bypass scientific or resource gates."""
    if gate["met"]:
        action, status, reason = "stop", "automated_candidate", "The bounded evidence gate is met."
    elif validation.decision == "reject":
        action, status, reason = (
            "stop",
            "validation_rejected",
            "Independent validation rejected the result.",
        )
    elif decision.action == "stop":
        action, status, reason = "stop", "research_stopped", decision.rationale
    elif (
        decision.action == "literature"
        or review.assessment != "candidate_gap"
        or len({e.source_id for e in review.sources}) < 2
    ):
        action, status, reason = (
            "literature",
            "needs_literature_review",
            ("More simulations cannot repair missing independent prior-art evidence."),
        )
    elif remaining_rounds <= 0:
        action, status, reason = "stop", "round_budget_exhausted", "No experimental rounds remain."
    else:
        action, status, reason = "repeat", "running", decision.rationale
    return {
        "requested_action": decision.action,
        "applied_action": action,
        "status": status,
        "reason": reason,
    }


def astrosat_summary(rows, config, batches):
    groups = ["fresh", "stale"]
    z = NormalDist().inv_cdf(1 - 0.05 / (8 * 3 * config.max_rounds * len(groups)))
    checks = []
    for group in groups:
        subset = [r for r in rows if r["scenario"] == group]
        positives = [r for r in subset if r["truth"]]
        negatives = [r for r in subset if not r["truth"]]
        if not positives or not negatives:
            return {"checks": [], "goal_eligible": False, "batches": batches}
        a = [not r["control_alert"] for r in positives]
        b = [not r["treatment_alert"] for r in positives]
        false_alerts = sum(r["treatment_alert"] for r in negatives) / len(negatives)
        extras = {
            "false_alert_rate": false_alerts,
            "control_false_alert_rate": sum(r["control_alert"] for r in negatives) / len(negatives),
            "positive_transits": len(positives),
            "negative_candidates": len(negatives),
        }
        aci, bci = (wilson(sum(a), len(a), z), wilson(sum(b), len(b), z))
        interval = [bci[0] - aci[1], bci[1] - aci[0]]
        resolved = interval[0] > config.minimum_effect or interval[1] < -config.minimum_effect
        equivalent = interval[0] >= -config.minimum_effect and interval[1] <= config.minimum_effect
        checks.append(
            {
                "scenario": str(group),
                "control": sum(a) / len(a),
                "treatment": sum(b) / len(b),
                "difference": sum(b) / len(b) - sum(a) / len(a),
                "difference_interval": interval,
                "interval_width": interval[1] - interval[0],
                "control_samples": len(a),
                "treatment_samples": len(b),
                "resolved": resolved or equivalent,
                "conclusion": "equivalent_within_threshold"
                if equivalent
                else "difference_detected"
                if resolved
                else "unresolved",
                **extras,
            }
        )
    return {
        "checks": checks,
        "batches": batches,
        "samples": len(rows),
        "goal_eligible": batches >= config.goal_min_batches
        and all(
            c["resolved"] and c["interval_width"] <= config.goal_max_interval_width for c in checks
        ),
        "metric": "missed-transit rate",
        "interval_method": (
            "Conservative Wilson endpoint bounds; Bonferroni across 3 branches, all "
            "planned batch looks, groups and endpoints. Paired covariance not exploited."
        ),
        "scientific_novelty": "unverified",
    }


def percolation_summary(rows, config, batches):
    groups = config.sizes
    z = NormalDist().inv_cdf(1 - 0.05 / (8 * 3 * config.max_rounds * len(groups)))
    checks = []
    for group in groups:
        subset = [r for r in rows if r["size"] == group]
        a = [r["wrap_x"] for r in subset if r["arm"] == "control"]
        b = [r["wrap_x"] for r in subset if r["arm"] == "treatment"]
        extras = {}
        aci, bci = (wilson(sum(a), len(a), z), wilson(sum(b), len(b), z))
        interval = [bci[0] - aci[1], bci[1] - aci[0]]
        resolved = interval[0] > config.minimum_effect or interval[1] < -config.minimum_effect
        equivalent = interval[0] >= -config.minimum_effect and interval[1] <= config.minimum_effect
        checks.append(
            {
                "scenario": str(group),
                "control": sum(a) / len(a),
                "treatment": sum(b) / len(b),
                "difference": sum(b) / len(b) - sum(a) / len(a),
                "difference_interval": interval,
                "interval_width": interval[1] - interval[0],
                "control_samples": len(a),
                "treatment_samples": len(b),
                "resolved": resolved or equivalent,
                "conclusion": "equivalent_within_threshold"
                if equivalent
                else "difference_detected"
                if resolved
                else "unresolved",
                **extras,
            }
        )
    return {
        "checks": checks,
        "batches": batches,
        "samples": len(rows),
        "goal_eligible": batches >= config.goal_min_batches
        and all(
            c["resolved"] and c["interval_width"] <= config.goal_max_interval_width for c in checks
        ),
        "metric": "horizontal wrapping rate",
        "interval_method": (
            "Conservative Wilson endpoint bounds; Bonferroni across 3 branches, all "
            "planned batch looks, groups and endpoints. Paired covariance not exploited."
        ),
        "scientific_novelty": "unverified",
    }


def summarize_branch(domain, rows, config, batches):
    if domain == "astrosat":
        return astrosat_summary(rows, config, batches)
    if domain == "percolation":
        return percolation_summary(rows, config, batches)
    raise ValueError("Unknown historical measurement schema")


def validate_process_variation(result):
    """Prevent scalar identities from being promoted as simulated processes."""
    displayed = [
        next(r for r in result["trials"] if r["arm"] == arm) for arm in ("control", "proposed")
    ]
    if all(
        np.allclose(row["output"]["values"], row["output"]["values"][0], rtol=1e-10, atol=1e-12)
        for row in displayed
    ):
        raise ValueError(
            "Both displayed trajectories are constant; "
            "retain as a diagnostic, not a process simulation"
        )


def process_from_trials(result, plan, *, provenance, artifact):
    """Map actual scalar trajectories to the shared player without a domain-specific model."""
    control = next(r for r in result["trials"] if r["arm"] == "control")
    proposed = next(r for r in result["trials"] if r["arm"] == "proposed")
    times = control["output"]["times"]
    if proposed["output"]["times"] != times:
        raise ValueError("Control and proposed trajectories must share recorded sample times")
    values = control["output"]["values"] + proposed["output"]["values"]
    trajectory_units = plan.trajectory_units or plan.units
    lo, hi = min(values), max(values)
    margin = max((hi - lo) * 0.08, 0.01)

    def world(row, label, color):
        values = row["output"]["values"]
        return {
            "label": label,
            "description": f"Recorded seed {row['seed']}: {row['parameters']}",
            "geometry": [
                {
                    "kind": "line",
                    "x": times[i - 1],
                    "y": values[i - 1],
                    "x2": times[i],
                    "y2": values[i],
                    "color": color,
                    "start": i,
                }
                for i in range(1, len(times))
            ],
            "frames": [
                {"caption": f"Step {step:g}: {value:g} {trajectory_units}", "glyphs": []}
                for step, value in zip(times, values, strict=True)
            ],
        }

    return checked_process(
        {
            "title": plan.trajectory_label or plan.metric,
            "description": "Recorded process samples from a paper-based implementation."
            if not provenance["repository_url"]
            else "Recorded process samples from the pinned repository experiment.",
            "x_label": "Recorded time / simulation step",
            "y_label": trajectory_units,
            "timeline_label": "Recorded time / simulation step",
            "times": times,
            "bounds": [times[0], times[-1], lo - margin, hi + margin],
            "original": world(control, "Original / control", "control"),
            "proposed": world(proposed, "Proposed", "proposed"),
            "selection": "First preregistered seed in each arm; all seeds are retained in "
            "raw trials.",
            "limitations": "A recorded scalar trajectory, not a spatial reconstruction. "
            + " ".join(plan.limitations),
            "replayed_trials": 0,
            "inputs": [{"artifact": artifact, "seed": control["seed"]}],
            "provenance": provenance,
        }
    )
