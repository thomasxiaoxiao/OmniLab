"""OmniLab scientific discovery lab: bounded controls and an inspectable decision journal."""

import fcntl
import hashlib
import html
import json
import os
import secrets
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from queue import SimpleQueue
from urllib.parse import urlsplit
from uuid import uuid4

from hacknation_databricks.research.intake import source_root
from hacknation_databricks.research.models import RunConfig
from hacknation_databricks.research.sources import read_source
from hacknation_databricks.research.workflow import run_research
from hacknation_databricks.seed_catalog import seed_examples
from hacknation_databricks.source_cache import source_library
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
from hacknation_databricks.web import components as ui


def esc(value: object) -> str:
    return html.escape(str(value))


def markup(value: str) -> None:
    ui.markdown(value, unsafe_allow_html=True)


def run_root() -> Path:
    return Path(
        os.environ.get(
            "RESEARCH_RUNS_DIR", os.environ.get("RESEARCH_OUTPUT_DIR", "output/research")
        )
    )


def available_sources() -> dict[str, Path]:
    registered, _ = source_library(source_root())
    return {
        **{f"{source.title} · {source.sha256[:8]}": Path(source.path) for source in registered},
        **seed_examples(),
    }


def scope_runs_to_source():
    """An explicit paper change must not leave another paper's run selected."""
    source = available_sources().get(
        ui.session_state.get(
            "uploaded_source"
            if ui.session_state.get("paper_input_mode") == "Uploaded paper"
            else "seed_source"
        )
    )
    if source is not None:
        ui.session_state["source_scope_sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
        ui.session_state["selected_seed_path"] = str(source.resolve())
    ui.session_state.pop("selected_literature_paths", None)


def runs_for_source(runs, digest):
    if not digest:
        return runs
    matching = []
    for directory in runs:
        try:
            sources = json.loads((directory / "sources.json").read_text())
            if any(s.get("source_id") == "seed" and s.get("sha256") == digest for s in sources):
                matching.append(directory)
        except (OSError, ValueError, TypeError, AttributeError):
            continue
    return matching


def latest_runs_by_paper(runs):
    """Keep the newest attempt per paper, including failed attempts; never hide a failure."""
    seen, latest = set(), []
    for directory in runs:
        identity = str(directory)
        try:
            sources = json.loads(read_artifact(directory, "sources.json"))
            identity = next(s["sha256"] for s in sources if s.get("source_id") == "seed")
        except (OSError, ValueError, TypeError, KeyError, AttributeError, StopIteration):
            pass
        if identity not in seen:
            latest.append(directory)
            seen.add(identity)
    return latest


def run_profiles(backend="omnigent"):
    shared = {
        "workflow": "adaptive" if backend == "omnigent" else "sequential",
        "domain": "auto" if backend == "omnigent" else "percolation",
        "decision_backend": "anyjev" if backend == "omnigent" else "codex",
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
    *,
    run_name: str | None = None,
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
            "workflow",
            "decision_backend",
            "allow_paper_implementation",
            "repository_url",
            "repository_ref",
            "code_timeout_seconds",
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
        import httpx

        server = os.environ.get("OMNIGENT_SERVER_URL", "http://127.0.0.1:6767")
        parsed = urlsplit(server)
        if (
            parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or not (
                parsed.scheme == "https"
                or parsed.scheme == "http"
                and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
            )
        ):
            raise ValueError(
                "Omnigent requires HTTPS or a local HTTP server without URL credentials."
            )
        try:
            response = httpx.get(
                server.rstrip("/") + "/v1/hosts",
                headers={"Authorization": f"Bearer {os.environ['OMNIGENT_API_TOKEN']}"}
                if os.environ.get("OMNIGENT_API_TOKEN")
                else {},
                timeout=5,
            )
            response.raise_for_status()
            hosts = response.json()["hosts"]
            host_id = os.environ.get("OMNIGENT_HOST_ID")
            if host_id and not any(
                h.get("host_id") == host_id and h.get("status") == "online" for h in hosts
            ):
                raise ValueError("Configured Omnigent host is offline. Start the host and retry.")
        except (httpx.HTTPError, KeyError):
            raise ValueError(
                "Omnigent is unavailable. Start its server and host with "
                "scripts/research-runtime.sh, then retry. Your uploaded paper is saved."
            ) from None
        progress("Retrieve cited references for automated evaluation")
        retrieved, retrieval = retrieve_references(
            source, Path("data/literature"), existing=literature
        )
        literature.extend(retrieved)
    name = run_name or datetime.now(UTC).strftime("%Y%m%dT%H%M%S") + "-" + uuid4().hex[:8]
    if Path(name).name != name or name in {".", ".."}:
        raise ValueError("Invalid run name")
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


@ui.cache_resource
def background_executor():
    return ThreadPoolExecutor(max_workers=1, thread_name_prefix="research-ui")


@ui.fragment(run_every=3)
def render_launch_monitor():
    if ui.session_state.get("research_launch_error"):
        ui.error(ui.session_state["research_launch_error"])
    future = ui.session_state.get("research_future")
    if future is None:
        return
    if future.done():
        ui.session_state.pop("research_future")
        try:
            directory = future.result()
            ui.session_state["new_run"] = directory.name
        except Exception as exc:
            active = ui.session_state.get("research_active_run")
            if active and (run_root() / active / "report.json").is_file():
                ui.session_state["new_run"] = active
            ui.session_state["research_launch_error"] = (
                str(exc)
                if isinstance(exc, ValueError)
                else f"Run stopped ({type(exc).__name__}); inspect retained artifacts."
            )
        ui.rerun()
    else:
        messages = ui.session_state.get("research_progress")
        if messages is not None:
            while not messages.empty():
                ui.session_state["research_progress_latest"] = messages.get_nowait()
        ui.info(ui.session_state.get("research_progress_latest", "Preparing paper research…"))
        ui.caption("Worker steps and saved results refresh automatically every five seconds.")
        if not ui.session_state.get("following_live_run"):
            name = ui.session_state.get("research_active_run")
            if name and (run_root() / name / "report.json").is_file():
                ui.session_state["new_run"] = name
                ui.session_state["following_live_run"] = True
                ui.rerun()


def render_sidebar() -> Path | None:
    """Run context only; intake and launch controls live on their own page."""
    imported = ui.session_state.pop("intake_selected", None)
    if imported:
        ui.session_state["paper_input_mode"] = "Uploaded paper"
        ui.session_state["uploaded_source"] = next(
            (
                label
                for label, path in available_sources().items()
                if str(path.resolve()) == imported
            ),
            None,
        )
        scope_runs_to_source()
    with ui.sidebar:
        markup('<div class="brand"><b>◈</b> OmniLab</div>')
        ui.caption("SCIENTIFIC DISCOVERY")
        runs = runs_for_source(
            discover_runs(run_root()), ui.session_state.get("source_scope_sha256")
        )
        active_name = ui.session_state.get("research_active_run")
        if active_name and (
            ui.session_state.get("research_future") is not None
            or ui.session_state.get("run_selection") == active_name
            or ui.session_state.get("new_run") == active_name
        ):
            runs.sort(key=lambda path: path.name != active_name)
        if not ui.checkbox("Show previous runs", value=True, key="show_previous_runs"):
            runs = latest_runs_by_paper(runs)
        names = [path.name for path in runs]
        chosen = ui.session_state.pop("new_run", None)
        if chosen in names:
            ui.session_state["run_selection"] = chosen
        if ui.session_state.get("run_selection") not in names:
            ui.session_state.pop("run_selection", None)
        selected = ui.selectbox(
            "Exploration run",
            names,
            key="run_selection",
            placeholder="No recorded runs yet",
        )
        if ui.button("Refresh artifacts", width="stretch", icon=":material/refresh:"):
            ui.rerun()
        render_launch_monitor()
        ui.divider()
        ui.caption("Seed paper → grounded proposals → bounded tests → updated decision")
        ui.caption("Research prototype · scientific conclusions require further validation.")
        ui.caption(f"Deployed revision: {os.environ.get('APP_REVISION', 'development')}")
    return run_root() / selected if selected else None


def render_run_setup() -> None:
    from hacknation_databricks.source_ui import render_sources

    source_column, budget_column = ui.columns([1.15, 1], gap="large")
    with source_column, ui.container(border=True):
        ui.markdown("**01 · Source paper**")
        with ui.expander("Add papers · upload or arXiv", expanded=False):
            render_sources()
        _, issues = source_library(source_root())
        for issue in issues:
            ui.warning(issue)
        sources = available_sources()
        examples = seed_examples()
        mode = ui.selectbox(
            "Paper source",
            ["Seed example", "Uploaded paper"],
            index=0 if examples else 1,
            key="paper_input_mode",
            on_change=scope_runs_to_source,
        )
        if ui.session_state.get("seed_source") not in examples:
            ui.session_state.pop("seed_source", None)
        example = ui.selectbox(
            "Seed paper",
            list(examples),
            key="seed_source",
            on_change=scope_runs_to_source,
            disabled=mode != "Seed example",
        )
        ui.caption("Seed examples are limited to Percolation and AstroSat. Uploads stay separate.")
        if mode == "Uploaded paper":
            uploads = {label: path for label, path in sources.items() if label not in examples}
            if ui.session_state.get("uploaded_source") not in uploads:
                ui.session_state.pop("uploaded_source", None)
            source = ui.selectbox(
                "Uploaded paper",
                list(uploads),
                key="uploaded_source",
                on_change=scope_runs_to_source,
            )
        else:
            source = example
        if source:
            ui.session_state["selected_seed_path"] = str(sources[source].resolve())
        else:
            ui.session_state.pop("selected_seed_path", None)
        # Discard removed picker state so references cannot carry across papers.
        ui.session_state.pop("selected_literature_paths", None)
        from hacknation_databricks.research.repository_source import repository_links

        links = repository_links(read_source(sources[source])) if source else {}
        repository_url = ui.text_input(
            "Paper's GitHub repository (optional)",
            value=next(iter(links)) if len(links) == 1 else "",
            key=f"repository-url-{source}",
            placeholder="https://github.com/owner/repository",
            help="Use the implementation cited by the paper, or supply a related "
            "repository explicitly. Leave blank to implement a scoped test from the paper.",
        )
        repository_ref = ui.text_input(
            "Repository version",
            value="HEAD",
            help="A commit, tag, or branch; the run saves the resolved commit.",
        )
    with budget_column, ui.container(border=True):
        ui.markdown("**02 · Runtime and local budget**")
        profile = ui.selectbox(
            "Environment profile",
            ["Quick verification", "Standard exploration", "Extended exploration"],
            index=1,
        )
        backend = "omnigent"
        ui.markdown("**Researcher agent:** Codex + Omnigent")
        ui.markdown("**Experimenter and evaluator:** Codex + Omnigent")
        ui.caption(
            "Specialists read the paper and any supplied code, critique directions, "
            "compare tests, generate and run an experiment, "
            "and use its measurements to choose the next test."
        )
        ready = source is not None
        if not ready:
            ui.info("Import a paper above to prepare a run.")
        ui.caption(
            "The run will use the linked repository. A failed retrieval stops the run."
            if repository_url.strip()
            else "No repository selected: agents will implement a scoped test from the paper. "
            "They may stop if its evidence or required data cannot support a valid experiment."
        )
        ui.caption(
            "Offline Python (standard library, NumPy, SciPy) and C17 code can run in "
            "Omnigent's OS sandbox. No network or package installation during experiments."
        )
        settings = run_profiles(backend)[profile]
        policy_draft = ui.session_state.get("omnigent_policy_drafts", {}).get(profile, {})
        if policy_draft:
            settings = RunConfig.model_validate({**settings.model_dump(), **policy_draft})
            ui.caption("Saved next-run policy applied. You can adjust its limits below.")
        ui.caption(
            f"Launch limits: up to {min(settings.trials, 32)} paired replicates · "
            f"{settings.max_rounds} experiments · {settings.max_seconds // 60} minutes"
        )
        with ui.expander("Adjust local simulation budget", expanded=False):
            rounds = ui.number_input("Maximum experiments", 2, 32, settings.max_rounds)
            trials = ui.number_input(
                "Maximum paired replicates", 8, 32, min(settings.trials, 32), step=8
            )
            code_timeout = ui.number_input(
                "Code execution limit per experiment (seconds)",
                1,
                180,
                settings.code_timeout_seconds,
            )
            seconds = ui.number_input(
                "Wall-clock limit (seconds)", 60, 21600, settings.max_seconds, step=60
            )
            calls = ui.number_input(
                "Agent request budget", 8, 512, settings.max_agent_calls, step=8
            )
            simulations = ui.number_input(
                "Simulation budget including replays",
                1000,
                1000000,
                settings.max_simulations,
                step=1000,
            )
            pinned = ui.checkbox("Use a specific master seed", value=False)
            seed = ui.number_input("Master seed", 0, 2**32 - 1, 20261003) if pinned else None
        ui.caption(
            "Control and proposed runs share seeds. Each experiment gets new seeds. "
            "Reader and literature researcher work concurrently, then hand their findings "
            "to the critic. One reviewed direction proceeds through bounded experiments; "
            "the evaluator explains every continuation or stop."
        )
        overrides = {
            "workflow": "repository",
            "allow_paper_implementation": True,
            "decision_backend": "codex",
            "repository_url": repository_url.strip(),
            "repository_ref": repository_ref.strip(),
            "max_rounds": rounds,
            "max_workers": min(2, settings.max_workers),
            "trials": trials,
            "code_timeout_seconds": code_timeout,
            "max_seconds": seconds,
            "max_agent_calls": calls,
            "max_simulations": simulations,
        }
        if ui.button(
            "Start bounded run",
            type="primary",
            width="stretch",
            icon=":material/play_arrow:",
            disabled=not ready or ui.session_state.get("research_future") is not None,
        ):
            ui.session_state.pop("research_launch_error", None)
            progress_messages = SimpleQueue()
            arguments = (
                sources[source],
                profile,
                backend,
                progress_messages.put,
                [],
                {**overrides, "seed": seed if seed is not None else secrets.randbits(32)},
            )
            name = datetime.now(UTC).strftime("%Y%m%dT%H%M%S") + "-" + uuid4().hex[:8]
            ui.session_state["research_active_run"] = name
            ui.session_state["research_progress"] = progress_messages
            ui.session_state["research_progress_latest"] = "Checking Omnigent connection…"
            ui.session_state["following_live_run"] = False
            ui.session_state["research_future"] = background_executor().submit(
                launch_run, *arguments, run_name=name
            )
            ui.switch_page("app_pages/agents.py")
        ui.caption(
            "The run preserves paper evidence, repository code, agent handoffs, "
            "measurements, and the reason for each next step."
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
    for col, (label, value, detail) in zip(ui.columns(4), stats, strict=True):
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
    with ui.expander(f"Inspect {record.id} · state, choices & evidence", expanded=False):
        left, right = ui.columns(2)
        with left:
            ui.markdown("**State → decision**")
            ui.caption(f"{spec.role} · {record.stage} · {record.timestamp}")
            contract = decision_contract(record)
            for key, question in contract["questions"].items():
                ui.markdown(f"**{key.replace('_', ' ').capitalize()}** · `choice`")
                ui.caption(question["instructions"])
                weights = (contract["probabilities"] or {}).get(key) or {}
                for option, description in question["criteria"].items():
                    selected = contract["answers"].get(key) == option
                    score = f" · {weights[option]:.1%}" if option in weights else ""
                    ui.write(f"{'●' if selected else '○'} {option}{score} — {description}")
            ui.caption(contract["provenance"])
        with right:
            ui.markdown("**Execution gate**")
            ui.write(spec.gate)
            ui.markdown("**Bounded environment**")
            ui.write(spec.boundary)
            ui.markdown("**Implementation**")
            ui.code(spec.implementation, language=None, wrap_lines=True)
        ui.markdown("**Evidence attached to this decision**")
        for name in record.evidence:
            digest = journal.artifacts.get(name, {}).get("sha256", "unsealed")
            ui.caption(f"{name} · SHA-256 {digest[:16]}")
        if record.step == "reader":
            for proposal in record.facts.get("proposals", []):
                evidence = proposal["evidence"]
                ui.text(
                    f"{proposal['title']} · source {evidence['source_id']} · "
                    f"source-local page {evidence['page']}"
                )
                ui.text("“" + evidence["quote"] + "”")
        if record.step == "validation":
            for limitation in record.facts.get("review", {}).get("limitations", []):
                ui.write("• " + limitation)
        ui.json({"contract": contract, "observed_evidence": record.facts}, expanded=False)


def render_journal(journal: Journal) -> None:
    left, right = ui.columns([2.2, 1], gap="large")
    with left:
        ui.subheader("Decision journal")
        ui.caption("What was decided, why it was allowed, and what changed.")
        filters = ui.columns([1.4, 1])
        with filters[0]:
            query = ui.text_input(
                "Search decisions", placeholder="Search rationale, step or artifact…"
            )
        with filters[1]:
            state_filter = ui.selectbox("Show", ["All decisions", "Needs attention", "Recorded"])
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
            ui.info("No decisions match this filter.")
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
        ui.subheader("Control boundary")
        ui.caption("Policy determines where this run can go.")
        render_gate(journal)
        ui.download_button(
            "Export decision ledger",
            journal.export(),
            file_name=f"{journal.run_id}-decisions.json",
            mime="application/json",
            width="stretch",
            icon=":material/download:",
        )


def render_implementations(journal: Journal) -> None:
    ui.subheader("Directions & implementations")
    ui.caption("A proposal becomes executable only after critique and a matching plan.")
    if not journal.proposals:
        ui.info("No source-backed proposals have been recorded yet.")
    columns = ui.columns(max(1, len(journal.proposals)))
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
    ui.write("")
    for record in journal.decisions:
        if record.step in {"planner", "experiment", "baseline"}:
            with ui.container(border=True):
                ui.markdown(f"**{record.id} · {STEP_BY_KEY[record.step].title}**")
                ui.write(record.choice)
                ui.caption(STEP_BY_KEY[record.step].implementation)
                ui.json(record.facts, expanded=False)
    ui.subheader("Allowed transition path")
    for index, step in enumerate(STEPS):
        ui.markdown(f"**{index + 1:02d} · {step.title}** — {step.gate}")
        ui.caption("Allowed: " + " / ".join(step.choices))
    ui.info(
        "After validation, the engine can finish its automated assessment or repeat literature → "
        "plan → experiment → validation for the same proposal within the round budget."
    )


def render_artifacts(journal: Journal) -> None:
    ui.subheader("Evidence vault")
    ui.caption(
        "Original run artifacts remain unchanged. Downloads come from the selected run only."
    )
    names = sorted(journal.artifacts)
    if not names:
        ui.info("The manifest is not sealed yet. Refresh after the run finishes.")
        return
    implementation_files = set()
    if "implementation.json" in names:
        implementation_files = set(
            json.loads(read_artifact(journal.directory, "implementation.json")).get("files", [])
        )
    if not ui.checkbox("Include framework provenance", value=False):
        names = [
            name
            for name in names
            if not name.startswith("framework/")
            and (not name.startswith("code/") or name in implementation_files)
        ]
    from hacknation_databricks.research.activity import load_activity
    from hacknation_databricks.research_views import artifact_origin, label

    nodes = load_activity(journal)
    producers = {name: label(node.role) for node in nodes for name in node.artifacts}
    origins = {name: artifact_origin(name) for name in names}
    counts = ui.columns(3)
    counts[0].metric(
        "Agent responses", sum(value == "Agent response" for value in origins.values())
    )
    counts[1].metric(
        "Simulation data files", sum(value == "Simulation data" for value in origins.values())
    )
    counts[2].metric("Sealed artifacts", len(names))
    category = ui.selectbox("Artifact origin", ["All origins", *sorted(set(origins.values()))])
    names = [name for name in names if category == "All origins" or origins[name] == category]
    ui.dataframe(
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
    selected = ui.selectbox("Inspect artifact", names)
    try:
        raw = read_artifact(journal.directory, selected)
        if selected.endswith(".json"):
            ui.json(json.loads(raw), expanded=False)
        elif selected.endswith((".txt", ".csv", ".jsonl", ".py")):
            ui.code(raw[:20000].decode("utf-8", errors="replace"), language=None)
            if len(raw) > 20000:
                ui.caption("Preview limited to 20 KB. Download contains the complete artifact.")
        ui.download_button(
            "Download artifact", raw, file_name=Path(selected).name, icon=":material/download:"
        )
    except (OSError, ValueError, KeyError):
        ui.error("This artifact could not be safely read. The run needs review.")


def render_environment(journal: Journal) -> None:
    ui.subheader("Pinned environment")
    ui.caption("Inputs, limits and implementation identity are recorded before the first decision.")
    left, right = ui.columns(2)
    with left:
        ui.markdown("**Run contract**")
        ui.json(journal.config)
    with right:
        ui.markdown("**Implementation identity**")
        ui.json(journal.environment)
        ui.caption(f"Viewer policy: {POLICY_VERSION}")
        ui.markdown(
            "[Jev decision pattern · official documentation](https://docs.typesafe.ai/introduction)"
        )
        ui.write(
            "This interface uses state, closed choices, evidence and code-controlled gates. "
            "Omnigent runs parallel researchers and a decision agent. The optional AnyJev "
            "backend records local option weights; these are not calibrated confidence."
        )
    ui.markdown("**Registered source evidence**")
    for source in journal.sources:
        with ui.container(border=True):
            ui.text(source.get("title", source["source_id"]))
            ui.caption(f"{source['source_id']} · {source['kind']} · SHA-256 {source['sha256']}")
            url = source.get("url", "")
            if urlsplit(url).scheme in {"http", "https"}:
                ui.link_button("Open source", url)
            if source["kind"] == "curated_excerpt":
                ui.warning(
                    "Curated excerpt only. Page numbers refer to the excerpt, not the PDF. "
                    "This run does not demonstrate automated full-paper extraction."
                )


def selected_journal(context="Research", *, compact=False, show_outcome=True) -> Journal | None:
    if ui.session_state.get("research_future") is not None and not ui.session_state.get(
        "following_live_run"
    ):
        ui.info("Run starting · checking the runtime and preparing source artifacts.")
        ui.caption("This page updates automatically as the new run produces evidence.")
        return None
    active = ui.session_state.get("research_active_run")
    if (
        ui.session_state.get("research_launch_error")
        and active
        and not (run_root() / active / "report.json").is_file()
    ):
        ui.error("Run could not start · see the runtime error in the sidebar. No experiment ran.")
        return None
    selected = ui.session_state.get("run_selection")
    if not selected:
        ui.info("No runs have been recorded. Open Source intake to choose a seed and start a run.")
        return None
    journal = load_journal(run_root() / selected)
    if journal.issues:
        ui.error("Evidence verification failed. This run is quarantined from the decision views.")
        for issue in journal.issues:
            ui.write(issue)
        ui.download_button(
            "Download diagnostic ledger",
            journal.export(),
            file_name="decision-ledger-diagnostic.json",
            mime="application/json",
        )
        return None
    backend = journal.report.get("backend", "unknown")
    if not compact:
        ui.caption(
            f"{journal.run_id} · {backend.upper()} · "
            f"{journal.report.get('status', 'running').replace('_', ' ')} · "
            f"{'Artifacts verified' if journal.verified else 'Unsealed live snapshot'}"
        )
    if backend != "omnigent":
        ui.info("Auxiliary run: no live Omnigent collaboration is claimed for this backend.")
    from hacknation_databricks.policy_ui import render_policy_context
    from hacknation_databricks.run_feedback_ui import render_run_outcome

    seed = next((s for s in journal.sources if s.get("source_id") == "seed"), {})
    if seed and not compact:
        ui.text(f"Run paper: {seed.get('title', 'Seed paper')}")
    if show_outcome:
        render_run_outcome(journal)
    if not compact:
        render_policy_context(journal, context)
    return journal


@ui.fragment(run_every=5)
def render_selected_run():
    journal = selected_journal(compact=True, show_outcome=False)
    if journal is None:
        return
    from hacknation_databricks.synthesis_ui import render_synthesis

    render_synthesis(journal)


def main() -> None:
    ui.title("Discovery overview")
    ui.write(
        "When a recorded scene is available, watch how the proposed experiment's pattern or "
        "trajectory differs from the original control. Read the agents' visualization choice, "
        "the measured result, and why they continued or stopped. The scene shows the first "
        "planned sample per arm; the result summarizes the full test. Flat or missing scenes "
        "are reported without adding artificial motion."
    )
    render_selected_run()


if __name__ == "__main__":
    # Supports direct developer previews as well as the multipage entrypoint.
    ui.set_page_config(page_title="OmniLab", layout="wide")
    render_sidebar()
    main()
