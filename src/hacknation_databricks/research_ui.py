"""Thin Streamlit viewer; scientific decisions live in the research package."""

import json
import os
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from hacknation_databricks.comparison_ui import render_comparison
from hacknation_databricks.research import PAPER_URL
from hacknation_databricks.research.artifacts import verify_artifacts
from hacknation_databricks.research.cli import default_source
from hacknation_databricks.research.models import RunConfig
from hacknation_databricks.research.sources import read_source
from hacknation_databricks.research.workflow import run_research

load_dotenv(".runtime/research.env")
st.set_page_config(page_title="Research & Validation Lab", page_icon="🔬", layout="wide")
st.title("Research & Validation Lab")
st.caption("Research prototype · scientific conclusions require further validation.")
st.markdown("Read a paper → critique directions → reproduce a baseline → test an extension")
st.caption(f"Deployed revision: {os.environ.get('APP_REVISION', 'development')}")
st.link_button("Read the seed paper · arXiv:2607.24975v1", PAPER_URL)
st.info(
    "Run research through Omnigent with your Codex subscription, or use local AnyJev decisions. "
    "The evaluator compares measurements with retrieved references and records a scoped verdict."
)

output_root = Path(os.getenv("RESEARCH_OUTPUT_DIR", "output/research"))
paper_path = Path(os.getenv("RESEARCH_PAPER_PATH", "data/papers/2607.24975v1.pdf"))
if not paper_path.is_file():
    paper_path = default_source()
    st.warning("Fetch the full seed paper with `research fetch` before starting a run.")

with st.sidebar:
    st.header("Run a local experiment")
    backend = st.selectbox("Agent runner", ["omnigent", "anyjev"])
    preset = st.selectbox(
        "Simulation size", ["Quick · 32 trials per size", "Validation · 256 trials"]
    )
    seed = st.number_input("Random seed", min_value=0, max_value=2**32 - 1, value=20261003)
    st.caption("At most 3 directions, 2 workers, and a 10-minute wall-clock budget.")
    run_clicked = st.button("Run research workflow", type="primary")

if run_clicked:
    output = output_root / datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    quick = preset.startswith("Quick")
    config = RunConfig(
        seed=int(seed),
        sizes=[8, 16] if quick else [16, 32],
        trials=32 if quick else 256,
        max_seconds=600,
    )
    with st.status("Running research workflow", expanded=True) as status:
        try:
            literature, retrieval = [], None
            source = read_source(paper_path)
            if backend == "omnigent":
                from hacknation_databricks.research.literature import retrieve_references

                st.write("Retrieve cited references")
                literature, retrieval = retrieve_references(source, Path("data/literature"))
            report = run_research(
                source,
                output,
                config,
                backend=backend,
                literature=literature,
                retrieval_report=retrieval,
                cache=Path(".cache/simulations"),
                progress=st.write,
            )
            st.session_state["research_run"] = str(output)
            status.update(label=f"Run finished: {report['status']}", state="complete")
        except Exception as exc:
            status.update(label=f"Run failed ({type(exc).__name__})", state="error")
            st.error("Inspect the saved report and audit events before retrying.")

runs = (
    sorted(output_root.glob("*/report.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if output_root.exists()
    else []
)
if runs:
    paths = [str(path.parent) for path in runs]
    current = st.session_state.get("research_run")
    selected = st.selectbox(
        "Saved run",
        paths,
        index=paths.index(current) if current in paths else 0,
        format_func=lambda p: Path(p).name,
    )
    directory = Path(selected)
    report = json.loads((directory / "report.json").read_text())
    acceptance = report["acceptance"]
    first, second, third = st.columns(3)
    first.metric("Baseline checks", "Pass" if acceptance["baseline_simulations"] else "Incomplete")
    second.metric("Follow-up", "Executed" if acceptance["followup_implemented"] else "Incomplete")
    third.metric(
        "Agent assessment",
        report.get("automated_review", {}).get("verdict", "Unverified").replace("_", " "),
    )
    st.write(f"**Status:** {report['status']} · **Backend:** {report['backend']}")
    st.caption(f"Source: {report['source_kind']} · Full-scale reproduction: not completed")
    comparison, overview, proposals_tab, experiments, audit = st.tabs(
        [
            "Original vs follow-up",
            "Baseline",
            "Directions & critique",
            "Follow-up & gate",
            "Artifacts",
        ]
    )
    with comparison:
        render_comparison(directory, report)
    with overview:
        summary_path = directory / "baseline/summary.json"
        if summary_path.exists():
            frame = pd.DataFrame(json.loads(summary_path.read_text()))
            st.dataframe(frame, hide_index=True)
            st.line_chart(
                frame.pivot(index="size", columns="model", values="wrap_x"),
                x_label="Lattice size",
                y_label="Horizontal wrapping rate",
            )
            st.caption(
                "Reference ≈ 0.75001 at each model's critical bond probability. "
                "Intervals and declared finite-size tolerance appear in validation.json."
            )
        else:
            st.info("No completed baseline in this run.")
    with proposals_tab:
        path = directory / "proposals.json"
        if path.exists():
            for proposal in json.loads(path.read_text())["proposals"]:
                st.subheader(proposal["title"])
                st.write(proposal["hypothesis"])
                st.text(proposal["evidence"]["quote"])
                st.caption(
                    f"Source {proposal['evidence']['source_id']}, "
                    f"text page {proposal['evidence']['page']}"
                )
        path = directory / "critiques.json"
        if path.exists():
            st.json(json.loads(path.read_text()), expanded=False)
    with experiments:
        for round_result in report["rounds"]:
            st.subheader(f"Round {round_result['round']}")
            st.dataframe(round_result["effect"]["checks"], hide_index=True)
            st.write(round_result["gate"]["meaning"])
            st.json(round_result["gate"]["criteria"])
        if not report["rounds"]:
            st.info("No completed follow-up review in this run.")
    with audit:
        if st.button("Verify saved artifact hashes"):
            failures = verify_artifacts(directory)
            if failures:
                st.error("; ".join(failures))
            else:
                st.success("Every recorded artifact matches its saved SHA-256 hash.")
        st.download_button(
            "Download run report",
            (directory / "report.json").read_bytes(),
            file_name="report.json",
            mime="application/json",
        )
        st.code(str(directory.resolve()))
        st.caption(
            "Includes source snapshots, raw trials, plans, reviews, seed replays, "
            "environment versions, code snapshot, audit events and checksums."
        )
else:
    st.info("Start a local run from the sidebar, or generate artifacts with the research CLI.")
