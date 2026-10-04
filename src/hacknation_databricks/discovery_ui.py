"""Scientific loop overview backed exclusively by saved, verified evidence."""

import json

import streamlit as st

from hacknation_databricks.checkpoint_ui import render_checkpoint_story
from hacknation_databricks.tracking import Journal, read_artifact


def render_discovery(journal: Journal) -> None:
    report = journal.report
    if not report.get("proposals") and (journal.directory / "paper_briefs.json").is_file():
        briefs = json.loads(read_artifact(journal.directory, "paper_briefs.json"))
        brief = briefs.get("seed", {})
        st.subheader("Paper-derived research directions")
        st.write(brief.get("research_question", "Research question not yet recorded"))
        st.caption("Unexecuted hypotheses derived before implementation selection.")
        for direction in brief.get("directions", []):
            with st.container(border=True):
                st.markdown(f"**{direction['title']}**")
                st.write(direction["hypothesis"])
                st.caption(direction["origin"].replace("_", " "))
                for evidence in direction["evidence"]:
                    st.caption(f"{evidence['source_id']} · page {evidence['page']}")
                    st.text(evidence["quote"])
    if report.get("status") == "unsupported_source":
        st.caption("No experiment or result-driven follow-up was executed in this run.")
        return
    if report.get("workflow_version") == "4":
        render_portfolio(journal)
        return
    from hacknation_databricks.synthesis_ui import render_comparison_outputs

    st.subheader("What changed our next move?")
    render_comparison_outputs(journal, None)
    st.subheader("Question → evidence → experiment → next decision")
    proposal = report.get("selected_proposal", {})
    st.markdown(
        f"**Research question:** {proposal.get('hypothesis', 'Awaiting a reviewed hypothesis')}"
    )
    if proposal.get("evidence"):
        evidence = proposal["evidence"]
        st.caption(f"Source: {evidence['source_id']} · page {evidence['page']}")
        st.text(evidence["quote"])
    if report.get("backend") != "omnigent":
        st.info("Auxiliary run: this is not evidence of a live Omnigent discovery loop.")
    st.caption("Hypotheses and agent assessments are provisional; global novelty is unverified.")
    acceleration = report.get("acceleration", {})
    columns = st.columns(3)
    columns[0].metric("Recorded elapsed time", f"{report.get('elapsed_seconds', 'Unrecorded')} s")
    columns[1].metric("Computed simulations", report.get("computed_simulations", 0))
    columns[2].metric("Acceleration multiplier", "Unverified")
    st.caption(acceleration.get("status", "No comparable manual baseline measured"))
    st.markdown(
        "**Experimenter:** bounded Python simulation tools, coordinated by the supervisor. "
        "Agent sessions select and review tests; they do not execute generated code."
    )
    for item in report.get("rounds", []):
        number = item["round"]
        with st.container(border=True):
            st.subheader(f"Discovery round {number}")
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
                    columns = st.columns(2)
                    for column, test in zip(columns, plan["tests"], strict=True):
                        with column, st.container(border=True):
                            option = options.get(test["test_id"], {})
                            selected = test["test_id"] == plan["selected_test_id"]
                            st.markdown(
                                f"**{test['test_id'].capitalize()}"
                                f"{' · selected' if selected else ''}**"
                            )
                            st.caption(
                                f"{option.get('trials_per_size', '?')} trials / size · "
                                f"{option.get('simulation_cost', '?')} simulation units"
                            )
                            st.write(test["expected_learning"])
                            with st.expander("Feasibility and cost"):
                                st.write(test["feasibility"])
                with st.expander("Why this test was selected"):
                    st.write(plan["rationale"])
            st.markdown(f"**Result:** {item['trials_per_size']} trials per lattice size")
            st.dataframe(item["effect"].get("checks", []), hide_index=True, width="stretch")
            decision = item.get("next_decision")
            if decision:
                st.markdown(f"**Recommended action: {decision['action']}**")
                transition = item.get("transition")
                if transition:
                    st.markdown(f"**Supervisor action: {transition['applied_action']}**")
                    st.caption(transition["reason"])
                else:
                    st.caption(f"Recorded run status: {report['status']}")
                st.write(decision["result_interpretation"])
                with st.expander("Decision rationale and proposed next experiment"):
                    st.write(decision["rationale"])
                    st.markdown(f"**Next experiment:** {decision['next_experiment']}")
            else:
                st.info("This older run has no structured result-driven next decision.")
    if not report.get("rounds"):
        st.info(
            "No experimental result yet. The workflow retains partial evidence if a stage stops."
        )


def render_portfolio(journal: Journal) -> None:
    import altair as alt
    import pandas as pd

    report, goal = journal.report, journal.report["goal"]
    render_checkpoint_story(journal)
    st.divider()
    st.subheader("Parallel research, continuous decisions")
    st.write(goal["description"])
    st.caption(
        f"{journal.config['max_rounds']} batches per direction · "
        f"{journal.config['max_workers']} concurrent workers · fresh seed streams per batch"
    )
    cols = st.columns(4)
    cols[0].metric("Goal", "Achieved" if goal["achieved"] else "Open")
    cols[1].metric("Research branches", len(report.get("branches", {})))
    cols[2].metric("Decision checkpoints", len(report.get("checkpoints", [])))
    cols[3].metric("Computed simulations", report.get("computed_simulations", 0))
    st.caption(
        f"Finish criterion: ≥{goal['minimum_batches']} independent batches, interval width "
        f"≤{goal['maximum_interval_width']}, "
        f"resolved effect at threshold {goal['minimum_effect']}, "
        "and independent validation. Budget exhaustion is not goal completion."
    )
    if report.get("domain") == "astrosat":
        st.info(
            "Astrosat sensitivity study: synthetic straight-line transits with assumed Gaussian "
            "orbit errors. Measures missed crossings and false alerts. Equation-1 geometry is "
            "checked against the paper; historical TLEs, brightness and SGP4 are not reproduced."
        )
    st.caption("Global novelty and an acceleration multiplier remain unverified.")
    branches = report.get("branches", {})
    columns = st.columns(max(1, len(branches)))
    for column, (key, branch) in zip(columns, branches.items(), strict=False):
        with column, st.container(border=True):
            proposal = branch["proposal"]
            st.markdown(f"**{key} · {proposal['title']}**")
            state = branch["status"].replace("_", " ")
            if report["status"] != "running" and state in {"ready", "paused", "evaluating"}:
                state = "work concluded"
            st.caption(f"{state} · {branch['batches']} completed batches")
            with st.expander(f"Hypothesis · {key}"):
                st.write(proposal["hypothesis"])
            st.caption(f"{proposal['origin'].replace('_', ' ')} · {proposal['experiment']}")
            if branch.get("checks"):
                widths = [c["interval_width"] for c in branch["checks"]]
                st.metric("Widest effect interval", f"{max(widths):.3f}")
                st.caption(
                    "Eligible for final review"
                    if branch["goal_eligible"]
                    else "More evidence needed"
                )
            with st.expander(f"Source evidence · {key}"):
                for evidence in proposal["evidence"]:
                    st.caption(f"{evidence['source_id']} · page {evidence['page']}")
                    st.text(evidence["quote"])
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
        st.altair_chart(
            chart.facet(column="Scenario:N"),
            width="stretch",
            alt="Cumulative effect estimates and simultaneous intervals by branch and batch",
        )
    if report.get("domain") == "astrosat" and any(b.get("checks") for b in branches.values()):
        st.markdown("**Recovery and false-alert tradeoff**")
        st.caption(
            "Miss rates are conditional on true crossings; false-alert rates are conditional "
            "on nontransits. Branches use different candidate samples."
        )
        st.dataframe(
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
    with st.expander("Baseline and final validation"):
        st.json(report.get("baseline", {}), expanded=False)
        st.json(report.get("validation", {}), expanded=False)
    st.caption(
        f"Run status: {report['status'].replace('_', ' ')} · "
        f"{report.get('elapsed_seconds', 0):.1f}s elapsed · "
        f"{report.get('role_calls', 0)} agent requests"
    )
