"""Visualization-first results for generated, repository-derived experiments."""

import json

from hacknation_databricks.web import components as ui

from .research.process_player import process_html
from .research.process_visualization import checked_process
from .research_routes_ui import render_research_routes
from .research_views import next_experiment_summary, saved_json
from .run_feedback_ui import render_run_outcome
from .seed_catalog import source_display_name
from .tracking import MAX_ARTIFACT_DOWNLOAD_BYTES, read_artifact


def brief(text, limit=360):
    """Keep the overview readable; the complete evaluator decision is expandable below."""
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0] + "…"


def render_repository_result(journal):
    report = journal.report
    rounds = report.get("rounds", [])
    sources = saved_json(journal, "sources.json") or []
    seed = next((s for s in sources if s.get("source_id") == "seed"), {})
    ui.caption(source_display_name(seed))
    if report.get("code_origin") == "paper_implementation":
        ui.caption(
            "This run builds its experiment from the paper. No author repository is supplied."
        )
    row = final_experiment(report) if journal.sealed else None
    if row:
        ui.caption(f"Final experiment · {len(rounds)} completed comparisons in this run")
        envelope = saved_json(journal, row["artifact_prefix"] + "/process.json")
        if envelope and envelope.get("status") == "ready":
            process = checked_process(envelope["process"])
            agent_scene = report.get("process_validation") == "agent_recorded_scene_v1"
            plan = saved_json(journal, "planner.json") or {}
            baseline = plan.get("baseline", {})
            treatment = row.get("treatment", {})
            changed = [key for key in treatment if treatment[key] != baseline.get(key)]
            render_scenario_comparison(plan, treatment, process)
            process["provenance"]["recorded_parameters"] = {
                "control": baseline,
                "proposed": treatment,
            }
            process["provenance"]["pre_experiment_limitations"] = process["limitations"]
            if agent_scene:
                process["description"] += " Scope notes below were recorded before code execution."
            if not agent_scene:
                for arm, parameters in [("original", baseline), ("proposed", treatment)]:
                    process[arm]["description"] = brief(
                        " · ".join(
                            f"{key.replace('_', ' ')}: {parameters.get(key)}" for key in changed
                        )
                        or "Recorded experiment samples",
                        limit=180,
                    )
            graphic = process_html(process, scalar_axes=not agent_scene)
            ui.iframe(
                graphic,
                height="content",
                alt="Recorded control and proposed simulation scenes",
            )
        else:
            ui.warning(
                (envelope or {}).get("reason", "The agent has not produced a visualization.")
            )
        summary = row["summary"]
        ui.markdown("**Result**")
        metric = summary["metric"].partition(":")[0]
        numerical_summary = (
            f"{metric}: {summary['control_mean']:.4g} → {summary['proposed_mean']:.4g} "
            f"{summary['units']}. Difference: {summary['difference']:+.4g}."
        )
        plan = saved_json(journal, "planner.json") or {}
        raw = None
        if plan.get("trajectory_units") and plan["trajectory_units"] != summary["units"]:
            try:
                raw = saved_json(journal, row["artifact_prefix"] + "/trials.json")
            except ValueError:
                ui.caption("Large trajectory details remain available in the raw-trials download.")
        if raw:
            values = next(r["output"]["values"] for r in raw["trials"] if r["arm"] == "proposed")
            ui.write(
                f"{plan.get('trajectory_label') or 'Recorded proposed trajectory'}: "
                f"{min(values):.4g} to {max(values):.4g} {plan['trajectory_units']} "
                f"across the displayed window (span {max(values) - min(values):.4g} "
                f"{plan['trajectory_units']})."
            )
        ui.write(numerical_summary)
        ui.caption(
            f"{summary['samples_per_arm']} paired seeds per arm · "
            f"preregistered meaningful difference: {summary['meaningful_difference']:.4g} "
            f"{summary['units']}."
        )
        if summary["interval"][0] == summary["interval"][1]:
            ui.caption(
                "Deterministic repeated result; these repetitions do not estimate uncertainty."
            )
        else:
            ui.caption(
                f"Exploratory 95% interval for the summary difference: "
                f"{summary['interval'][0]:+.4g} to {summary['interval'][1]:+.4g} "
                f"{summary['units']}."
            )
        decision = row.get("next_decision", {})
        assessment = saved_json(journal, row["artifact_prefix"] + "/assessment.json")
        ui.markdown("**What changed**")
        ui.write(
            decision.get("result_interpretation", "The evaluator has not returned a decision yet.")
        )
        ui.markdown("**Why the agents continued or stopped**")
        if assessment:
            ui.caption("Researcher interpretation and proposal · Codex through Omnigent")
            ui.write(assessment["rationale"])
            ui.caption("Final action · decision-only AnyJev evaluator")
        ui.write(decision.get("rationale", "Awaiting the evaluator."))
        ui.markdown("**Next experiment**")
        next_experiment = decision.get("next_experiment", "Awaiting the evaluator.")
        ui.write(next_experiment_summary(next_experiment))
        if next_experiment_summary(next_experiment) != next_experiment:
            with ui.expander("Full recorded next experiment"):
                ui.write(next_experiment)
        ui.markdown("**Research question & experimental design**")
        reader = saved_json(journal, "approved_reader.json") or {}
        ui.write(reader.get("research_question", plan.get("hypothesis", "")))
        ui.write(plan.get("hypothesis", ""))
        ui.write(plan.get("baseline_scope", ""))
        ui.write(plan.get("controls", ""))
        if plan.get("visualization_plan"):
            ui.markdown("**Why this visualization**")
            ui.write(plan["visualization_plan"])
            for option in plan.get("visualization_options", []):
                ui.write(option)
        ui.markdown("**What remains uncertain**")
        for limitation in decision.get("limitations", plan.get("limitations", [])):
            ui.write(limitation)
        if decision:
            executed = any(r["round"] > row["round"] for r in rounds)
            ui.caption(
                "Follow-up executed in the next experiment."
                if executed
                else "Proposed next step; no later experiment is recorded."
            )
        with ui.expander("Download visualization and raw measurements"):
            if envelope and envelope.get("status") == "ready":
                ui.download_button(
                    "Download playable simulation",
                    graphic,
                    file_name=f"{journal.run_id}-process.html",
                    mime="text/html",
                )
            ui.write(numerical_summary)
            try:
                # Downloads retain exact sealed bytes. Large evidence need not be parsed
                # or squeezed into the separate 20 MiB structured-preview budget.
                trial_bytes = read_artifact(
                    journal.directory,
                    row["artifact_prefix"] + "/trials.json",
                    max_bytes=MAX_ARTIFACT_DOWNLOAD_BYTES,
                )
            except (OSError, ValueError):
                ui.warning(
                    "Raw trials exceed the download limit or are unavailable; "
                    "inspect the saved run directory."
                )
            else:
                ui.download_button(
                    "Download raw trials",
                    trial_bytes,
                    file_name=f"{journal.run_id}-trials.json",
                    mime="application/json",
                )
            ui.write(summary["interval_method"])
    else:
        ui.info(
            "No final experiment is ready. The run must finish with validated measurements "
            "and an evaluator decision before a result is highlighted."
        )
    render_run_outcome(journal)
    render_research_routes(journal)
    repository = report.get("repository", {})
    if repository:
        ui.caption(
            f"Source: {repository['url']} · commit {repository['commit'][:12]} · "
            f"{repository['origin'].replace('_', ' ')}"
        )
    with ui.expander("Paper evidence, plan, and generated code"):
        for name in [
            "approved_reader.json",
            "approved_literature.json",
            "approved_critic.json",
            "planner.json",
            "implementation.json",
        ]:
            value = saved_json(journal, name)
            if value:
                ui.markdown(f"**{name}**")
                ui.json(value, expanded=False)
        if row and row.get("next_decision"):
            assessment = saved_json(journal, row["artifact_prefix"] + "/assessment.json")
            if assessment:
                ui.markdown("**Researcher's assessment and proposal**")
                ui.json(assessment, expanded=False)
            ui.markdown("**Evaluator's full decision**")
            ui.json(row["next_decision"], expanded=False)
        ui.caption(
            "Limited computational check; scientific novelty and real-world "
            "validity are unverified."
        )
    with ui.expander("Execution limits, uncertainty, and timing"):
        ui.json(saved_json(journal, "capability.json"), expanded=False)
        if row:
            execution = saved_json(journal, row["artifact_prefix"] + "/execution.json") or {}
            ui.write(execution.get("memory_limit_note", "Memory limit unrecorded"))
        ui.write(report.get("acceleration", {}))
        ui.write(
            f"{report.get('computed_simulations', 0)} requested simulations "
            "including sanity checks and replays; "
            f"{report.get('elapsed_seconds', 0):.1f} seconds elapsed."
        )
    earlier = [r for r in rounds if r is not row]
    if earlier:
        with ui.expander("Earlier experiments · audit history"):
            ui.dataframe(
                [
                    {
                        "Experiment": r["round"],
                        "Metric": r["summary"]["metric"],
                        "Difference": r["summary"]["difference"],
                        "Changed parameters": "; ".join(
                            f"{k.replace('_', ' ')}={v}"
                            for k, v in r.get("treatment", {}).items()
                            if v != plan.get("baseline", {}).get(k)
                        ),
                        "Decision": r.get("next_decision", {}).get("action", "Pending"),
                    }
                    for r in earlier
                ],
                hide_index=True,
                alt="Intermediate experiment measurements and decisions",
            )
            ui.caption(
                "Intermediate measurements are retained here; "
                "only the final experiment is featured above."
            )


def final_experiment(report):
    """One terminal evaluated experiment, never a running or failed partial result."""
    rounds = report.get("rounds", [])
    if report.get("status") not in {"research_stopped", "budget_exhausted"} or not rounds:
        return None
    last = rounds[-1]
    if not last.get("next_decision"):
        return None
    if report.get("final_experiment", last["round"]) != last["round"]:
        return None
    return last


def render_scenario_comparison(plan, treatment, process):
    baseline = plan.get("baseline", {})
    comparison = plan.get("comparison") or {}
    ui.markdown("**How the scenarios differ**")
    if comparison:
        ui.write(comparison["difference"])
        ui.caption("Held constant: " + comparison["held_constant"])
    changed = [
        {
            "Parameter": key.replace("_", " "),
            "Baseline": json.dumps(baseline.get(key), ensure_ascii=False),
            "Proposed": json.dumps(value, ensure_ascii=False),
        }
        for key, value in treatment.items()
        if value != baseline.get(key)
    ]
    if changed:
        ui.dataframe(changed, hide_index=True, alt="Actual changed simulation parameters")
    times = process["times"]
    ui.caption(
        f"Recorded range · {process['timeline_label']}: {times[0]:g} to {times[-1]:g} · "
        f"{len(times)} computed frames. Press Play or move the slider to inspect the sweep."
    )
    if plan.get("history_difference"):
        with ui.expander("Why this experiment was selected"):
            ui.write(plan["history_difference"])
