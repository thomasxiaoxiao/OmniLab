"""Visualization-first results for generated, repository-derived experiments."""

import json

from hacknation_databricks.web import components as ui

from .research.process_player import process_html
from .research.process_visualization import checked_process
from .research_views import saved_json
from .run_feedback_ui import render_run_outcome


def brief(text, limit=360):
    """Keep the overview readable; the complete evaluator decision is expandable below."""
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0] + "…"


def render_repository_result(journal):
    report = journal.report
    rounds = report.get("rounds", [])
    row = final_experiment(report) if journal.sealed else None
    if row:
        envelope = saved_json(journal, row["artifact_prefix"] + "/process.json")
        if envelope and envelope.get("status") == "ready":
            process = checked_process(envelope["process"])
            process["title"] = process["title"].partition(":")[0]
            plan = saved_json(journal, "planner.json") or {}
            baseline = plan.get("baseline", {})
            treatment = row.get("treatment", {})
            changed = [key for key in treatment if treatment[key] != baseline.get(key)]
            process["provenance"]["recorded_parameters"] = {
                "control": baseline,
                "proposed": treatment,
            }
            process["provenance"]["pre_experiment_limitations"] = process["limitations"]
            for arm, parameters in [("original", baseline), ("proposed", treatment)]:
                process[arm]["description"] = brief(
                    " · ".join(f"{key.replace('_', ' ')}: {parameters.get(key)}" for key in changed)
                    or "Recorded experiment samples",
                    limit=180,
                )
            process["limitations"] = (
                "Recorded scalar samples from one seed per arm. This is a scoped code check; "
                "full paper reproduction and physical validation remain unverified."
            )
            graphic = process_html(process, scalar_axes=True)
            ui.iframe(
                graphic,
                height="content",
                alt="Recorded original and proposed repository simulation trajectories",
            )
        summary = row["summary"]
        ui.markdown("**Result**")
        metric = summary["metric"].partition(":")[0]
        numerical_summary = (
            f"{metric}: {summary['control_mean']:.4g} → {summary['proposed_mean']:.4g} "
            f"{summary['units']}. Difference: {summary['difference']:+.4g}."
        )
        raw = saved_json(journal, row["artifact_prefix"] + "/trials.json")
        plan = saved_json(journal, "planner.json") or {}
        if raw and plan.get("trajectory_units") and plan["trajectory_units"] != summary["units"]:
            values = next(r["output"]["values"] for r in raw["trials"] if r["arm"] == "proposed")
            ui.write(
                f"{plan.get('trajectory_label') or 'Recorded proposed trajectory'}: "
                f"{min(values):.4g} to {max(values):.4g} {plan['trajectory_units']} "
                f"across the displayed window (span {max(values) - min(values):.4g} "
                f"{plan['trajectory_units']})."
            )
        else:
            ui.write(numerical_summary)
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
        ui.markdown("**What changed**")
        ui.write(
            brief(
                decision.get(
                    "result_interpretation", "The evaluator has not returned a decision yet."
                )
            )
        )
        ui.markdown("**Next experiment**")
        ui.write(brief(decision.get("next_experiment", "Awaiting the evaluator.")))
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
            ui.download_button(
                "Download raw trials",
                json.dumps(raw, indent=2),
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
    repository = report.get("repository", {})
    if repository:
        ui.caption(
            f"Source: {repository['url']} · commit {repository['commit'][:12]} · "
            f"{repository['origin'].replace('_', ' ')}"
        )
    with ui.expander("Paper evidence, plan, and generated code"):
        for name in [
            "approved_reader.json",
            "approved_critic.json",
            "planner.json",
            "implementation.json",
        ]:
            value = saved_json(journal, name)
            if value:
                ui.markdown(f"**{name}**")
                ui.json(value, expanded=False)
        if row and row.get("next_decision"):
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
