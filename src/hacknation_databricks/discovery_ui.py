"""Scientific loop overview backed exclusively by saved, verified evidence."""

import json

from hacknation_databricks.checkpoint_ui import render_checkpoint_story
from hacknation_databricks.tracking import Journal, read_artifact
from hacknation_databricks.web import components as ui


def render_discovery(journal: Journal) -> None:
    report = journal.report
    if not report.get("proposals") and (journal.directory / "paper_briefs.json").is_file():
        briefs = json.loads(read_artifact(journal.directory, "paper_briefs.json"))
        brief = briefs.get("seed", {})
        ui.subheader("Paper-derived research directions")
        ui.write(brief.get("research_question", "Research question not yet recorded"))
        ui.caption("Unexecuted hypotheses derived before implementation selection.")
        for direction in brief.get("directions", []):
            with ui.container(border=True):
                ui.markdown(f"**{direction['title']}**")
                ui.write(direction["hypothesis"])
                ui.caption(direction["origin"].replace("_", " "))
                for evidence in direction["evidence"]:
                    ui.caption(f"{evidence['source_id']} · page {evidence['page']}")
                    ui.text(evidence["quote"])
    if report.get("status") == "unsupported_source":
        ui.caption("No experiment or result-driven follow-up was executed in this run.")
        return
    if report.get("workflow_version") == "4":
        render_portfolio(journal)
        return
    from hacknation_databricks.synthesis_ui import render_comparison_outputs

    ui.subheader("What changed our next move?")
    render_comparison_outputs(journal, None)
    ui.subheader("Question → evidence → experiment → next decision")
    proposal = report.get("selected_proposal", {})
    ui.markdown(
        f"**Research question:** {proposal.get('hypothesis', 'Awaiting a reviewed hypothesis')}"
    )
    if proposal.get("evidence"):
        evidence = proposal["evidence"]
        ui.caption(f"Source: {evidence['source_id']} · page {evidence['page']}")
        ui.text(evidence["quote"])
    if report.get("backend") != "omnigent":
        ui.info("Auxiliary run: this is not evidence of a live Omnigent discovery loop.")
    ui.caption("Hypotheses and agent assessments are provisional; global novelty is unverified.")
    acceleration = report.get("acceleration", {})
    columns = ui.columns(3)
    columns[0].metric("Recorded elapsed time", f"{report.get('elapsed_seconds', 'Unrecorded')} s")
    columns[1].metric("Computed simulations", report.get("computed_simulations", 0))
    columns[2].metric("Acceleration multiplier", "Unverified")
    ui.caption(acceleration.get("status", "No comparable manual baseline measured"))
    ui.markdown(
        "**Experimenter:** bounded Python simulation tools, coordinated by the supervisor. "
        "Agent sessions select and review tests; they do not execute generated code."
    )
    for item in report.get("rounds", []):
        number = item["round"]
        with ui.container(border=True):
            ui.subheader(f"Discovery round {number}")
            plan_path = f"rounds/{number:02d}/plan.json"
            if (journal.directory / plan_path).is_file():
                plan = json.loads(read_artifact(journal.directory, plan_path))
                options_path = f"rounds/{number:02d}/test_options.json"
                options = (
                    json.loads(read_artifact(journal.directory, options_path))
                    if (journal.directory / options_path).is_file()
                    else {}
                )
                if plan.get("tests"):
                    columns = ui.columns(2)
                    for column, test in zip(columns, plan["tests"], strict=True):
                        with column, ui.container(border=True):
                            option = options.get(test["test_id"], {})
                            selected = test["test_id"] == plan["selected_test_id"]
                            ui.markdown(
                                f"**{test['test_id'].capitalize()}"
                                f"{' · selected' if selected else ''}**"
                            )
                            ui.caption(
                                f"{option.get('trials_per_size', '?')} trials / size · "
                                f"{option.get('simulation_cost', '?')} simulation units"
                            )
                            ui.write(test["expected_learning"])
                            with ui.expander("Feasibility and cost"):
                                ui.write(test["feasibility"])
                with ui.expander("Why this test was selected"):
                    ui.write(plan["rationale"])
            ui.markdown(f"**Result:** {item['trials_per_size']} trials per lattice size")
            ui.dataframe(item["effect"].get("checks", []), hide_index=True, width="stretch")
            decision = item.get("next_decision")
            if decision:
                ui.markdown(f"**Recommended action: {decision['action']}**")
                transition = item.get("transition")
                if transition:
                    ui.markdown(f"**Supervisor action: {transition['applied_action']}**")
                    ui.caption(transition["reason"])
                else:
                    ui.caption(f"Recorded run status: {report['status']}")
                ui.write(decision["result_interpretation"])
                with ui.expander("Decision rationale and proposed next experiment"):
                    ui.write(decision["rationale"])
                    ui.markdown(f"**Next experiment:** {decision['next_experiment']}")
            else:
                ui.info("This older run has no structured result-driven next decision.")
    if not report.get("rounds"):
        ui.info(
            "No experimental result yet. The workflow retains partial evidence if a stage stops."
        )


def render_portfolio(journal: Journal) -> None:
    import altair as alt
    import pandas as pd

    report, goal = journal.report, journal.report["goal"]
    render_checkpoint_story(journal)
    ui.divider()
    ui.subheader("Parallel research, continuous decisions")
    ui.write(goal["description"])
    ui.caption(
        f"{journal.config['max_rounds']} batches per direction · "
        f"{journal.config['max_workers']} concurrent workers · fresh seed streams per batch"
    )
    cols = ui.columns(4)
    cols[0].metric("Goal", "Achieved" if goal["achieved"] else "Open")
    cols[1].metric("Research branches", len(report.get("branches", {})))
    cols[2].metric("Decision checkpoints", len(report.get("checkpoints", [])))
    cols[3].metric("Computed simulations", report.get("computed_simulations", 0))
    ui.caption(
        f"Finish criterion: ≥{goal['minimum_batches']} independent batches, interval width "
        f"≤{goal['maximum_interval_width']}, "
        f"resolved effect at threshold {goal['minimum_effect']}, "
        "and independent validation. Budget exhaustion is not goal completion."
    )
    if report.get("domain") == "astrosat":
        ui.info(
            "Astrosat sensitivity study: synthetic straight-line transits with assumed Gaussian "
            "orbit errors. Measures missed crossings and false alerts. Equation-1 geometry is "
            "checked against the paper; historical TLEs, brightness and SGP4 are not reproduced."
        )
    ui.caption("Global novelty and an acceleration multiplier remain unverified.")
    branches = report.get("branches", {})
    columns = ui.columns(max(1, len(branches)))
    for column, (key, branch) in zip(columns, branches.items(), strict=False):
        with column, ui.container(border=True):
            proposal = branch["proposal"]
            ui.markdown(f"**{key} · {proposal['title']}**")
            state = branch["status"].replace("_", " ")
            if report["status"] != "running" and state in {"ready", "paused", "evaluating"}:
                state = "work concluded"
            ui.caption(f"{state} · {branch['batches']} completed batches")
            with ui.expander(f"Hypothesis · {key}"):
                ui.write(proposal["hypothesis"])
            ui.caption(f"{proposal['origin'].replace('_', ' ')} · {proposal['experiment']}")
            if branch.get("checks"):
                widths = [c["interval_width"] for c in branch["checks"]]
                ui.metric("Widest effect interval", f"{max(widths):.3f}")
                ui.caption(
                    "Eligible for final review"
                    if branch["goal_eligible"]
                    else "More evidence needed"
                )
            with ui.expander(f"Source evidence · {key}"):
                for evidence in proposal["evidence"]:
                    ui.caption(f"{evidence['source_id']} · page {evidence['page']}")
                    ui.text(evidence["quote"])
    plotted = []
    for item in report.get("rounds", []):
        for result in item["effect"].get("checks", []):
            plotted.append(
                {
                    "Branch": item["branch_id"],
                    "Batch": item["batch"],
                    "Scenario": result["scenario"],
                    "Difference": result["difference"],
                    "Lower": result["difference_interval"][0],
                    "Upper": result["difference_interval"][1],
                }
            )
    if plotted:
        frame = pd.DataFrame(plotted)
        base = alt.Chart(frame).encode(
            x=alt.X("Batch:O"),
            color="Branch:N",
            xOffset="Branch:N",
            tooltip=["Branch", "Batch", "Scenario", "Difference", "Lower", "Upper"],
        )
        chart = alt.layer(
            base.mark_rule().encode(y=alt.Y("Lower:Q", title="Treatment − control"), y2="Upper:Q"),
            base.mark_point(filled=True, size=75).encode(y="Difference:Q"),
        )
        ui.altair_chart(
            chart.facet(column="Scenario:N"),
            width="stretch",
            alt="Cumulative effect estimates and simultaneous intervals by branch and batch",
        )
    if report.get("domain") == "astrosat" and any(b.get("checks") for b in branches.values()):
        ui.markdown("**Recovery and false-alert tradeoff**")
        ui.caption(
            "Miss rates are conditional on true crossings; false-alert rates are conditional "
            "on nontransits. Branches use different candidate samples."
        )
        ui.dataframe(
            [
                {
                    "Branch": key,
                    "Scenario": c["scenario"],
                    "Control misses": f"{c['control']:.1%}",
                    "Guard misses": f"{c['treatment']:.1%}",
                    "Control false alerts": f"{c['control_false_alert_rate']:.1%}",
                    "Guard false alerts": f"{c['false_alert_rate']:.1%}",
                    "True crossings": c["positive_transits"],
                    "Nontransits": c["negative_candidates"],
                }
                for key, branch in branches.items()
                for c in branch.get("checks", [])
            ],
            hide_index=True,
            width="stretch",
            alt="Missed crossings and false alerts for each Astrosat guard and scenario",
        )
    with ui.expander("Baseline and final validation"):
        ui.json(report.get("baseline", {}), expanded=False)
        ui.json(report.get("validation", {}), expanded=False)
    ui.caption(
        f"Run status: {report['status'].replace('_', ' ')} · "
        f"{report.get('elapsed_seconds', 0):.1f}s elapsed · "
        f"{report.get('role_calls', 0)} agent requests"
    )
