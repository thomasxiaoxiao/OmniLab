"""Omnigent scientific discovery lab: bounded controls and an inspectable decision journal."""

import fcntl
import html
import json
import os
import secrets
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

import streamlit as st

from hacknation_databricks.discovery_ui import render_discovery
from hacknation_databricks.research.decision_runtime import runtime_status
from hacknation_databricks.research.intake import library_sources, source_root
from hacknation_databricks.research.models import RunConfig
from hacknation_databricks.research.sources import read_source
from hacknation_databricks.research.workflow import run_research
from hacknation_databricks.tracking import (
    POLICY_VERSION,
    STEP_BY_KEY,
    STEPS,
    Decision,
    Journal,
    decision_contract,
    discover_runs,
    load_journal,
    read_artifact,
)

CSS = """
<style>
:root { --ink:#182b35; --muted:#697984; --line:#e1e7ea; --teal:#087e80; }
.stApp { background:#f6f8fa; color:var(--ink); }
.block-container { max-width:1500px; padding-top:3.7rem; padding-bottom:3rem; }
[data-testid="stSidebar"] { background:#edf2f4; border-right:1px solid var(--line); }
[data-testid="stSidebar"] .block-container { padding-top:1.6rem; }
h1,h2,h3 { color:var(--ink); letter-spacing:-.035em; }
h1 { font-size:2.6rem!important; font-weight:650!important; padding-top:0!important; }
h3 { font-size:1.2rem!important; }
.eyebrow { color:var(--teal); font-size:.7rem; font-weight:750; letter-spacing:.17em;
           text-transform:uppercase; margin-bottom:.6rem; }
.brand { font-size:1.35rem; font-weight:750; letter-spacing:-.05em; margin-bottom:.1rem; }
.brand b { color:var(--teal); }
.brand-sub { color:var(--muted); font-size:.75rem; margin-bottom:2rem; }
.context { color:var(--muted); font-size:.88rem; margin-bottom:1.2rem; }
.pill { display:inline-block; border:1px solid #bcdedb; background:#eaf6f3; color:#22675d;
        border-radius:6px; font-size:.66rem; font-weight:700; letter-spacing:.05em;
        padding:4px 8px; max-width:100%; box-sizing:border-box; }
.pill.review,.pill.blocked { background:#fff4df; color:#966320; border-color:#eedabb; }
.pill.running { background:#e9effc; color:#3d5c9e; border-color:#ccd7ee; }
.pill.pending { background:#f0f3f5; color:#71808a; border-color:#dce4e9; }
.stat { background:white; border:1px solid var(--line); border-radius:10px; padding:18px 20px; }
.stat-label { color:var(--muted); font-size:.73rem; }
.stat-value { font-size:1.75rem; font-weight:650; letter-spacing:-.05em; margin:4px 0; }
.stat-detail { color:var(--muted); font-size:.72rem; }
.path { display:flex; gap:8px; margin:22px 0 24px; }
.node { flex:1; min-width:0; border-top:3px solid #d9e1e6; padding:11px 9px 8px;
        background:#eef2f5; border-radius:0 0 5px 5px; }
.node.recorded { border-top-color:var(--teal); background:#eaf3f3; }
.node.review,.node.blocked { border-top-color:#c68a37; background:#faf2e7; }
.node.running { border-top-color:#567ac0; background:#eef2fc; }
.node-index { font-size:.62rem; color:var(--muted); font-weight:700; margin-bottom:5px; }
.node-label { font-size:.72rem; font-weight:600; }
.decision { padding:17px 20px; border:1px solid var(--line); border-left:3px solid var(--teal);
            border-radius:8px; background:white; margin-top:10px; }
.decision.review,.decision.blocked { border-left-color:#c68a37; }
.decision.running { border-left-color:#567ac0; }
.decision-top { display:flex; align-items:center; justify-content:space-between; gap:12px; }
.decision-meta { color:var(--muted); font-size:.69rem; letter-spacing:.025em; }
.decision-title { font-size:1.02rem; font-weight:650; margin:8px 0 6px; }
.decision-body { color:#64747e; font-size:.82rem; line-height:1.55; }
.small-label { color:var(--muted); font-size:.68rem; text-transform:uppercase;
               letter-spacing:.09em; font-weight:650; margin-bottom:8px; }
.gate { padding:20px; background:#172f38; color:#f2f7f8; border-radius:10px; margin-bottom:18px; }
.gate .small-label { color:#9ab7bf; }
.gate-title { font-size:1.3rem; font-weight:600; margin:5px 0 10px; }
.gate-detail { font-size:.81rem; line-height:1.6; color:#c2d2d8; }
.criterion { display:flex; gap:8px; font-size:.76rem; padding:8px 0;
             border-bottom:1px solid #ffffff19; }
.criterion .yes { color:#80d8b8; } .criterion .no { color:#f0bf79; }
.policy-box { background:white; padding:19px; border:1px solid var(--line); border-radius:9px; }
.policy-row { font-size:.78rem; padding:8px 0; color:#4f626c; border-bottom:1px solid #edf1f3; }
.proposal { border:1px solid var(--line); border-radius:8px; background:white; padding:18px;
            height:100%; min-height:165px; }
.proposal h4 { font-size:.95rem; margin:8px 0; color:var(--ink); }
.proposal p { font-size:.78rem; color:var(--muted); line-height:1.5; }
[data-testid="stTabs"] [data-baseweb="tab-list"] { gap:25px; border-bottom:1px solid var(--line); }
[data-testid="stTabs"] [data-baseweb="tab"] { font-size:.83rem; }
[data-testid="stTabs"] [aria-selected="true"] { color:var(--teal)!important; }
[data-testid="stTabs"] [data-baseweb="tab-highlight"] { background-color:var(--teal)!important; }
[data-testid="stBaseButton-primary"] { background:var(--teal); border-color:var(--teal); }
[data-testid="stExpander"] { background:white; border-radius:7px; }
[data-testid="stButton"] button, [data-testid="stDownloadButton"] button { border-radius:7px; }
[data-testid="stAlert"] { border-radius:8px; }
@media(max-width:800px) {
  .path { flex-wrap:wrap; } .node { flex:1 1 25%; }
  .block-container { padding-top:4rem; } h1 { font-size:2rem!important; }
}
</style>
"""


def esc(value: object) -> str:
    return html.escape(str(value))


def markup(value: str) -> None:
    st.markdown(value, unsafe_allow_html=True)


def run_root() -> Path:
    return Path(
        os.environ.get(
            "RESEARCH_RUNS_DIR", os.environ.get("RESEARCH_OUTPUT_DIR", "output/research")
        )
    )


def available_sources() -> dict[str, Path]:
    registered, _ = library_sources(source_root())
    return {f"{source.title} · {source.sha256[:8]}": Path(source.path) for source in registered}


def run_profiles(backend="omnigent"):
    shared = {
        "workflow": "adaptive" if backend == "omnigent" else "sequential",
        "domain": "auto" if backend == "omnigent" else "percolation",
        "agent_timeout_seconds": 240,
    }
    return {
        "Quick verification": RunConfig(
            **shared,
            sizes=[8, 16],
            trials=32,
            max_rounds=4,
            max_workers=4,
            max_seconds=1200,
            max_agent_calls=48,
            max_simulations=20000,
        ),
        "Standard exploration": RunConfig(
            **shared,
            sizes=[8, 16],
            trials=128,
            max_rounds=8,
            max_workers=6,
            max_seconds=3600,
            max_agent_calls=96,
            max_simulations=100000,
        ),
        "Extended exploration": RunConfig(
            **shared,
            sizes=[16, 32],
            trials=256,
            max_rounds=16,
            max_workers=12,
            max_seconds=7200,
            max_agent_calls=192,
            max_simulations=300000,
        ),
    }


def launch_run(
    source_path: Path,
    profile: str,
    backend: str,
    progress,
    literature_paths: list[Path] | None = None,
    overrides: dict | None = None,
) -> Path:
    """Closed launch boundary: controls choose profiles, never executable instructions."""
    registered = {p.resolve() for p in available_sources().values()}
    if any(p.resolve() not in registered for p in [source_path, *(literature_paths or [])]):
        raise ValueError("Source is not registered")
    profiles = run_profiles(backend)
    if profile not in profiles or backend not in {"anyjev", "omnigent"}:
        raise ValueError("Unknown run profile or backend")
    config_data = profiles[profile].model_dump()
    if overrides:
        allowed = {
            "max_rounds",
            "max_workers",
            "trials",
            "max_seconds",
            "max_agent_calls",
            "max_simulations",
            "seed",
            "goal_max_interval_width",
        }
        if not set(overrides) <= allowed:
            raise ValueError("Unknown budget override")
        config_data.update(overrides)
    config = RunConfig.model_validate(config_data)
    if backend == "anyjev" and config.domain != "percolation":
        raise ValueError("Astrosat uses the Omnigent adaptive workflow")
    if len(literature_paths or []) > 3:
        raise ValueError("Select at most three related sources")
    source = read_source(source_path)
    literature = [
        read_source(p, source_id=f"literature_{i}") for i, p in enumerate(literature_paths or [], 1)
    ]
    retrieval = None
    if backend == "omnigent":
        from dotenv import load_dotenv

        from hacknation_databricks.research.literature import retrieve_references

        load_dotenv(".runtime/research.env")
        progress("Retrieve cited references for automated evaluation")
        retrieved, retrieval = retrieve_references(
            source, Path("data/literature"), existing=literature
        )
        literature.extend(retrieved)
    name = datetime.now(UTC).strftime("%Y%m%dT%H%M%S") + "-" + uuid4().hex[:8]
    directory = run_root() / name
    run_root().mkdir(parents=True, exist_ok=True)
    with (run_root() / ".ui-run.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("Another UI run is active; refresh its saved progress") from None
        run_research(
            source,
            directory,
            config,
            backend=backend,
            literature=literature,
            progress=progress,
            cache=Path(".cache/simulations"),
            retrieval_report=retrieval,
        )
    return directory


@st.cache_resource
def background_executor():
    return ThreadPoolExecutor(max_workers=1, thread_name_prefix="research-ui")


@st.fragment(run_every=3)
def render_launch_monitor():
    future = st.session_state.get("research_future")
    if future is None:
        return
    if future.done():
        st.session_state.pop("research_future")
        try:
            directory = future.result()
            st.session_state["new_run"] = directory.name
        except Exception as exc:
            st.error(f"Run stopped ({type(exc).__name__}); inspect retained artifacts.")
        st.rerun()
    else:
        st.info("Omnigent research is running. Saved partial results refresh automatically.")
        if not st.session_state.get("following_live_run"):
            runs = discover_runs(run_root())
            if runs and load_journal(runs[0]).report.get("status") == "running":
                st.session_state["new_run"] = runs[0].name
                st.session_state["following_live_run"] = True
                st.rerun()


def render_sidebar() -> Path | None:
    """Run context only; intake and launch controls live on their own page."""
    with st.sidebar:
        markup('<div class="brand"><b>◈</b> Omnigent lab</div>')
        st.caption("SCIENTIFIC DISCOVERY")
        runs = discover_runs(run_root())
        names = [path.name for path in runs]
        chosen = st.session_state.pop("new_run", None)
        if chosen in names:
            st.session_state["run_selection"] = chosen
        if st.session_state.get("run_selection") not in names:
            st.session_state.pop("run_selection", None)
        selected = st.selectbox(
            "Exploration run",
            names,
            key="run_selection",
            placeholder="No recorded runs yet",
        )
        if st.button("Refresh artifacts", width="stretch", icon=":material/refresh:"):
            st.rerun()
        render_launch_monitor()
        st.divider()
        st.caption("Seed paper → grounded proposals → bounded tests → updated decision")
        st.caption("Research prototype · scientific conclusions require further validation.")
        st.caption(f"Deployed revision: {os.environ.get('APP_REVISION', 'development')}")
    return run_root() / selected if selected else None


def render_run_setup() -> None:
    st.subheader("Prepare a discovery run")
    st.caption(
        "Explore parallel directions. Omnigent specialists revisit investments after each result."
    )
    source_column, budget_column = st.columns([1.15, 1], gap="large")
    with source_column, st.container(border=True):
        st.markdown("**01 · Seed and related papers**")
        sources = available_sources()
        imported = st.session_state.pop("intake_selected", None)
        if imported:
            st.session_state["seed_source"] = next(
                (label for label, path in sources.items() if str(path.resolve()) == imported),
                next(iter(sources), None),
            )
        if st.session_state.get("seed_source") not in sources:
            st.session_state.pop("seed_source", None)
        if "seed_source" not in st.session_state:
            saved = st.session_state.get("selected_seed_path")
            st.session_state["seed_source"] = next(
                (label for label, path in sources.items() if str(path.resolve()) == saved),
                next(iter(sources), None),
            )
        source = st.selectbox("Registered source", list(sources), key="seed_source")
        if source:
            st.session_state["selected_seed_path"] = str(sources[source].resolve())
        literature = st.multiselect(
            "Related literature",
            [label for label in sources if label != source],
            max_selections=3,
            default=[
                label
                for label, path in sources.items()
                if label != source
                and str(path.resolve()) in st.session_state.get("selected_literature_paths", [])
            ],
        )
        st.session_state["selected_literature_paths"] = [
            str(sources[label].resolve()) for label in literature
        ]
        st.caption("Choose a saved local paper, or import one above.")
    with budget_column, st.container(border=True):
        st.markdown("**02 · Runtime and local budget**")
        profile = st.selectbox(
            "Environment profile",
            ["Quick verification", "Standard exploration", "Extended exploration"],
            index=1,
        )
        runner = st.selectbox(
            "Decision backend",
            ["Codex subscription · Omnigent", "AnyJev · local Qwen · decision only"],
        )
        backend = "omnigent" if runner.startswith("Codex") else "anyjev"
        runtime = runtime_status() if backend == "anyjev" else {}
        ready = bool(sources) and (backend == "omnigent" or runtime["ready"])
        if backend == "omnigent":
            st.caption(
                "Uses the configured Omnigent host and saved Codex login. "
                "Each role runs in a separate session."
            )
        elif not runtime["ready"]:
            st.info("Prepare the local model with `research prepare-model` after `uv sync`.")
        if not sources:
            st.info("Import a paper above to prepare a run.")
        st.caption(
            "The research agent reads the seed paper to establish its question and context. "
            "Local experiment tools currently support percolation and transit uncertainty; "
            "unsupported papers stop before simulation."
            if backend == "omnigent"
            else "The auxiliary AnyJev backend supports percolation decisions only."
        )
        settings = run_profiles(backend)[profile]
        st.caption(
            f"Profile defaults: {settings.trials} trials/group · {settings.max_workers} workers · "
            f"{settings.max_rounds} batches/direction · {settings.max_seconds // 60} minutes"
        )
        with st.expander("Adjust local simulation budget", expanded=False):
            rounds = st.number_input("Maximum batches per direction", 2, 32, settings.max_rounds)
            workers = st.number_input("Concurrent workers / agents", 1, 16, settings.max_workers)
            trials = st.number_input("Initial trials per group", 8, 4096, settings.trials, step=8)
            seconds = st.number_input(
                "Wall-clock limit (seconds)", 60, 21600, settings.max_seconds, step=60
            )
            calls = st.number_input(
                "Agent request budget", 8, 512, settings.max_agent_calls, step=8
            )
            simulations = st.number_input(
                "Simulation budget including replays",
                1000,
                1000000,
                settings.max_simulations,
                step=1000,
            )
            interval_width = st.number_input(
                "Goal: maximum interval width", 0.05, 0.5, 0.25, step=0.05
            )
            pinned = st.checkbox("Use a specific master seed", value=False)
            seed = st.number_input("Master seed", 0, 2**32 - 1, 20261003) if pinned else None
        st.caption(
            "Independent seed streams for every branch and batch. The master seed is saved. "
            "Decisions follow each result; the loop ends at its goal or declared limits."
        )
        overrides = {
            "max_rounds": rounds,
            "max_workers": workers,
            "trials": trials,
            "max_seconds": seconds,
            "max_agent_calls": calls,
            "max_simulations": simulations,
            "goal_max_interval_width": interval_width,
        }
        if st.button(
            "Start bounded run",
            type="primary",
            width="stretch",
            icon=":material/play_arrow:",
            disabled=not ready or st.session_state.get("research_future") is not None,
        ):
            arguments = (
                sources[source],
                profile,
                backend,
                lambda message: None,
                [sources[label] for label in literature],
                {**overrides, "seed": seed if seed is not None else secrets.randbits(32)},
            )
            if backend == "omnigent":
                st.session_state["following_live_run"] = False
                st.session_state["research_future"] = background_executor().submit(
                    launch_run, *arguments
                )
                st.rerun()
            else:
                with st.status("Executing local decisions…", expanded=True) as status:
                    try:
                        directory = launch_run(*arguments)
                        st.session_state["new_run"] = directory.name
                        status.update(label="Run artifacts saved", state="complete")
                    except Exception as exc:
                        status.update(label="Run stopped", state="error")
                        st.error(
                            f"Execution stopped ({type(exc).__name__}); inspect retained artifacts."
                        )
                    else:
                        st.rerun()
        st.caption(
            "Source and citation researchers propose parallel work. A decision agent reallocates "
            "simulation batches as partial evidence arrives."
        )


def render_path(journal: Journal | None) -> None:
    nodes = []
    for index, step in enumerate(STEPS, start=1):
        records = [d for d in journal.decisions if d.step == step.key] if journal else []
        status = records[-1].status if records else "pending"
        nodes.append(
            f'<div class="node {status}"><div class="node-index">'
            f"{index:02d} / {esc(status.upper())}</div>"
            f'<div class="node-label">{esc(step.title)}</div></div>'
        )
    markup('<div class="path">' + "".join(nodes) + "</div>")


def render_stats(journal: Journal) -> None:
    config = journal.config
    adaptive = journal.report.get("workflow_version") == "4"
    batch_limit = config.get("max_rounds", 0) * (len(journal.proposals) if adaptive else 1)
    stats = [
        ("Recorded decisions", str(len(journal.decisions)), "Every transition has a record"),
        ("Research directions", f"{len(journal.proposals)} / 3", "Only accepted proposals may run"),
        (
            "Artifacts",
            str(len(journal.artifacts)),
            "SHA-256 checked" if journal.verified else "Verification incomplete",
        ),
        (
            "Evaluated batches" if adaptive else "Exploration rounds",
            f"{len(journal.report.get('rounds', []))} / {batch_limit}",
            "Hard stop at the configured budget",
        ),
    ]
    for col, (label, value, detail) in zip(st.columns(4), stats, strict=True):
        with col:
            markup(
                f'<div class="stat"><div class="stat-label">{esc(label)}</div>'
                f'<div class="stat-value">{esc(value)}</div>'
                f'<div class="stat-detail">{esc(detail)}</div></div>'
            )


def render_gate(journal: Journal) -> None:
    validations = [d for d in journal.decisions if d.step == "validation" and d.facts.get("gate")]
    gate = validations[-1].facts["gate"] if validations else {}
    criteria = gate.get("criteria", {})
    labels = {
        "baseline_consistent": "Baseline consistency",
        "numerical_validation": "Numerical validation",
        "detectable_effect": "Detectable effect",
        "independent_review_supports": "Model review supports effect",
        "literature_candidate_gap": "Literature gap",
        "multiple_sources_reviewed": "Multiple sources",
        "reference_evaluator_supports": "Reference evaluator supports contribution",
    }
    rows = "".join(
        f'<div class="criterion"><span class="{"yes" if value is True else "no"}">'
        f"{'✓' if value is True else '○'}</span>{esc(labels.get(key, key))}</div>"
        for key, value in criteria.items()
    )
    status = journal.report.get("status", "in_progress").replace("_", " ")
    title = "Automated candidate" if gate.get("met") is True else "Evidence before advancement"
    markup(
        f'<div class="gate"><div class="small-label">Current gate</div>'
        f'<div class="gate-title">{esc(title)}</div><div class="gate-detail">'
        f"{esc(status.capitalize())}. Scientific novelty remains unverified.</div>{rows}</div>"
    )
    markup(
        '<div class="policy-box"><div class="small-label">Execution boundaries</div>'
        '<div class="policy-row">01 &nbsp; Code defines every next state</div>'
        '<div class="policy-row">02 &nbsp; Agents choose from fixed options</div>'
        '<div class="policy-row">03 &nbsp; Evidence gates control execution</div>'
        '<div class="policy-row">04 &nbsp; Budgets stop further exploration</div>'
        '<div class="policy-row">05 &nbsp; Explanations cannot grant authority</div></div>'
    )


def render_inspector(record: Decision, journal: Journal) -> None:
    spec = STEP_BY_KEY[record.step]
    with st.expander(f"Inspect {record.id} · state, choices & evidence", expanded=False):
        left, right = st.columns(2)
        with left:
            st.markdown("**State → decision**")
            st.caption(f"{spec.role} · {record.stage} · {record.timestamp}")
            contract = decision_contract(record)
            for key, question in contract["questions"].items():
                st.markdown(f"**{key.replace('_', ' ').capitalize()}** · `choice`")
                st.caption(question["instructions"])
                weights = (contract["probabilities"] or {}).get(key) or {}
                for option, description in question["criteria"].items():
                    selected = contract["answers"].get(key) == option
                    score = f" · {weights[option]:.1%}" if option in weights else ""
                    st.write(f"{'●' if selected else '○'} {option}{score} — {description}")
            st.caption(contract["provenance"])
        with right:
            st.markdown("**Execution gate**")
            st.write(spec.gate)
            st.markdown("**Bounded environment**")
            st.write(spec.boundary)
            st.markdown("**Implementation**")
            st.code(spec.implementation, language=None, wrap_lines=True)
        st.markdown("**Evidence attached to this decision**")
        for name in record.evidence:
            digest = journal.artifacts.get(name, {}).get("sha256", "unsealed")
            st.caption(f"{name} · SHA-256 {digest[:16]}")
        if record.step == "reader":
            for proposal in record.facts.get("proposals", []):
                evidence = proposal["evidence"]
                st.text(
                    f"{proposal['title']} · source {evidence['source_id']} · "
                    f"source-local page {evidence['page']}"
                )
                st.text("“" + evidence["quote"] + "”")
        if record.step == "validation":
            for limitation in record.facts.get("review", {}).get("limitations", []):
                st.write("• " + limitation)
        st.json({"contract": contract, "observed_evidence": record.facts}, expanded=False)


def render_journal(journal: Journal) -> None:
    left, right = st.columns([2.2, 1], gap="large")
    with left:
        st.subheader("Decision journal")
        st.caption("What was decided, why it was allowed, and what changed.")
        filters = st.columns([1.4, 1])
        with filters[0]:
            query = st.text_input(
                "Search decisions", placeholder="Search rationale, step or artifact…"
            )
        with filters[1]:
            state_filter = st.selectbox("Show", ["All decisions", "Needs attention", "Recorded"])
        records = [
            d
            for d in journal.decisions
            if (not query or query.casefold() in json.dumps(d.__dict__).casefold())
            and (
                state_filter == "All decisions"
                or (state_filter == "Needs attention" and d.status != "recorded")
                or (state_filter == "Recorded" and d.status == "recorded")
            )
        ]
        if not records:
            st.info("No decisions match this filter.")
        for record in reversed(records):
            spec = STEP_BY_KEY[record.step]
            label = "NEEDS REVIEW" if record.status == "review" else record.status.upper()
            markup(
                f'<div class="decision {record.status}"><div class="decision-top">'
                f'<span class="decision-meta">{esc(record.id)} &nbsp; / &nbsp; '
                f"{esc(spec.role.upper())} &nbsp; · &nbsp; "
                f"{'ROUND ' + str(record.round) if record.round else 'FOUNDATION'}</span>"
                f'<span class="pill {record.status}">{esc(label)}</span></div>'
                f'<div class="decision-title">{esc(record.choice)}</div>'
                f'<div class="decision-body">{esc(record.rationale)}</div></div>'
            )
            render_inspector(record, journal)
    with right:
        st.subheader("Control boundary")
        st.caption("Policy determines where this run can go.")
        render_gate(journal)
        st.download_button(
            "Export decision ledger",
            journal.export(),
            file_name=f"{journal.run_id}-decisions.json",
            mime="application/json",
            width="stretch",
            icon=":material/download:",
        )


def render_implementations(journal: Journal) -> None:
    st.subheader("Directions & implementations")
    st.caption("A proposal becomes executable only after critique and a matching plan.")
    if not journal.proposals:
        st.info("No source-backed proposals have been recorded yet.")
    columns = st.columns(max(1, len(journal.proposals)))
    for column, proposal in zip(columns, journal.proposals, strict=False):
        planned = any(
            d.step == "planner" and d.facts.get("proposal_id") == proposal["id"]
            for d in journal.decisions
        )
        with column:
            markup(
                f'<div class="proposal"><span class="pill {"recorded" if planned else "pending"}">'
                f"{'IMPLEMENTATION LOCKED' if planned else 'PROPOSED'}</span>"
                f"<h4>{esc(proposal['title'])}</h4><p>{esc(proposal['hypothesis'])}</p>"
                f'<div class="decision-meta">{esc(proposal["experiment"])}</div></div>'
            )
    st.write("")
    for record in journal.decisions:
        if record.step in {"planner", "experiment", "baseline"}:
            with st.container(border=True):
                st.markdown(f"**{record.id} · {STEP_BY_KEY[record.step].title}**")
                st.write(record.choice)
                st.caption(STEP_BY_KEY[record.step].implementation)
                st.json(record.facts, expanded=False)
    st.subheader("Allowed transition path")
    for index, step in enumerate(STEPS):
        st.markdown(f"**{index + 1:02d} · {step.title}** — {step.gate}")
        st.caption("Allowed: " + " / ".join(step.choices))
    st.info(
        "After validation, the engine can finish its automated assessment or repeat literature → "
        "plan → experiment → validation for the same proposal within the round budget."
    )


def render_artifacts(journal: Journal) -> None:
    st.subheader("Evidence vault")
    st.caption(
        "Original run artifacts remain unchanged. Downloads come from the selected run only."
    )
    names = sorted(journal.artifacts)
    if not names:
        st.info("The manifest is not sealed yet. Refresh after the run finishes.")
        return
    from hacknation_databricks.research.activity import load_activity
    from hacknation_databricks.research_views import artifact_origin, label

    nodes = load_activity(journal)
    producers = {name: label(node.role) for node in nodes for name in node.artifacts}
    origins = {name: artifact_origin(name) for name in names}
    counts = st.columns(3)
    counts[0].metric(
        "Agent responses", sum(value == "Agent response" for value in origins.values())
    )
    counts[1].metric(
        "Simulation data files", sum(value == "Simulation data" for value in origins.values())
    )
    counts[2].metric("Sealed artifacts", len(names))
    category = st.selectbox("Artifact origin", ["All origins", *sorted(set(origins.values()))])
    names = [name for name in names if category == "All origins" or origins[name] == category]
    st.dataframe(
        [
            {
                "Artifact": name,
                "Origin": origins[name],
                "Recorded step": producers.get(name, "Supervisor / input"),
                "Bytes": journal.artifacts[name]["bytes"],
                "SHA-256": journal.artifacts[name]["sha256"],
            }
            for name in names
        ],
        hide_index=True,
        width="stretch",
        alt="Generated artifacts with origin and recorded producing step",
    )
    selected = st.selectbox("Inspect artifact", names)
    try:
        raw = read_artifact(journal.directory, selected)
        if selected.endswith(".json"):
            st.json(json.loads(raw), expanded=False)
        elif selected.endswith((".txt", ".csv", ".jsonl", ".py")):
            st.code(raw[:20000].decode("utf-8", errors="replace"), language=None)
            if len(raw) > 20000:
                st.caption("Preview limited to 20 KB. Download contains the complete artifact.")
        st.download_button(
            "Download artifact", raw, file_name=Path(selected).name, icon=":material/download:"
        )
    except (OSError, ValueError, KeyError):
        st.error("This artifact could not be safely read. The run needs review.")


def render_environment(journal: Journal) -> None:
    st.subheader("Pinned environment")
    st.caption("Inputs, limits and implementation identity are recorded before the first decision.")
    left, right = st.columns(2)
    with left:
        st.markdown("**Run contract**")
        st.json(journal.config)
    with right:
        st.markdown("**Implementation identity**")
        st.json(journal.environment)
        st.caption(f"Viewer policy: {POLICY_VERSION}")
        st.markdown(
            "[Jev decision pattern · official documentation](https://docs.typesafe.ai/introduction)"
        )
        st.write(
            "This interface uses state, closed choices, evidence and code-controlled gates. "
            "Omnigent runs parallel researchers and a decision agent. The optional AnyJev "
            "backend records local option weights; these are not calibrated confidence."
        )
    st.markdown("**Registered source evidence**")
    for source in journal.sources:
        with st.container(border=True):
            st.text(source.get("title", source["source_id"]))
            st.caption(f"{source['source_id']} · {source['kind']} · SHA-256 {source['sha256']}")
            url = source.get("url", "")
            if urlsplit(url).scheme in {"http", "https"}:
                st.link_button("Open source", url)
            if source["kind"] == "curated_excerpt":
                st.warning(
                    "Curated excerpt only. Page numbers refer to the excerpt, not the PDF. "
                    "This run does not demonstrate automated full-paper extraction."
                )


def selected_journal() -> Journal | None:
    selected = st.session_state.get("run_selection")
    if not selected:
        st.info("No runs have been recorded. Open Source intake to choose a seed and start a run.")
        return None
    journal = load_journal(run_root() / selected)
    if journal.issues:
        st.error("Evidence verification failed. This run is quarantined from the decision views.")
        for issue in journal.issues:
            st.write(issue)
        st.download_button(
            "Download diagnostic ledger",
            journal.export(),
            file_name="decision-ledger-diagnostic.json",
            mime="application/json",
        )
        return None
    backend = journal.report.get("backend", "unknown")
    st.caption(
        f"{journal.run_id} · {backend.upper()} · "
        f"{journal.report.get('status', 'running').replace('_', ' ')} · "
        f"{'Artifacts verified' if journal.verified else 'Unsealed live snapshot'}"
    )
    if backend != "omnigent":
        st.info("Auxiliary run: no live Omnigent collaboration is claimed for this backend.")
    return journal


@st.fragment(run_every=5)
def render_selected_run():
    journal = selected_journal()
    if journal is None:
        return
    from hacknation_databricks.synthesis_ui import render_research_path

    with st.expander("Research question, seed paper and reviewed directions"):
        render_research_path(journal)
    render_discovery(journal)


def main() -> None:
    st.title("Discovery overview")
    st.caption("Follow a seed paper from grounded directions to the next scientific decision.")
    render_selected_run()


if __name__ == "__main__":
    # Supports direct developer previews as well as the multipage entrypoint.
    st.set_page_config(page_title="Omnigent lab", layout="wide")
    markup(CSS)
    render_sidebar()
    main()
