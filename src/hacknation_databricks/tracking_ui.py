"""Exploration control room: bounded controls and an inspectable decision journal."""

import fcntl
import html
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

import streamlit as st

from hacknation_databricks.activity_ui import render_activity
from hacknation_databricks.research.decision_runtime import runtime_status
from hacknation_databricks.research.intake import list_sources, source_root
from hacknation_databricks.research.models import RunConfig
from hacknation_databricks.research.sources import read_source
from hacknation_databricks.research.workflow import run_research
from hacknation_databricks.source_ui import render_sources
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
    sources = {}
    registered, _ = list_sources(source_root())
    for source in registered:
        sources[f"{source.title} · {source.sha256[:8]}"] = Path(source.path)
    configured = os.environ.get("RESEARCH_PAPER_PATH")
    if configured and Path(configured).is_file():
        sources["Registered project source"] = Path(configured)
    for path in (Path("data/papers/2607.24975v1.pdf"), Path(".cache/research/paper.pdf")):
        if path.is_file():
            sources["Full paper · arXiv v1"] = path
            break
    return sources


def launch_run(
    source_path: Path,
    profile: str,
    backend: str,
    progress,
    literature_paths: list[Path] | None = None,
) -> Path:
    """Closed launch boundary: controls choose profiles, never executable instructions."""
    registered = {p.resolve() for p in available_sources().values()}
    if any(p.resolve() not in registered for p in [source_path, *(literature_paths or [])]):
        raise ValueError("Source is not registered")
    profiles = {
        "Quick verification": RunConfig(
            sizes=[8, 16], trials=32, max_rounds=2, max_seconds=600, max_simulations=2000
        ),
        "Standard exploration": RunConfig(
            sizes=[16, 32], trials=128, max_rounds=2, max_seconds=900, max_simulations=12000
        ),
    }
    if profile not in profiles or backend not in {"anyjev", "omnigent"}:
        raise ValueError("Unknown run profile or backend")
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
            profiles[profile],
            backend=backend,
            literature=literature,
            progress=progress,
            cache=Path(".cache/simulations"),
            retrieval_report=retrieval,
        )
    return directory


def render_sidebar() -> Path | None:
    with st.sidebar:
        markup(
            '<div class="brand"><b>◈</b> exploration</div>'
            '<div class="brand-sub">RESEARCH CONTROL ROOM</div>'
        )
        markup('<div class="eyebrow">Workspace</div>')
        runs = discover_runs(run_root())
        names = [path.name for path in runs]
        chosen = st.session_state.get("new_run")
        index = names.index(chosen) if chosen in names else 0
        selected = st.selectbox(
            "Exploration run",
            names,
            index=index if names else None,
            placeholder="No recorded runs yet",
        )
        if st.button("Refresh artifacts", use_container_width=True, icon=":material/refresh:"):
            st.rerun()
        st.divider()
        markup('<div class="eyebrow">New bounded run</div>')
        sources = available_sources()
        imported = st.session_state.pop("intake_selected", None)
        if imported:
            st.session_state["seed_source"] = next(
                (label for label, path in sources.items() if str(path.resolve()) == imported),
                next(iter(sources), None),
            )
        if st.session_state.get("seed_source") not in sources:
            st.session_state.pop("seed_source", None)
        source = st.selectbox("Registered source", list(sources), key="seed_source")
        literature = st.multiselect(
            "Related literature",
            [label for label in sources if label != source],
            max_selections=3,
        )
        st.caption("Add PDF, Markdown or arXiv sources in Source intake below.")
        profile = st.selectbox(
            "Environment profile", ["Quick verification", "Standard exploration"]
        )
        runner = st.selectbox(
            "Decision backend",
            ["Codex subscription · Omnigent", "AnyJev · local Qwen · decision only"],
        )
        backend = "omnigent" if runner.startswith("Codex") else "anyjev"
        runtime = runtime_status()
        ready = bool(sources) and (backend == "omnigent" or runtime["ready"])
        if backend == "omnigent":
            st.caption(
                "Uses the configured Omnigent host and saved Codex login. "
                "Each role runs in a separate session."
            )
        elif not runtime["ready"]:
            st.info("Prepare the local model with `research prepare-model` after `uv sync`.")
        if not sources:
            st.info("Add a seed in Source intake below.")
        st.caption(
            "2 rounds · 2 workers · fixed seed\n\n"
            + (
                "32 trials / size · 600s limit"
                if profile == "Quick verification"
                else "128 trials / size · 900s limit"
            )
        )
        if st.button(
            "Start bounded run",
            type="primary",
            use_container_width=True,
            icon=":material/play_arrow:",
            disabled=not ready,
        ):
            with st.status("Executing the fixed workflow…", expanded=True) as status:
                try:
                    directory = launch_run(
                        sources[source],
                        profile,
                        backend,
                        st.write,
                        [sources[label] for label in literature],
                    )
                    st.session_state["new_run"] = directory.name
                    status.update(label="Run artifacts saved", state="complete")
                except ValueError as exc:
                    status.update(label="Run stopped", state="error")
                    st.error(str(exc))
                except Exception as exc:
                    status.update(label="Run stopped", state="error")
                    st.error(
                        f"Execution stopped ({type(exc).__name__}). "
                        "Refresh to inspect any saved audit events."
                    )
                else:
                    st.rerun()
        st.caption(
            "Every run starts at source intake. Decisions cannot jump stages or widen scope."
        )
        st.divider()
        if backend == "anyjev":
            st.caption("Jev-style contracts\n\nState → closed choice → code-enforced gate")
            st.caption(
                "AnyJev L0 · open weights · no generated text\n\nOption scores are uncalibrated."
            )
        else:
            st.caption("Omnigent sessions → validated JSON → source and numerical checks")
            st.caption("Reference-grounded evaluation · bounded calls · no human approval gate")
        st.caption("Not legal advice.")
        st.caption(f"Deployed revision: {os.environ.get('APP_REVISION', 'development')}")
    return run_root() / selected if selected else None


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
    stats = [
        ("Recorded decisions", str(len(journal.decisions)), "Every transition has a record"),
        ("Research directions", f"{len(journal.proposals)} / 3", "Only accepted proposals may run"),
        (
            "Artifacts",
            str(len(journal.artifacts)),
            "SHA-256 checked" if journal.verified else "Verification incomplete",
        ),
        (
            "Exploration rounds",
            f"{len(journal.report.get('rounds', []))} / {config.get('max_rounds', '—')}",
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
            use_container_width=True,
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
    st.dataframe(
        [
            {"Artifact": name, "Bytes": item["bytes"], "SHA-256": item["sha256"]}
            for name, item in sorted(journal.artifacts.items())
        ],
        hide_index=True,
        use_container_width=True,
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
            "New runs use AnyJev with local Qwen logits. Decisions record every option weight "
            "and zero generated tokens. L0 weights are not calibrated confidence."
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


def main() -> None:
    st.set_page_config(
        page_title="Exploration · Decision control room", page_icon="◈", layout="wide"
    )
    markup(CSS)
    selected = render_sidebar()
    markup('<div class="eyebrow">Research operations &nbsp; / &nbsp; Decision tracking</div>')
    title_col, badge_col = st.columns([5, 1])
    with title_col:
        st.title("Exploration control room")
    with badge_col:
        markup('<span class="pill">BOUNDED WORKFLOW</span>')
    st.caption("Follow the evidence. Inspect every decision. Keep exploration inside its contract.")
    if selected is None:
        render_sources()
        render_path(None)
        st.subheader("Your first exploration starts with a fixed boundary.")
        st.write(
            "Select a registered source and environment profile in the sidebar, then start a "
            "bounded run. The journal will fill from actual saved decisions and artifacts."
        )
        cols = st.columns(3)
        for col, label, body in zip(
            cols,
            ["01 / Closed choices", "02 / Evidence gates", "03 / Reproducible runs"],
            [
                "Up to three directions, three experiment recipes, one ordered path.",
                "Inspect quotations, critique, validation and every reason to stop.",
                "Pinned seeds, code snapshots and hashed artifacts for every run.",
            ],
            strict=True,
        ):
            with col:
                markup(
                    f'<div class="proposal"><div class="small-label">{label}</div>'
                    f"<p>{body}</p></div>"
                )
        st.info(
            "No runs have been recorded in this workspace. AnyJev will select source-backed "
            "directions with the local model, then execute only the approved experiment."
        )
        return
    journal = load_journal(selected)
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
        return
    backend = journal.report.get("backend", "unknown")
    source_kind = journal.report.get("source_kind", "unknown")
    markup(
        f'<div class="context">{esc(journal.run_id)} &nbsp; / &nbsp; '
        f"{esc(backend.upper())} &nbsp; / &nbsp; "
        f"{esc(source_kind.replace('_', ' '))} &nbsp; / &nbsp; "
        f"{'Artifacts verified' if journal.verified else 'Run not sealed'}</div>"
    )
    if backend == "anyjev":
        usage = journal.report.get("decision_usage", {})
        st.info(
            f"Model decisions · {journal.report.get('decision_calls', 0)} closed questions · "
            f"{usage.get('prefills', 0)} model prefills · 0 generated tokens. "
            "Inspect any step for competing options, scores and source evidence."
        )
    if backend == "scripted":
        st.info(
            "Scripted research run · numerical experiments are real; role decisions use fixed "
            "responses. No live agents or verified novelty are claimed.",
            icon=":material/info:",
        )
    render_stats(journal)
    render_path(journal)
    tabs = st.tabs(
        [
            "Agents & loops",
            "Decision journal",
            "Source intake",
            "Implementations & path",
            "Artifacts",
            "Environment",
            "Original vs follow-up",
        ]
    )
    with tabs[0]:
        render_activity(journal)
    with tabs[1]:
        render_journal(journal)
    with tabs[2]:
        render_sources()
    with tabs[3]:
        render_implementations(journal)
    with tabs[4]:
        render_artifacts(journal)
    with tabs[5]:
        render_environment(journal)
    with tabs[6]:
        from hacknation_databricks.comparison_ui import render_comparison

        render_comparison(journal.directory, journal.report)


if __name__ == "__main__":
    main()
