"""Allowlisted batch tools and predeclared, simultaneous evidence criteria.

Astrosat is a synthetic uncertainty sensitivity study, not an SGP4/TLE replay.
"""

import hashlib
import math
from statistics import NormalDist

import numpy as np

from .simulation import simulate, wilson

MEASUREMENT_CONTRACTS = {
    "astrosat": {
        "primary_endpoint": "Missed-transit rate: missed true crossings / positive_transits.",
        "false_alert_rate": "Treatment alerts among nontransits / negative_candidates.",
        "control_false_alert_rate": "Control alerts among nontransits / negative_candidates.",
        "denominator_warning": "False-alert rate is NOT false alerts / all alerts. The latter "
        "is false discovery proportion and is not the reported endpoint.",
        "comparison": "Treatment minus nominal control within each fresh/stale scenario. "
        "Control and treatment share candidates within a branch; different guard branches "
        "use independent candidate samples, not matched samples.",
        "hypothesis_scope": "The goal resolves each guard versus its nominal control. "
        "Guard-to-guard superiority and stale-versus-fresh differences are secondary "
        "questions not evaluated by this goal. Do not make either the primary hypothesis.",
        "interpretation": "Widening the guard nests the alert sets, so fewer misses and "
        "more false alerts are expected structurally. The measured magnitude and tradeoff "
        "are the useful result; no optimal margin or operational benefit is established.",
    },
    "percolation": {
        "primary_endpoint": "Horizontal strongly connected wrapping: wrapping trials / "
        "all trials, separately for each lattice size and arm.",
        "comparison": "Treatment minus fresh independent control at the recipe's fixed p.",
        "hypothesis_scope": "A finite-size, fixed-probability mechanism comparison. "
        "It does not estimate a critical probability or test a universality class.",
    },
}

ASTROSAT_RECIPES = {
    f"transit_margin_{k}": {
        "question": f"Does a {k}-sigma cross-track guard reduce missed field crossings?",
        "margin_sigma": k,
        "control": "Nominal field plus the paper's +/-5 second temporal search window",
        "scenarios": ["fresh", "stale"],
        "field_diameter_deg": 0.5,
        "altitude_km": 335.0,
        "exposure_seconds": 30.0,
        "timing_window_seconds": 5.0,
        "cross_track_sigma_km": 0.5,
        "in_track_sigma_km": {"fresh": 2.0, "stale": 25.0},
        "assumptions": "Independent Gaussian errors; the paper's quoted errors are treated as "
        "scenario standard deviations, which is an experimental assumption, not a paper claim. "
        "Uniform candidate midtimes and cross-track offsets around a 0.5-degree field. "
        "Straight-line, zenith, circular-orbit transit geometry; no brightness or SGP4.",
        "source": "arXiv:2111.11268v1, section 2.1 (page 2), equation 1",
    }
    for k in (1, 2, 3)
}


def seed_for(master: int, branch: str, batch: int, scenario: str = "") -> int:
    identity = f"{master}/{branch}/{batch}/{scenario}".encode()
    return int.from_bytes(hashlib.sha256(identity).digest()[:4], "big")


def transit_geometry(altitude_km=335.0, cross_track_km=0.5, in_track_km=2.0):
    speed = math.sqrt(398600.4418 / (6371.0 + altitude_km))
    return {
        "speed_km_s": speed,
        "angular_speed_deg_s": math.degrees(speed / altitude_km),
        "cross_track_deg": math.degrees(math.atan(cross_track_km / altitude_km)),
        "timing_error_seconds": in_track_km / speed,
    }


def astrosat_baseline():
    geometry = transit_geometry()
    stale = transit_geometry(in_track_km=25.0)
    checks = [
        {
            "quantity": "2 km timing error (s)",
            "measured": geometry["timing_error_seconds"],
            "reference": 0.27,
            "tolerance": 0.015,
        },
        {
            "quantity": "25 km timing error (s)",
            "measured": stale["timing_error_seconds"],
            "reference": 3.26,
            "tolerance": 0.03,
        },
        {
            "quantity": "500 m angular error (deg)",
            "measured": geometry["cross_track_deg"],
            "reference": 0.09,
            "tolerance": 0.01,
        },
    ]
    for check in checks:
        check["passed"] = abs(check["measured"] - check["reference"]) <= check["tolerance"]
    return {
        "passed": all(c["passed"] for c in checks),
        "checks": checks,
        "claim": "Equation-1 geometry consistency check against rounded published examples.",
        "limitation": "Does not reproduce the paper's historical satellite population or TLEs.",
        "numerical": {"passed": True, "seed_replays": 0},
    }


def transit_batch(recipe, trials, seed, consume, on_row=None):
    geometry = transit_geometry()
    sigma_y = geometry["cross_track_deg"]
    radius = recipe["field_diameter_deg"] / 2
    speed = geometry["angular_speed_deg_s"]
    rows = []
    for scenario, in_track in recipe["in_track_sigma_km"].items():
        scenario_seed = seed_for(seed, "transit", 0, scenario)
        rng = np.random.default_rng(scenario_seed)
        for trial in range(trials):
            consume()
            nominal_y = float(rng.uniform(-radius - 4 * sigma_y, radius + 4 * sigma_y))
            nominal_t = float(rng.uniform(-10, recipe["exposure_seconds"] + 10))
            true_y = nominal_y + float(rng.normal(0, sigma_y))
            true_t = nominal_t + float(rng.normal(0, in_track / geometry["speed_km_s"]))
            half_chord = math.sqrt(max(0.0, radius**2 - true_y**2)) / speed
            truth = (
                abs(true_y) <= radius
                and true_t + half_chord >= 0
                and (true_t - half_chord <= recipe["exposure_seconds"])
            )
            timing = (
                -recipe["timing_window_seconds"]
                <= nominal_t
                <= (recipe["exposure_seconds"] + recipe["timing_window_seconds"])
            )
            control = timing and abs(nominal_y) <= radius
            treatment = timing and abs(nominal_y) <= radius + recipe["margin_sigma"] * sigma_y
            rows.append(
                {
                    "scenario": scenario,
                    "seed": scenario_seed,
                    "trial": trial,
                    "nominal_y_deg": nominal_y,
                    "nominal_time_s": nominal_t,
                    "true_y_deg": true_y,
                    "true_time_s": true_t,
                    "truth": truth,
                    "control_alert": control,
                    "treatment_alert": treatment,
                }
            )
            if on_row:
                on_row(rows[-1])
    return rows


def batch_cost(domain, trials, sizes):
    return trials * (2 if domain == "astrosat" else 2 * len(sizes))


def execute_batch(domain, recipe, sizes, trials, seed, budget, on_row=None):
    if domain == "astrosat":
        return transit_batch(recipe, trials, seed, budget.consume, on_row)
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


def summarize_branch(domain, rows, config, batches):
    # A union bound over all three branches and every possible interim look,
    # both arms/endpoints, and all scenarios/sizes. Adaptive selection cannot
    # turn an ordinary per-look 95% interval into a repeated significance test.
    groups = ["fresh", "stale"] if domain == "astrosat" else config.sizes
    z = NormalDist().inv_cdf(1 - 0.05 / (8 * 3 * config.max_rounds * len(groups)))
    checks = []
    for group in groups:
        if domain == "astrosat":
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
                "control_false_alert_rate": sum(r["control_alert"] for r in negatives)
                / len(negatives),
                "positive_transits": len(positives),
                "negative_candidates": len(negatives),
            }
        else:
            subset = [r for r in rows if r["size"] == group]
            a = [r["wrap_x"] for r in subset if r["arm"] == "control"]
            b = [r["wrap_x"] for r in subset if r["arm"] == "treatment"]
            extras = {}
        aci, bci = wilson(sum(a), len(a), z), wilson(sum(b), len(b), z)
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
                else ("difference_detected" if resolved else "unresolved"),
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
        "metric": "missed-transit rate" if domain == "astrosat" else "horizontal wrapping rate",
        "interval_method": "Conservative Wilson endpoint bounds; Bonferroni across 3 branches, "
        "all planned batch looks, groups and endpoints. Paired covariance not exploited.",
        "scientific_novelty": "unverified",
    }


def audit_statistics(domain, rows, config):
    """Exact integer counts and simultaneous uncertainty for independent review."""
    groups = ["fresh", "stale"] if domain == "astrosat" else config.sizes
    z = NormalDist().inv_cdf(1 - 0.05 / (8 * 3 * config.max_rounds * len(groups)))
    result = []
    for group in groups:
        if domain == "astrosat":
            subset = [r for r in rows if r["scenario"] == group]
            table = []
            for truth in (False, True):
                denominator = sum(r["truth"] == truth for r in subset)
                for control in (False, True):
                    for treatment in (False, True):
                        table.append(
                            {
                                "truth": truth,
                                "control_alert": control,
                                "treatment_alert": treatment,
                                "count": sum(
                                    r["truth"] == truth
                                    and r["control_alert"] == control
                                    and r["treatment_alert"] == treatment
                                    for r in subset
                                ),
                            }
                        )
                for arm in ("control_alert", "treatment_alert"):
                    hits = sum(r["truth"] == truth and r[arm] for r in subset)
                    result.append(
                        {
                            "scenario": group,
                            "metric": "recall" if truth else "false_alert_rate",
                            "arm": arm,
                            "successes": hits,
                            "trials": denominator,
                            "simultaneous_interval": wilson(hits, denominator, z),
                        }
                    )
            result.append({"scenario": group, "paired_contingency_table": table})
        else:
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
