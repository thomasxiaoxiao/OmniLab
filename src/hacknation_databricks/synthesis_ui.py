"""Scientific summaries derived from recorded datasets and cited paper passages."""

import json
from pathlib import Path
from urllib.parse import urlsplit

import altair as alt
import pandas as pd
import streamlit as st

from hacknation_databricks.research.artifacts import canonical
from hacknation_databricks.research.comparison import comparison_bundle, comparison_svg
from hacknation_databricks.research_views import (
    dataset_artifacts,
    latest_datasets,
    measurement_rows,
    paper_dot,
    paper_evidence,
    saved_json,
    synthesis_dataset,
)
from hacknation_databricks.tracking import Journal, read_artifact


def render_comparison_outputs(journal: Journal, dataset: dict | None) -> None:
    bundle = comparison_bundle(
        journal.report,
        journal.config,
        journal.sources,
        lambda name: saved_json(journal, name),
        dataset,
    )
    graphic = comparison_svg(bundle)
    st.markdown("**Original vs proposed · simulation visualization**")
    st.image(
        graphic,
        width="stretch",
        alt="Original and proposed simulated rates, differences and uncertainty",
    )
    st.markdown("**Difference in one sentence**")
    st.write(bundle["summary"])
    st.caption(bundle["provenance"])
    with st.container(horizontal=True):
        st.download_button(
            "Download simulation visualization",
            graphic,
            file_name=f"{journal.run_id}-simulation.svg",
            mime="image/svg+xml",
        )
        st.download_button(
            "Download difference summary",
            bundle["summary"] + "\n",
            file_name=f"{journal.run_id}-summary.txt",
            mime="text/plain",
        )
        st.download_button(
            "Download comparison data",
            canonical(bundle),
            file_name=f"{journal.run_id}-comparison.json",
            mime="application/json",
        )
    with st.expander("Paper inputs and simulation assumptions"):
        st.json(
            {
                "recorded_recipe": bundle["recipe"],
                "master_seed": bundle["master_seed"],
                "sizes": bundle["sizes"],
                "recipe_artifact": bundle["recipe_artifact"],
            }
        )
        st.caption(bundle["scope"])
        for evidence in bundle["evidence"]:
            st.caption(f"{evidence['source_id']} · page {evidence['page']}")
            st.text(evidence["quote"])
        if not bundle["evidence"]:
            st.caption("No proposal passage recorded for this dataset.")


def render_research_path(journal: Journal) -> None:
    report = journal.report
    seed = next((s for s in journal.sources if s["source_id"] == "seed"), None)
    if seed:
        with st.container(border=True):
            st.caption("RESEARCH STARTS HERE · SEED PAPER")
            st.subheader(seed.get("title", "Seed paper"))
            st.caption(f"{len(seed.get('pages', []))} text pages · SHA-256 {seed['sha256'][:16]}")
            if urlsplit(seed.get("url", "")).scheme in {"https", "http"}:
                st.link_button("Open pinned paper", seed["url"], icon=":material/article:")
    cols = st.columns(3)
    cols[0].metric("Grounded directions", len(journal.proposals))
    cols[1].metric("Completed result checkpoints", len(report.get("rounds", [])))
    cols[2].metric("Simulation budget", journal.config.get("max_simulations", "Unrecorded"))
    with st.expander("Seed → research proposals → critique", expanded=not report.get("rounds")):
        critique = (
            saved_json(journal, "consolidation.json") or saved_json(journal, "critiques.json") or {}
        )
        decisions = {c["proposal_id"]: c for c in critique.get("critiques", [])}
        for proposal in journal.proposals:
            with st.container(border=True):
                st.markdown(f"**{proposal['title']}**")
                st.caption(proposal.get("origin", "Source-grounded proposal").replace("_", " "))
                st.write(proposal["hypothesis"])
                ev = proposal.get("evidence", [])
                for evidence in ev if isinstance(ev, list) else [ev]:
                    st.caption(f"{evidence['source_id']} · page {evidence['page']}")
                    st.text(evidence["quote"])
                decision = decisions.get(proposal["id"])
                if decision:
                    st.markdown(f"**Critic: {decision['decision']}**")
                    st.write(
                        decision.get(
                            "reason", decision.get("reasoning", decision.get("rationale", ""))
                        )
                    )
        if not journal.proposals:
            st.info("Source-backed directions will appear after the reader completes.")


def render_measurements(dataset: dict) -> None:
    rows = measurement_rows(dataset)
    if not rows:
        st.info("No completed measurements for this dataset.")
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
    left, right = st.columns(2)
    with left:
        st.markdown("**Original → follow-up**")
        st.altair_chart(bars, width="stretch", alt=f"Measured control and follow-up {metric}")
    with right:
        st.markdown("**Effect and uncertainty**")
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
        st.altair_chart(
            (interval + dots + zero).properties(height=280),
            width="stretch",
            alt="Treatment minus control with recorded conservative difference "
            "intervals and zero reference",
        )
    display = frame.rename(columns={"Lower": "Interval lower", "Upper": "Interval upper"})
    st.dataframe(
        display,
        hide_index=True,
        width="stretch",
        alt="Final snapshot measurements and sample counts",
        column_config={
            name: st.column_config.NumberColumn(format="percent")
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
    st.caption(dataset.get("effect", {}).get("interval_method", "Uncertainty method not recorded."))
    if "Control false alerts" in frame:
        st.caption(
            "Tradeoff: false alerts are reported separately from missed "
            "transits; lower misses alone do not establish operational value."
        )


def render_dataset_files(journal: Journal, dataset: dict) -> None:
    files = dataset_artifacts(journal, dataset)
    with st.expander("Dataset, seeds and reproducibility"):
        st.caption(
            "These CSVs produced the selected snapshot. Cumulative checkpoints "
            "are not added together."
        )
        st.json(
            {
                k: journal.config.get(k)
                for k in ["seed", "sizes", "trials", "max_rounds", "max_simulations"]
            }
        )
        if not files:
            st.info("Raw files are not sealed yet; refresh after this run finishes.")
        for name in files:
            st.caption(f"{name} · SHA-256 {journal.artifacts[name]['sha256'][:16]}")
        if files:
            name = st.selectbox("Snapshot dataset", files)
            st.download_button(
                "Download raw simulation data",
                read_artifact(journal.directory, name),
                file_name=Path(name).name,
                mime="text/csv",
            )
        st.code(f'research verify "{journal.directory}"', language="bash")


def render_synthesis(journal: Journal) -> None:
    report = journal.report
    dataset = synthesis_dataset(report)
    finalized = report.get("goal", {}).get("achieved") is True and journal.verified
    st.subheader("Simulation synthesis")
    if finalized:
        st.success(
            "Finalized discovery dataset · supervisor marked the scoped goal achieved. "
            "See the evaluator’s assessment and limitations below."
        )
    elif report.get("status") == "running":
        st.info(
            "Provisional synthesis · this run is still active. Only completed "
            "checkpoints are shown."
        )
    else:
        st.info("Recorded outcome · this run has not established a finalized discovery goal.")
    if dataset is None:
        render_comparison_outputs(journal, None)
    else:
        decision = dataset.get("next_decision") or report.get("automated_review") or {}
        branch = dataset.get("branch_id", "follow-up")
        proposal = report.get("branches", {}).get(branch, {}).get("proposal") or report.get(
            "selected_proposal", {}
        )
        if proposal:
            st.markdown(f"**{proposal['title']}**")
            st.caption(
                f"{proposal.get('origin', 'source-grounded proposal').replace('_', ' ')} · "
                f"implemented test: {proposal['experiment']}"
            )
        st.caption(
            f"Dataset: {branch} · batch {dataset.get('batch', dataset['round'])} · "
            "snapshot selected from the recorded decision, with no new model or simulation calls"
        )
        render_comparison_outputs(journal, dataset)
        with st.expander("Detailed measurements and uncertainty"):
            render_measurements(dataset)
        with st.container(border=True):
            st.markdown("**What the result changed**")
            st.write(
                decision.get("result_interpretation")
                or decision.get("rationale")
                or "This older run has no structured result-driven interpretation."
            )
            if decision.get("action"):
                st.caption(
                    f"Agent recommendation: {decision['action']} · "
                    f"recorded run outcome: {report['status']}"
                )
            if dataset.get("transition"):
                transition = dataset["transition"]
                st.caption(
                    f"Applied action: {transition['applied_action']} · {transition['reason']}"
                )
            st.markdown("**Next experiment**")
            st.write(decision.get("next_experiment", "No next experiment was recorded."))
            st.caption(
                "Interpretation and proposed next experiment were recorded at this checkpoint, "
                "before any later review."
            )
        validation = report.get("validation")
        if validation:
            st.markdown(
                f"**Final evaluator assessment: {validation.get('decision', 'unrecorded')}**"
            )
            st.write(validation.get("reasoning", "No reasoning recorded."))
            with st.expander("Scientific limitations retained by the evaluator", expanded=False):
                for limitation in validation.get("limitations", []):
                    st.write("• " + limitation)
        render_dataset_files(journal, dataset)
    st.divider()
    st.subheader("Paper exploration")
    render_papers(journal)


def render_papers(journal: Journal) -> None:
    evidence = paper_evidence(journal)
    if not journal.sources:
        st.info("No source manifest has been saved yet.")
        return
    st.caption(
        "Each node is a paper with a concept used by the agents. Edges label recorded "
        "seed citations or shared evidence contexts. Select a paper for exact passages."
    )
    sources = {s["source_id"]: s for s in journal.sources}
    selected = st.selectbox(
        "Inspect paper and concepts",
        list(sources),
        format_func=lambda sid: sources[sid].get("title", sid),
    )
    st.graphviz_chart(
        paper_dot(journal, evidence, selected),
        width="stretch",
        height=430,
        alt="Papers and evidence concepts used together by research agents",
    )
    source = sources[selected]
    matching = [e for e in evidence if e["source_id"] == selected]
    st.markdown(f"**{source.get('title', selected)}**")
    st.caption(f"{selected} · {source.get('kind', 'source')} · SHA-256 {source['sha256']}")
    if urlsplit(source.get("url", "")).scheme in {"https", "http"}:
        st.link_button("Read original paper", source["url"])
    if not matching:
        st.warning(
            "This source was supplied, but no supporting passage appears "
            "in the inspected proposal and review artifacts."
        )
    for e in matching:
        with st.expander(f"{e['concept']} · page {e['page']}"):
            st.text(e["quote"])
            st.caption(f"Recorded in {e['artifact']}")
    with st.expander("Search coverage and missing evidence"):
        briefs = saved_json(journal, "research_briefs.json") or {}
        if selected in briefs:
            st.write(briefs[selected].get("search_scope", "Search scope not recorded"))
            st.write(briefs[selected].get("missing_evidence", []))
        for r in journal.report.get("rounds", []):
            if "branch_id" not in r:
                lit = saved_json(journal, f"rounds/{r['round']:02d}/literature.json") or {}
                if lit.get("search_scope"):
                    st.write(lit["search_scope"])
        retrieval = saved_json(journal, "reference_retrieval.json")
        if retrieval:
            st.json(retrieval, expanded=False)
        st.caption(
            "Coverage is limited to the saved sources and outputs; a "
            "retrieved source is not proof that every page was reviewed."
        )
    st.download_button(
        "Export paper evidence map",
        json.dumps(evidence, indent=2),
        file_name=f"{journal.run_id}-paper-evidence.json",
        mime="application/json",
    )


def render_comparison_page(journal: Journal) -> None:
    st.caption(
        "Compare the published reference, the local baseline and the "
        "follow-up on their actual scope."
    )
    baseline = journal.report.get("baseline", {})
    left, right = st.columns(2)
    with left, st.container(border=True):
        st.caption("ORIGINAL · SOURCE + LOCAL BASELINE")
        st.markdown("**Baseline check**")
        st.write(baseline.get("claim", "Baseline has not completed."))
        st.caption(
            baseline.get(
                "limitation", "Published paper results remain distinct from local controls."
            )
        )
        if baseline.get("checks"):
            st.dataframe(
                baseline["checks"],
                hide_index=True,
                alt="Local baseline checks against published references",
            )
    with right, st.container(border=True):
        st.caption("FOLLOW-UP · AGENT PROPOSAL + LOCAL TEST")
        proposals = journal.proposals
        for proposal in proposals:
            st.markdown(f"**{proposal['title']}**")
            st.caption(proposal.get("origin", "source-grounded proposal").replace("_", " "))
        st.write(
            "Results below compare the local control with the implemented "
            "treatment. They do not reproduce the entire paper."
        )
    datasets = latest_datasets(journal.report)
    if not datasets:
        render_comparison_outputs(journal, None)
        return
    finalized_branch = journal.report.get("goal", {}).get("branch_id")
    selected_index = next(
        (i for i, item in enumerate(datasets) if item.get("branch_id") == finalized_branch), 0
    )
    chosen = st.selectbox(
        "Follow-up dataset",
        range(len(datasets)),
        index=selected_index,
        format_func=lambda i: (
            f"{datasets[i].get('branch_id', 'Follow-up')} · checkpoint {datasets[i]['round']}"
        ),
    )
    dataset = datasets[chosen]
    render_comparison_outputs(journal, dataset)
    with st.expander("Detailed measurements and uncertainty"):
        render_measurements(dataset)
    st.subheader("Artifact lineage")
    originals = [n for n in journal.artifacts if n.startswith(("inputs/", "baseline/"))]
    if "branch_id" in dataset:
        prefix = f"branches/{dataset['branch_id']}/"
    else:
        prefix = f"rounds/{dataset['round']:02d}/"
    followups = [n for n in journal.artifacts if n.startswith(prefix)]
    for column, title, names in zip(
        st.columns(2),
        ["Original artifacts", "Follow-up artifacts"],
        [originals, followups],
        strict=True,
    ):
        with column, st.container(border=True):
            st.markdown(f"**{title}**")
            st.caption(f"{len(names)} sealed artifacts")
            if names:
                name = st.selectbox(title, sorted(names), key=title)
                st.caption(f"SHA-256 {journal.artifacts[name]['sha256'][:20]}")
                st.download_button(
                    "Download " + title.lower(),
                    read_artifact(journal.directory, name),
                    file_name=Path(name).name,
                )
                if name.endswith(".json"):
                    st.json(saved_json(journal, name), expanded=False)
    review = journal.report.get("automated_review")
    if review:
        with st.expander("Reference evaluator: original work versus added value"):
            st.write(review["rationale"])
            st.dataframe(
                [{k: v for k, v in c.items() if k != "evidence"} for c in review["comparisons"]],
                hide_index=True,
                alt="Original work, follow-up work and claimed added value",
            )
            st.write(review["limitations"])
    render_dataset_files(journal, dataset)
