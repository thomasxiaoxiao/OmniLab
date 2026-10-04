"""Percolation implementation; isolated from other experiment families."""

from statistics import NormalDist

from .scientific_statistics import seed_for, wilson
from .simulation import simulate

MEASUREMENT_CONTRACT = {
    "primary_endpoint": (
        "Horizontal strongly connected wrapping: wrapping trials / all trials, "
        "separately for each lattice size and arm."
    ),
    "comparison": "Treatment minus fresh independent control at the recipe's fixed p.",
    "hypothesis_scope": (
        "A finite-size, fixed-probability mechanism comparison. It does not estimate "
        "a critical probability or test a universality class."
    ),
}


def batch_cost(trials, sizes):
    return trials * (2 * len(sizes))


def execute_batch(recipe, sizes, trials, seed, budget, on_row=None):
    rows = []
    for size in sizes:
        for arm, model, mode in (
            ("control", recipe["control"], "bond"),
            ("treatment", recipe["model"], recipe["mode"]),
        ):
            for row in simulate(
                model,
                mode,
                size,
                recipe["p"],
                trials,
                seed_for(seed, arm, 0),
                check_budget=budget.consume,
                on_trial=(lambda row, arm=arm: on_row({**row, "arm": arm})) if on_row else None,
            ):
                rows.append({**row, "arm": arm})
    return rows


def summarize_branch(rows, config, batches):
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


def audit_statistics(rows, config):
    """Exact integer counts and simultaneous uncertainty for independent review."""
    groups = config.sizes
    z = NormalDist().inv_cdf(1 - 0.05 / (8 * 3 * config.max_rounds * len(groups)))
    result = []
    for group in groups:
        for arm in ("control", "treatment"):
            subset = [r for r in rows if r["size"] == group and r["arm"] == arm]
            hits = sum(r["wrap_x"] for r in subset)
            result.append(
                {
                    "size": group,
                    "arm": arm,
                    "wrapping_count": hits,
                    "trials": len(subset),
                    "simultaneous_interval": wilson(hits, len(subset), z),
                }
            )
    return {
        "family_alpha": 0.05,
        "planned_branches": 3,
        "planned_looks_per_branch": config.max_rounds,
        "groups": groups,
        "endpoint_count_per_group": 4,
        "z": z,
        "statistics": result,
    }
