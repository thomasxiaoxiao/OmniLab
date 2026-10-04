"""Scientific summaries derived from recorded datasets and cited paper passages."""

import json
import re
from urllib.parse import urlsplit

import altair as alt
import pandas as pd

from hacknation_databricks.highlights_ui import render_highlights
from hacknation_databricks.process_ui import render_process
from hacknation_databricks.research.artifacts import canonical
from hacknation_databricks.research.comparison import comparison_bundle, comparison_svg
from hacknation_databricks.research_views import (
    dataset_artifacts,
    measurement_rows,
    paper_dot,
    paper_evidence,
    saved_json,
    synthesis_dataset,
)
from hacknation_databricks.tracking import Journal, read_artifact
from hacknation_databricks.web import components as ui


def render_comparison_outputs(journal: Journal, dataset: dict | None) -> None:
    bundle = comparison_bundle(
        journal.report,
        journal.config,
        journal.sources,
        lambda name: saved_json(journal, name),
        dataset,
    )
    graphic = comparison_svg(bundle)
    render_process(journal, bundle)
    ui.image(
        graphic,
        width="stretch",
        alt="Original and proposed simulated rates, differences and uncertainty",
    )
    ui.markdown("**Result**")
    ui.write(bundle["summary"])
    with ui.expander("Paper comparison and scientific interpretation"):
        render_highlights(bundle)
        ui.caption(bundle["provenance"])
    with ui.container(horizontal=True):
        ui.download_button(
            "Download numerical comparison chart",
            graphic,
            file_name=f"{journal.run_id}-simulation.svg",
            mime="image/svg+xml",
        )
        ui.download_button(
            "Download difference summary",
            bundle["summary"] + "\n",
            file_name=f"{journal.run_id}-summary.txt",
            mime="text/plain",
        )
        ui.download_button(
            "Download comparison data",
            canonical(bundle),
            file_name=f"{journal.run_id}-comparison.json",
            mime="application/json",
        )
    if dataset:
        render_dataset_files(journal, dataset)
    with ui.expander("Paper inputs and simulation assumptions"):
        ui.json(
            {
                "recorded_recipe": bundle["recipe"],
                "master_seed": bundle["master_seed"],
                "sizes": bundle["sizes"],
                "recipe_artifact": bundle["recipe_artifact"],
            }
        )
        ui.caption(bundle["scope"])
        for evidence in bundle["evidence"]:
            ui.caption(f"{evidence['source_id']} · page {evidence['page']}")
            ui.text(evidence["quote"])
        if not bundle["evidence"]:
            ui.caption("No proposal passage recorded for this dataset.")


def render_research_path(journal: Journal) -> None:
    report = journal.report
    dataset = synthesis_dataset(report)
    branch_id = (dataset or {}).get("branch_id") or report.get("goal", {}).get("branch_id")
    proposal = report.get("branches", {}).get(branch_id, {}).get("proposal") or report.get(
        "selected_proposal", {}
    )
    with ui.container(border=True):
        ui.caption("CHOSEN PATH · EXPLORED IDEA")
        if proposal:
            ui.subheader(proposal["title"])
            ui.write(proposal.get("hypothesis", ""))
            label = (
                "Accepted result branch"
                if report.get("goal", {}).get("achieved")
                else (
                    "Most recently measured branch"
                    if dataset and branch_id
                    else "Selected direction"
                )
            )
            ui.caption(
                f"{label}{' · ' + branch_id if branch_id else ''} · "
                + proposal.get("origin", "Source-grounded proposal").replace("_", " ")
            )
            evidence = proposal.get("evidence", [])
            for item in evidence if isinstance(evidence, list) else [evidence]:
                ui.caption(f"{item['source_id']} · page {item['page']}")
                ui.text(item["quote"])
        else:
            ui.subheader("Explored idea pending")
            ui.caption(
                "No selected or measured path is recorded yet. Reviewed directions appear below."
            )
    seed = next((s for s in journal.sources if s["source_id"] == "seed"), None)
    if seed:
        with ui.container(border=True):
            ui.markdown("**Source inputs**")
            ui.write(seed.get("title", "Seed paper"))
            ui.caption(f"{len(seed.get('pages', []))} text pages · SHA-256 {seed['sha256'][:16]}")
            if urlsplit(seed.get("url", "")).scheme in {"https", "http"}:
                ui.link_button("Open pinned paper", seed["url"], icon=":material/article:")
            links = {}
            for page, text in enumerate(seed.get("pages", []), 1):
                for link in re.findall(
                    r"https?://(?:github\.com|gitlab\.com|bitbucket\.org)/[\w.-]+/[\w.-]+",
                    text,
                ):
                    links.setdefault(link.rstrip(".,;"), page)
            for link, page in links.items():
                ui.link_button(
                    "Code cited by paper · " + link.split("/")[-1], link, icon=":material/code:"
                )
                ui.caption(f"Repository link extracted from seed paper · page {page}")
            if not links:
                ui.caption("Code link: no repository URL found in the saved paper text.")
    cols = ui.columns(3)
    cols[0].metric("Grounded directions", len(journal.proposals))
    cols[1].metric("Completed result checkpoints", len(report.get("rounds", [])))
    cols[2].metric("Simulation budget", journal.config.get("max_simulations", "Unrecorded"))
    with ui.expander("Seed → research proposals → critique", expanded=not report.get("rounds")):
        critique = (
            saved_json(journal, "consolidation.json") or saved_json(journal, "critiques.json") or {}
        )
        decisions = {c["proposal_id"]: c for c in critique.get("critiques", [])}
        for proposal in journal.proposals:
            with ui.container(border=True):
                ui.markdown(f"**{proposal['title']}**")
                ui.caption(proposal.get("origin", "Source-grounded proposal").replace("_", " "))
                ui.write(proposal["hypothesis"])
                ev = proposal.get("evidence", [])
                for evidence in ev if isinstance(ev, list) else [ev]:
                    ui.caption(f"{evidence['source_id']} · page {evidence['page']}")
                    ui.text(evidence["quote"])
                decision = decisions.get(proposal["id"])
                if decision:
                    ui.markdown(f"**Critic: {decision['decision']}**")
                    ui.write(
                        decision.get(
                            "reason", decision.get("reasoning", decision.get("rationale", ""))
                        )
                    )
        if not journal.proposals:
            ui.info("Source-backed directions will appear after the reader completes.")


def render_measurements(dataset: dict) -> None:
    rows = measurement_rows(dataset)
    if not rows:
        ui.info("No completed measurements for this dataset.")
        return
    metric = dataset.get("effect", {}).get("metric", "one-axis wrapping probability")
    frame = pd.DataFrame(rows)
    plotted = frame.melt(
        id_vars=["Scenario"],
        value_vars=["Original / control", "Follow-up"],
        var_name="Version",
        value_name="Rate",
    )
    bars = (
        alt.Chart(plotted)
        .mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3)
        .encode(
            x=alt.X("Scenario:N", title="Scenario / lattice size"),
            xOffset="Version:N",
            y=alt.Y(
                "Rate:Q",
                title=metric.capitalize(),
                scale=alt.Scale(domain=[0, 1]),
                axis=alt.Axis(format=".0%"),
            ),
            color=alt.Color(
                "Version:N",
                scale=alt.Scale(
                    domain=["Original / control", "Follow-up"], range=["#94a3b8", "#0f766e"]
                ),
                legend=alt.Legend(orient="bottom"),
            ),
            tooltip=["Scenario", "Version", alt.Tooltip("Rate:Q", format=".2%")],
        )
        .properties(height=280)
    )
    left, right = ui.columns(2)
    with left:
        ui.markdown("**Local control and proposed simulation**")
        ui.altair_chart(bars, width="stretch", alt=f"Measured control and follow-up {metric}")
    with right:
        ui.markdown("**Effect and uncertainty**")
        points = alt.Chart(frame).encode(
            y=alt.Y("Scenario:N", title=None), tooltip=["Scenario", "Difference", "Lower", "Upper"]
        )
        interval = points.mark_rule(color="#0f766e", strokeWidth=3).encode(
            x=alt.X("Lower:Q", title="Follow-up − control", axis=alt.Axis(format=".0%")),
            x2="Upper:Q",
        )
        dots = points.mark_point(filled=True, color="#0f766e", size=95).encode(x="Difference:Q")
        zero = (
            alt.Chart(pd.DataFrame({"zero": [0]}))
            .mark_rule(strokeDash=[4, 4], color="#94a3b8")
            .encode(x="zero:Q")
        )
        ui.altair_chart(
            (interval + dots + zero).properties(height=280),
            width="stretch",
            alt="Treatment minus control with recorded conservative difference "
            "intervals and zero reference",
        )
    display = frame.rename(columns={"Lower": "Interval lower", "Upper": "Interval upper"})
    ui.dataframe(
        display,
        hide_index=True,
        width="stretch",
        alt="Final snapshot measurements and sample counts",
        column_config={
            name: ui.column_config.NumberColumn(format="percent")
            for name in [
                "Original / control",
                "Follow-up",
                "Difference",
                "Interval lower",
                "Interval upper",
                "Control false alerts",
                "Follow-up false alerts",
            ]
        },
    )
    ui.caption(dataset.get("effect", {}).get("interval_method", "Uncertainty method not recorded."))
    if "Control false alerts" in frame:
        ui.caption(
            "Tradeoff: false alerts are reported separately from missed "
            "transits; lower misses alone do not establish operational value."
        )


def render_dataset_files(journal: Journal, dataset: dict) -> None:
    files = dataset_artifacts(journal, dataset)
    if "branch_id" in dataset:
        prefix = f"branches/{dataset['branch_id']}/batches/"
        candidates = [
            f"{prefix}{number:02d}/{name}"
            for number in range(1, dataset["batch"] + 1)
            for name in ("specification.json", "trials.csv", "checks.json", "cumulative.json")
        ]
    else:
        prefix = f"rounds/{dataset['round']:02d}/"
        candidates = [prefix + name for name in ("experiment.json", "trials.csv", "checks.json")]
    files = sorted(
        set(
            files
            + [
                name
                for name in candidates
                if (
                    name in journal.artifacts
                    if journal.sealed
                    else (journal.directory / name).is_file()
                )
            ]
        )
    )
    with ui.expander("Proposed simulation artifacts · recipe, data and checks"):
        ui.caption("Files are scoped to this checkpoint; later batches are excluded.")
        if not files:
            ui.info("No simulation files have been written for this snapshot yet.")
        else:
            name = ui.selectbox(
                "Snapshot artifact",
                files,
                index=next(
                    (
                        i
                        for i, f in enumerate(files)
                        if f.endswith("specification.json")
                        and f"/{dataset.get('batch', 0):02d}/" in f
                    ),
                    0,
                ),
            )
            digest = journal.artifacts.get(name, {}).get("sha256")
            ui.caption(f"SHA-256 {digest}" if digest else "Live artifact · manifest not sealed yet")
            raw = read_artifact(journal.directory, name)
            if name.endswith(".json"):
                ui.json(json.loads(raw), expanded=False)
            ui.download_button(
                "Download simulation artifact",
                raw,
                file_name=name.replace("/", "-"),
                mime="text/csv" if name.endswith(".csv") else "application/json",
            )
        ui.code(f'research verify "{journal.directory}"', language="bash")


def render_synthesis(journal: Journal) -> None:
    if journal.report.get("workflow") == "repository":
        from hacknation_databricks.repository_ui import render_repository_result

        render_repository_result(journal)
        return
    report = journal.report
    dataset = synthesis_dataset(report)
    # Show the evidence before status, prose, metrics, or audit details.
    render_comparison_outputs(journal, dataset)
    decision = (dataset or {}).get("next_decision") or report.get("automated_review") or {}
    if dataset and not decision:
        checkpoint = next(
            (c for c in report.get("checkpoints", []) if c["checkpoint"] == dataset["round"]), {}
        )
        decision = checkpoint.get("decision", {})
    ui.markdown("**What changed**")
    ui.write(
        decision.get("result_interpretation")
        or decision.get("rationale")
        or "No result-driven interpretation has been recorded yet."
    )
    ui.markdown("**Next experiment**")
    from hacknation_databricks.research_views import next_experiment_summary

    next_experiment = decision.get("next_experiment", "No next experiment has been recorded.")
    ui.write(next_experiment_summary(next_experiment))
    if next_experiment_summary(next_experiment) != next_experiment:
        with ui.expander("Full recorded next experiment"):
            ui.write(next_experiment)
    from hacknation_databricks.run_feedback_ui import render_run_outcome

    render_run_outcome(journal)
    from hacknation_databricks.research_routes_ui import render_research_routes

    render_research_routes(journal)
    with ui.expander("Research question, sources, and selected direction"):
        render_research_path(journal)
    if dataset:
        with ui.expander("Detailed measurements and uncertainty"):
            render_measurements(dataset)
    if report.get("checkpoints"):
        with ui.expander("Decision history and executed actions"):
            from hacknation_databricks.checkpoint_ui import render_checkpoint_story

            render_checkpoint_story(journal, show_comparison=False)
    else:
        with ui.expander("Decision history and executed actions"):
            for item in report.get("rounds", []):
                transition = item.get("transition", {})
                ui.markdown(
                    f"**Supervisor action: {transition.get('applied_action', 'unrecorded')}**"
                )
                ui.write(transition.get("reason", ""))
    with ui.expander("Validation, limitations, and run measurements"):
        baseline = report.get("baseline", {})
        ui.write(baseline.get("claim", "Baseline validation has not completed."))
        ui.caption(baseline.get("limitation", "This is a scoped simulation check."))
        validation = report.get("validation", {})
        ui.write(validation.get("reasoning", "Independent validation has not been recorded."))
        for limitation in validation.get("limitations", []):
            ui.write("• " + limitation)
        cols = ui.columns(3)
        cols[0].metric("Completed checkpoints", len(report.get("rounds", [])))
        cols[1].metric("Computed simulations", report.get("computed_simulations", 0))
        cols[2].metric("Elapsed time", f"{report.get('elapsed_seconds', 0):.1f} s")
        ui.metric("Acceleration multiplier", "Unverified")
        ui.caption(
            report.get("acceleration", {}).get("status", "No comparable manual baseline measured")
        )
        for key, branch in report.get("branches", {}).items():
            ui.markdown(f"**{key} · {branch['proposal']['title']}**")
            ui.write(
                f"{branch['batches']} completed batches · {branch['status'].replace('_', ' ')}"
            )
    ui.caption("Scientific novelty and real-world validity require independent validation.")


def render_papers(journal: Journal) -> None:
    evidence = paper_evidence(journal)
    if not journal.sources:
        ui.info("No source manifest has been saved yet.")
        return
    ui.caption(
        "Each node is a paper with a concept used by the agents. Edges label recorded "
        "seed citations or shared evidence contexts. Select a paper for exact passages."
    )
    sources = {s["source_id"]: s for s in journal.sources}
    selected = ui.selectbox(
        "Inspect paper and concepts",
        list(sources),
        format_func=lambda sid: sources[sid].get("title", sid),
    )
    ui.graphviz_chart(
        paper_dot(journal, evidence, selected),
        width="stretch",
        height=430,
        alt="Papers and evidence concepts used together by research agents",
    )
    source = sources[selected]
    matching = [e for e in evidence if e["source_id"] == selected]
    ui.markdown(f"**{source.get('title', selected)}**")
    ui.caption(f"{selected} · {source.get('kind', 'source')} · SHA-256 {source['sha256']}")
    if urlsplit(source.get("url", "")).scheme in {"https", "http"}:
        ui.link_button("Read original paper", source["url"])
    if not matching:
        ui.warning(
            "This source was supplied, but no supporting passage appears "
            "in the inspected proposal and review artifacts."
        )
    for e in matching:
        with ui.expander(f"{e['concept']} · page {e['page']}"):
            ui.text(e["quote"])
            ui.caption(f"Recorded in {e['artifact']}")
    with ui.expander("Search coverage and missing evidence"):
        briefs = saved_json(journal, "research_briefs.json") or {}
        if selected in briefs:
            ui.write(briefs[selected].get("search_scope", "Search scope not recorded"))
            ui.write(briefs[selected].get("missing_evidence", []))
        for r in journal.report.get("rounds", []):
            if "branch_id" not in r:
                lit = saved_json(journal, f"rounds/{r['round']:02d}/literature.json") or {}
                if lit.get("search_scope"):
                    ui.write(lit["search_scope"])
        retrieval = saved_json(journal, "reference_retrieval.json")
        if retrieval:
            ui.json(retrieval, expanded=False)
        ui.caption(
            "Coverage is limited to the saved sources and outputs; a "
            "retrieved source is not proof that every page was reviewed."
        )
    ui.download_button(
        "Export paper evidence map",
        json.dumps(evidence, indent=2),
        file_name=f"{journal.run_id}-paper-evidence.json",
        mime="application/json",
    )
