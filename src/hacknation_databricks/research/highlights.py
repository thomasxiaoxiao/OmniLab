"""Plain-language, deterministic interpretations of saved comparisons."""


def research_highlights(bundle: dict) -> dict:
    recipe = bundle.get("recipe", {})
    metric = bundle.get("metric", "recorded rate")
    astro = metric == "missed-transit rate"
    percolation = metric == "horizontal wrapping rate"
    sources = {s.get("url", "") for s in bundle.get("sources", [])}
    reference = None
    if percolation and "https://arxiv.org/abs/2607.24975v1" in sources:
        reference = {
            "url": "https://arxiv.org/abs/2607.24975v1",
            "location": "Tables I–II, p. 9; extension discussion, p. 2",
            "rate": 0.75001,
            "finding": "The paper estimates a 75.001% one-direction wrapping probability "
            "at each model's critical occupation probability in the infinite-size limit. "
            "For Manhattan, that critical probability is 0.697160. It conjectures similar "
            "critical behavior for other arrangements, including randomly oriented Manhattan. "
            "Its main simulations exclude two-way bonds; those are discussed as prior work.",
        }
    elif astro and "https://arxiv.org/abs/2111.11268v1" in sources:
        reference = {
            "url": "https://arxiv.org/abs/2111.11268v1",
            "location": "Section 2.1, Eq. 1, p. 2",
            "finding": "The paper uses a ±5-second search window for timing uncertainty. "
            "It estimates that 500 m of cross-track error corresponds to about 0.09° at "
            "335 km altitude and suggests expanding the field to account for this error. "
            "It does not report the missed-transit rates measured in this simulation.",
        }
    if astro:
        meaning = (
            "Missed-transit rate is the share of true simulated field crossings the "
            "search fails to flag. Lower is better for detection; false-alert rate measures "
            "how often non-crossings are unnecessarily flagged. Both matter."
        )
        change = (
            f"Keep the {recipe['field_diameter_deg']}° field "
            f"and ±{recipe['timing_window_seconds']} "
            f"second timing window; add a {recipe['margin_sigma']}-sigma spatial guard "
            "around the field. Sigma is the assumed cross-track error standard deviation."
            if all(
                k in recipe for k in ("field_diameter_deg", "timing_window_seconds", "margin_sigma")
            )
            else "The archived treatment parameters are unavailable."
        )
        implication = (
            "The useful result is the detection-versus-false-alert tradeoff. "
            "Compare guard widths and validate the assumed errors with observations before "
            "choosing an operational setting. Zero observed misses does not prove zero risk."
        )
    elif percolation:
        meaning = (
            "Horizontal wrapping rate is the share of simulated lattices where a "
            "strongly connected cluster loops around the horizontal periodic boundary. "
            "Every site in that cluster can reach every other along directed paths. "
            "Higher means wrapping is more frequent, not that the model is better."
        )
        names = {
            "manhattan": "alternating Manhattan directions",
            "random_manhattan": "randomized row and column directions",
            "random_diode": "random one-way bonds",
            "resistor_diode": "a mixture of one-way and two-way bonds",
        }
        change = (
            f"Compare {names.get(recipe['control'], recipe['control'])} (bond occupation) "
            f"with {names.get(recipe['model'], recipe['model'])} "
            f"({recipe.get('mode', 'unrecorded')} occupation), holding occupation probability "
            f"p = {recipe['p']} fixed."
            if all(k in recipe for k in ("control", "model", "p"))
            else "The archived treatment parameters are unavailable."
        )
        implication = (
            "This tests sensitivity to a changed lattice mechanism at fixed p. "
            "A difference can reflect a shifted critical threshold or finite-size effects. "
            "To test the paper's universality conjecture, estimate the follow-up's own "
            "critical threshold across larger sizes and compare scaling there."
        )
    else:
        meaning = (
            f"Recorded endpoint: {metric}. "
            "No validated plain-language metric definition is available."
        )
        change = recipe.get("question", "The archived treatment parameters are unavailable.")
        implication = "Interpret the result within the saved experiment and source evidence."
    if recipe.get("question"):
        change = recipe["question"] + " " + change
    rows = []
    for c in bundle.get("checks", []):
        delta = 100 * (c["treatment"] - c["control"])
        direction = "fewer" if delta < 0 else "more" if delta > 0 else "no change in"
        unit = (
            "misses per 100 true crossings"
            if astro
            else "wrapping lattices per 100 simulations"
            if percolation
            else "events per 100 trials"
        )
        interval = c.get("difference_interval")
        if interval is None:
            uncertainty = "Uncertainty unavailable; direction is not established."
        elif c.get("conclusion") == "equivalent_within_threshold":
            uncertainty = (
                "The recorded comparison is within the predeclared negligible-effect range; "
                "this does not establish identical behavior."
            )
        elif interval[0] <= 0 <= interval[1]:
            uncertainty = "The interval includes no change; the direction is not yet resolved."
        else:
            uncertainty = "The recorded interval excludes no change."
        rows.append(
            {
                "Scenario": f"{c['scenario']} × {c['scenario']} lattice"
                if percolation
                else c["scenario"],
                "Local original": f"{c['control']:.1%}",
                "Follow-up": f"{c['treatment']:.1%}",
                "What changed": f"{abs(delta):.1f} {direction} {unit}"
                if delta
                else f"No observed change in {unit}",
                "Uncertainty": (
                    f"{interval[0] * 100:+.1f} to {interval[1] * 100:+.1f} percentage points. "
                    if interval
                    else ""
                )
                + uncertainty,
                "Samples (original / follow-up)": (
                    f"{c.get('control_samples') or 'unrecorded'} / "
                    f"{c.get('treatment_samples') or 'unrecorded'}"
                ),
            }
        )
        if "false_alert_rate" in c:
            rows[-1]["False-alert tradeoff"] = (
                f"{c['control_false_alert_rate']:.1%} → {c['false_alert_rate']:.1%} "
                "of non-crossings "
                f"({100 * (c['false_alert_rate'] - c['control_false_alert_rate']):+.1f} "
                "percentage points; "
                f"n={c.get('negative_candidates', 'unrecorded')})."
            )
    return {
        "checkpoint": bundle.get("checkpoint"),
        "branch_id": bundle.get("branch_id"),
        "recipe_artifact": bundle.get("recipe_artifact"),
        "sources": bundle.get("sources", []),
        "reference": reference,
        "meaning": meaning,
        "change": change,
        "implication": implication,
        "rows": rows,
    }
