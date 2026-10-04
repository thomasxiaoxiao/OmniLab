"""Deterministic comparison deliverables from recorded measurements, never model prose."""

import json
import textwrap
import time
from html import escape


def synthesis_dataset(report: dict) -> dict | None:
    rounds = report.get("rounds", [])
    if not rounds:
        return None
    accepted = next(
        (c for c in reversed(report.get("checkpoints", [])) if c.get("goal_accepted")), None
    )
    branch = report.get("goal", {}).get("branch_id")
    if accepted:
        branch = accepted.get("decision", {}).get("goal_branch_id") or branch
        eligible = [r for r in rounds if r["round"] <= accepted["checkpoint"]]
        return next(
            (r for r in reversed(eligible) if not branch or r.get("branch_id") == branch), None
        )
    if branch:
        return next((r for r in reversed(rounds) if r.get("branch_id") == branch), None)
    return rounds[-1]


def comparison_bundle(report, config, sources, read_json, dataset=None):
    """Use saved recipes, not today's catalog, when interpreting historical runs."""
    dataset = dataset if dataset is not None else synthesis_dataset(report)
    branch = (dataset or {}).get("branch_id", "follow-up")
    proposal = report.get("branches", {}).get(branch, {}).get("proposal") or report.get(
        "selected_proposal", {}
    )
    recipe, recipe_path = {}, None
    if dataset:
        if "branch_id" in dataset:
            recipe_path = f"branches/{branch}/batches/{dataset['batch']:02d}/specification.json"
            recipe = (read_json(recipe_path) or {}).get("recipe", {})
        else:
            recipe_path = f"rounds/{dataset['round']:02d}/experiment.json"
            recipe = read_json(recipe_path) or {}
    effect = (dataset or {}).get("effect", {})
    domain = report.get("domain", config.get("domain", "percolation"))
    metric = effect.get(
        "metric", "horizontal wrapping rate" if domain == "percolation" else "recorded metric"
    )
    checks = []
    for check in effect.get("checks", []):
        interval = check.get("difference_interval")
        if interval is None and check.get("control_interval") and check.get("treatment_interval"):
            interval = [
                check["treatment_interval"][0] - check["control_interval"][1],
                check["treatment_interval"][1] - check["control_interval"][0],
            ]
        checks.append(
            {
                **check,
                "scenario": str(check.get("scenario", check.get("size", "All"))),
                "difference_interval": interval,
                "control_samples": check.get("control_samples", dataset.get("trials_per_size")),
                "treatment_samples": check.get("treatment_samples", dataset.get("trials_per_size")),
            }
        )
    parts = []
    for c in checks:
        part = (
            f"{c['scenario']}: {c['control']:.2%} → {c['treatment']:.2%} "
            f"({c['difference'] * 100:+.2f} percentage points"
        )
        if c["difference_interval"]:
            low, high = c["difference_interval"]
            part += f", recorded interval {low * 100:+.2f} to {high * 100:+.2f} points"
        part += ")"
        if "false_alert_rate" in c:
            part += (
                f", false alerts {c['control_false_alert_rate']:.2%} → "
                f"{c['false_alert_rate']:.2%} "
                f"({100 * (c['false_alert_rate'] - c['control_false_alert_rate']):+.2f} points)"
            )
        parts.append(part)
    summary = (
        f"In the recorded simulation, proposed versus original {metric} was "
        + "; ".join(parts)
        + "."
        if parts
        else "No completed original-versus-proposed measurements are available; "
        "the numerical difference is unavailable."
    )
    evidence = proposal.get("evidence", [])
    evidence = evidence if isinstance(evidence, list) else [evidence]
    scope = (
        "Synthetic sensitivity study; no historical satellite forecast or observational validation."
        if domain == "astrosat"
        else "Finite-size simulation at fixed parameters; "
        "no full-paper reproduction or universality claim."
        if domain == "percolation"
        else "Scoped simulation only; scientific and real-world validity "
        "require independent validation."
    )
    result = {
        "schema_version": 1,
        "domain": domain,
        "status": "measured" if checks else "unavailable",
        "run_status": report.get("status", "unrecorded"),
        "branch_id": branch if dataset else None,
        "checkpoint": (dataset or {}).get("round"),
        "batch": (dataset or {}).get("batch"),
        "proposal": proposal,
        "recipe": recipe,
        "recipe_artifact": recipe_path,
        "master_seed": config.get("seed"),
        "sizes": config.get("sizes"),
        "metric": metric,
        "checks": checks,
        "summary": summary,
        "interval_method": effect.get("interval_method", "Not recorded"),
        "scope": scope,
        "sources": [
            {k: s.get(k) for k in ("source_id", "title", "url", "sha256")} for s in sources
        ],
        "evidence": evidence,
        "provenance": "Derived from saved report measurements and experiment specification; "
        "original denotes the local control, not published numerical results.",
    }
    return result


def comparison_svg(bundle: dict) -> str:
    """Portable, escaped vector plot with identical 0–100% scales for both arms."""
    lines = []
    y = 38

    def text(value, *, x=30, size=15, color="#334155"):
        nonlocal y
        lines.append(
            f'<text x="{x}" y="{y}" font-size="{size}" fill="{color}">{escape(str(value))}</text>'
        )
        y += size + 9

    def paragraph(value, size=14):
        for line in textwrap.wrap(str(value), 110):
            text(line, size=size)

    text("Original vs proposed · simulation results", size=25, color="#0f172a")
    paragraph(
        f"{bundle['branch_id'] or 'No dataset'} · checkpoint {bundle['checkpoint']} · "
        f"{bundle['metric']} · run: {bundle['run_status']}"
    )
    recipe = bundle["recipe"]
    if recipe:
        if "margin_sigma" in recipe:
            paragraph(
                f"Original: nominal {recipe['field_diameter_deg']}° field; proposed: "
                f"+{recipe['margin_sigma']}σ cross-track guard; both: "
                f"±{recipe['timing_window_seconds']} s timing window."
            )
        else:
            paragraph(
                f"Original: {recipe.get('control')} / bond; proposed: {recipe.get('model')} / "
                f"{recipe.get('mode')}; both p={recipe.get('p')}."
            )
    else:
        paragraph("Historical experiment parameters not available in this artifact set.")
    y += 15
    for c in bundle["checks"]:
        text(f"Scenario {c['scenario']} · {bundle['metric']}", size=17, color="#0f172a")
        for label, rate, count, color in (
            ("Original", c["control"], c["control_samples"], "#64748b"),
            ("Proposed", c["treatment"], c["treatment_samples"], "#0f766e"),
        ):
            lines.append(f'<rect x="145" y="{y - 15}" width="590" height="21" fill="#f1f5f9"/>')
            lines.append(
                f'<rect x="145" y="{y - 15}" width="{590 * rate:.3f}" height="21" fill="{color}"/>'
            )
            lines.append(
                f'<text x="750" y="{y}" font-size="15" fill="#334155">'
                f"{rate:.2%} · n={escape(str(count if count is not None else 'unrecorded'))}</text>"
            )
            text(label)
        for x, value in ((145, "0%"), (400, "Same scale"), (706, "100%")):
            lines.append(f'<text x="{x}" y="{y}" font-size="11">{value}</text>')
        y += 24
        interval = c["difference_interval"]
        bounds = (
            f" · interval [{100 * interval[0]:+.2f}, {100 * interval[1]:+.2f}] points"
            if interval
            else " · interval not recorded"
        )
        text(f"Difference: {100 * c['difference']:+.2f} percentage points{bounds}")
        text(
            c.get("conclusion", "Threshold met" if c.get("passed") else "Inconclusive").replace(
                "_", " "
            ),
            size=13,
        )
        if "false_alert_rate" in c:
            text(
                f"False-alert tradeoff: {c['control_false_alert_rate']:.2%} "
                f"→ {c['false_alert_rate']:.2%} "
                f"· non-transit candidates n={c.get('negative_candidates', 'unrecorded')}",
                size=14,
            )
        y += 18
    if not bundle["checks"]:
        paragraph(bundle["summary"])
        y += 20
    paragraph(bundle["scope"])
    paragraph(bundle["interval_method"], size=12)
    paragraph("Original = local simulated control; proposed = implemented follow-up.", size=12)
    paragraph(
        "Source inputs: "
        + "; ".join(s.get("url") or s.get("title") or s["source_id"] for s in bundle["sources"]),
        size=12,
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 980 {y + 16}" '
        'role="img" aria-label="Original versus proposed simulation comparison" '
        'font-family="Arial, sans-serif"><rect width="100%" height="100%" fill="white"/>'
        + "".join(lines)
        + "</svg>"
    )


def save_comparisons(store, report, config, sources, *, process_builder=None):
    """Enforce and seal process + numerical comparisons at every terminal path."""
    from .process_player import process_html
    from .process_visualization import build_process, enforce_process_output

    def read_json(name):
        path = store.directory / name
        return json.loads(path.read_text()) if path.is_file() else None

    outputs, prepared, processes = {}, {}, {}
    started = time.monotonic()
    for dataset in [*report.get("rounds", []), None]:
        prefix = f"comparisons/{dataset['round']:03d}" if dataset else "comparison"
        bundle = comparison_bundle(report, config, sources, read_json, dataset)
        checkpoint = bundle["checkpoint"]
        if checkpoint not in processes:
            processes[checkpoint] = (process_builder or build_process)(
                bundle,
                lambda name: (store.directory / name).read_bytes(),
                run_id=store.directory.name,
            )
        process = processes[checkpoint]
        prepared[prefix] = bundle, process
        outputs[prefix] = {
            "highlight": f"{prefix}/highlights.json",
            "visualization": f"{prefix}/simulation.svg",
            "summary": f"{prefix}/summary.txt",
            "measurements": f"{prefix}/comparison.json",
            "status": bundle["status"],
            "process_status": process["status"],
            "process_data": f"{prefix}/process.json",
            "process_visualization": f"{prefix}/process.html"
            if process["status"] == "ready"
            else None,
        }
    enforce_process_output(report, outputs)
    for prefix, (bundle, process) in prepared.items():
        from .highlights import research_highlights

        bundle["run_status"] = report["status"]
        store.write(f"{prefix}/highlights.json", research_highlights(bundle))
        store.write(f"{prefix}/comparison.json", bundle)
        store.write_text(f"{prefix}/simulation.svg", comparison_svg(bundle))
        store.write_text(f"{prefix}/summary.txt", bundle["summary"] + "\n")
        # Compact states stay within the viewer's artifact-size limit even for
        # large lattice geometry. The ordinary report remains human-readable.
        store.write_text(
            f"{prefix}/process.json", json.dumps(process, allow_nan=False, separators=(",", ":"))
        )
        if process["status"] == "ready":
            store.write_text(f"{prefix}/process.html", process_html(process["process"]))
    report["comparison_artifacts"] = outputs
    report["visualization_compute"] = {
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "replayed_trials": sum(
            p.get("process", {}).get("replayed_trials", 0) for p in processes.values()
        ),
        "new_statistical_trials": 0,
        "scope": "Bounded rendering/reconstruction of saved trials; "
        "separate from research sampling.",
    }
