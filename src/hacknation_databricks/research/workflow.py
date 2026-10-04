"""Strict research stage ordering and deterministic evidence gates."""

import csv
import hashlib
import json
import re
import shutil
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from statistics import NormalDist

from . import WORKFLOW_VERSION
from .agents import AgentBudgetExceeded, AgentUnavailable, OmnigentRoles
from .artifacts import RunStore, canonical, code_digest, environment
from .code_archive import archive_framework, archive_implementation
from .comparison import save_comparisons
from .decision_roles import AnyJevRoles, DecisionAbstained
from .models import (
    CritiqueBatch,
    DiscoveryPlan,
    ExperimentPlan,
    LiteratureReview,
    NextDecision,
    NoveltyReview,
    ProposalBatch,
    RunConfig,
    ValidationReview,
)
from .simulation import (
    BENCHMARKS,
    WRAPPING_TARGET,
    lattice,
    measure,
    simulate,
    summarize,
    wilson,
)
from .sources import Source, check_evidence

RECIPES = {
    "random_manhattan": {
        "model": "random_manhattan",
        "mode": "bond",
        "control": "manhattan",
        "p": 0.697160,
        "question": "Test whether randomizing row and column directions changes one-axis wrapping.",
    },
    "site_percolation": {
        "model": "manhattan",
        "mode": "site",
        "control": "manhattan",
        "p": 0.697160,
        "question": "Test whether occupying sites instead of bonds changes wrapping at fixed p.",
    },
    "resistor_diode": {
        "model": "resistor_diode",
        "mode": "bond",
        "control": "random_diode",
        "p": 1.0,
        "question": "Test whether making 25% of occupied diodes bidirectional changes wrapping.",
    },
}


class RunBudgetExceeded(RuntimeError):
    pass


class Budget:
    def __init__(self, config: RunConfig):
        self.config = config
        self.started = time.monotonic()
        self.simulations = 0
        self.lock = threading.Lock()

    def check(self) -> None:
        if time.monotonic() - self.started >= self.config.max_seconds:
            raise RunBudgetExceeded("Wall-clock budget exhausted")

    def consume(self) -> None:
        with self.lock:
            self.check()
            if self.simulations >= self.config.max_simulations:
                raise RunBudgetExceeded("Simulation budget exhausted")
            self.simulations += 1


def baseline_validation(summaries: list[dict], tolerance: float) -> dict:
    checks = []
    for item in summaries:
        lo, hi = item["wrap_x_ci95"]
        checks.append(
            {
                "model": item["model"],
                "size": item["size"],
                "observed": item["wrap_x"],
                "ci95": [lo, hi],
                "reference": WRAPPING_TARGET,
                "passed": lo - tolerance <= WRAPPING_TARGET <= hi + tolerance,
            }
        )
    return {
        "passed": bool(checks) and all(c["passed"] for c in checks),
        "checks": checks,
        "claim": "Small-lattice simulation consistency check, not high-precision reproduction.",
        "reference": "arXiv:2607.24975v1, Tables I-II; one-axis wrapping",
        "finite_size_tolerance": tolerance,
        "limitation": "Tolerance is an engineering allowance, not a fitted scaling correction.",
    }


def numerical_checks(rows: list[dict], budget: Budget) -> dict:
    violations = []
    for row in rows:
        n = row["size"] ** 2
        if not (0 <= row["largest"] <= row["occupied_sites"] <= n):
            violations.append("Invalid occupied/cluster size")
        if not 0 <= row["largest_fraction"] <= 1:
            violations.append("Invalid cluster fraction")
        if row["wrap_both"] != (row["wrap_x"] and row["wrap_y"]):
            violations.append("Inconsistent wrapping flags")
    # One independent replay per job, recomputing from raw seed and parameters.
    replayed = set()
    for row in rows:
        key = (row["model"], row["mode"], row["size"], row["p"])
        if key in replayed:
            continue
        replayed.add(key)
        budget.consume()
        replay = measure(lattice(row["size"], row["model"], row["p"], row["seed"], row["mode"]))
        if any(row[k] != value for k, value in replay.items()):
            violations.append("Seed replay mismatch")
    return {"passed": not violations, "violations": violations, "seed_replays": len(replayed)}


def effect_validation(control: list[dict], treatment: list[dict], config: RunConfig) -> dict:
    # Simultaneous, conservative intervals: two endpoints per comparison, across
    # all sizes and all predeclared rounds. No naive optional-stopping p-values.
    z = NormalDist().inv_cdf(1 - 0.05 / (4 * len(config.sizes) * config.max_rounds))
    checks = []
    for size in config.sizes:
        a = [row for row in control if row["size"] == size]
        b = [row for row in treatment if row["size"] == size]
        if not a or not b:
            raise ValueError("Missing control or treatment for a configured lattice size")
        ca, cb = sum(row["wrap_x"] for row in a), sum(row["wrap_x"] for row in b)
        a_ci, b_ci = wilson(ca, len(a), z), wilson(cb, len(b), z)
        lower = max(0.0, b_ci[0] - a_ci[1], a_ci[0] - b_ci[1])
        checks.append(
            {
                "size": size,
                "control": ca / len(a),
                "treatment": cb / len(b),
                "difference": cb / len(b) - ca / len(a),
                "control_interval": a_ci,
                "treatment_interval": b_ci,
                "absolute_effect_lower_bound": lower,
                "passed": lower >= config.minimum_effect,
            }
        )
    return {
        "passed": all(c["passed"] for c in checks),
        "checks": checks,
        "minimum_effect": config.minimum_effect,
        "interval_method": "Wilson with Bonferroni correction across sizes and planned rounds",
        "interpretation": "Finite-size difference in one-axis wrapping; not proof of universality.",
    }


def novelty_gate(
    baseline: dict,
    numerical: dict,
    effect: dict,
    literature: LiteratureReview,
    review: ValidationReview,
    backend: str,
    evaluation: NoveltyReview | None = None,
) -> dict:
    criteria = {
        "baseline_consistent": baseline["passed"],
        "numerical_validation": numerical["passed"],
        "detectable_effect": effect["passed"],
        "independent_review_supports": review.decision == "supported"
        and backend in {"anyjev", "omnigent"},
        "literature_candidate_gap": literature.assessment == "candidate_gap",
        "multiple_sources_reviewed": len({e.source_id for e in literature.sources}) >= 2,
    }
    if evaluation is not None:
        criteria["reference_evaluator_supports"] = evaluation.verdict == "candidate_contribution"
    return {
        "met": all(criteria.values()),
        "criteria": criteria,
        "meaning": "Automated evidence gate within reviewed literature; no global discovery claim.",
        "scientific_novelty": "unverified",
    }


def discovery_transition(decision, gate, validation, review, remaining_rounds):
    """A specialist recommendation cannot bypass scientific or resource gates."""
    if gate["met"]:
        action, status, reason = "stop", "automated_candidate", "The bounded evidence gate is met."
    elif validation.decision == "reject":
        action, status, reason = (
            "stop",
            "validation_rejected",
            "Independent validation rejected the result.",
        )
    elif decision.action == "stop":
        action, status, reason = "stop", "research_stopped", decision.rationale
    elif (
        decision.action == "literature"
        or review.assessment != "candidate_gap"
        or len({e.source_id for e in review.sources}) < 2
    ):
        action, status, reason = (
            "literature",
            "needs_literature_review",
            ("More simulations cannot repair missing independent prior-art evidence."),
        )
    elif remaining_rounds <= 0:
        action, status, reason = "stop", "round_budget_exhausted", "No experimental rounds remain."
    else:
        action, status, reason = "repeat", "running", decision.rationale
    return {
        "requested_action": decision.action,
        "applied_action": action,
        "status": status,
        "reason": reason,
    }


def _jobs(
    jobs: list[tuple],
    config: RunConfig,
    budget: Budget,
    cache: Path | None,
) -> tuple[list[dict], int]:
    digest = code_digest()

    def one(job: tuple) -> tuple[list[dict], bool]:
        budget.check()
        key = hashlib.sha256(canonical([digest, job]).encode()).hexdigest()
        path = cache / f"{key}.json" if cache else None
        if path and path.exists():
            stored = json.loads(path.read_text())
            rows = stored["rows"]
            if hashlib.sha256(canonical(rows).encode()).hexdigest() != stored["sha256"]:
                raise ValueError("Simulation cache checksum mismatch")
            return rows, True
        rows = simulate(*job, check_budget=budget.consume)
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(".tmp")
            temporary.write_text(
                canonical(
                    {
                        "sha256": hashlib.sha256(canonical(rows).encode()).hexdigest(),
                        "rows": rows,
                    }
                )
            )
            temporary.replace(path)
        return rows, False

    with ThreadPoolExecutor(max_workers=config.max_workers) as executor:
        results = list(executor.map(one, jobs))
    return [row for rows, _ in results for row in rows], sum(hit for _, hit in results)


def _save_trials(store: RunStore, name: str, rows: list[dict]) -> None:
    path = store.directory / name
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=sorted(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    store.event("artifact_written", {"path": name})


def run_research(
    source: Source,
    output: Path,
    config: RunConfig | None = None,
    backend: str = "omnigent",
    literature: list[Source] | None = None,
    cache: Path | None = None,
    progress: Callable[[str], None] | None = None,
    roles_factory: Callable | None = None,
    retrieval_report: dict | None = None,
) -> dict:
    """Execute reader -> critic -> baseline -> literature/plan/experiment/review loop.

    The injection point is for deterministic integration tests, never an input
    from paper text. Live mode fails explicitly; it never falls back to scripted.
    """
    config = config or RunConfig(workflow="adaptive")
    if config.workflow == "repository":
        from .repository_workflow import run_repository

        return run_repository(
            source,
            output,
            config,
            backend=backend,
            literature=literature,
            progress=progress,
            roles_factory=roles_factory,
            retrieval_report=retrieval_report,
        )
    if config.workflow == "adaptive":
        from .adaptive import run_adaptive

        return run_adaptive(
            source,
            output,
            config,
            backend=backend,
            literature=literature,
            cache=cache,
            progress=progress,
            roles_factory=roles_factory,
            retrieval_report=retrieval_report,
        )
    if config.domain == "auto":
        raise ValueError("Paper-derived context requires the adaptive Omnigent workflow")
    if backend not in {"anyjev", "omnigent"} and not (backend == "fixture" and roles_factory):
        raise ValueError("Backend must be anyjev or omnigent")
    sources = [source, *(literature or [])]
    if backend == "anyjev" and len(sources) > 4:
        raise ValueError("AnyJev permits one seed and at most three related sources per run")
    if source.source_id != "seed" or len({s.source_id for s in sources}) != len(sources):
        raise ValueError("Seed must have ID 'seed'; source IDs must be unique")
    if any(not re.fullmatch(r"[a-zA-Z0-9_-]{1,60}", s.source_id) for s in sources):
        raise ValueError("Source IDs must be simple identifiers")
    if len({s.sha256 for s in sources}) != len(sources):
        raise ValueError("Duplicate source content cannot count as additional literature")
    if sum(sum(map(len, s.pages)) for s in sources) > 180_000:
        raise ValueError("Combined sources exceed the bounded agent context; nothing was truncated")
    store = RunStore(output)
    budget = Budget(config)
    report = {
        "workflow_version": WORKFLOW_VERSION,
        "backend": backend,
        "status": "running",
        "source_kind": source.kind,
        "scientific_novelty": "unverified",
        "rounds": [],
        "acceptance": {
            "baseline_simulations": False,
            "followup_implemented": False,
            "live_agents_executed": False,
            "full_paper_reproduction": False,
        },
    }

    def announce(message: str) -> None:
        budget.check()
        if progress:
            progress(message)

    def save_report() -> None:
        report["elapsed_seconds"] = round(time.monotonic() - budget.started, 3)
        report["computed_simulations"] = budget.simulations
        report["acceleration"] = {
            "bottleneck": "Source-backed hypothesis to validated computational result",
            "elapsed_seconds": report["elapsed_seconds"],
            "baseline_seconds": None,
            "multiplier": None,
            "status": "No comparable manual baseline measured",
        }
        store.write("report.json", report)

    roles = None
    try:
        store.write("config.json", config.model_dump())
        store.write("environment.json", environment())
        store.write("sources.json", [s.payload() for s in sources])
        if retrieval_report is not None:
            store.write("reference_retrieval.json", retrieval_report)
        for item in sources:
            destination = output / "inputs" / f"{item.source_id}{Path(item.path).suffix}"
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(item.path, destination)
            provenance = Path(item.path).with_suffix(Path(item.path).suffix + ".json")
            if provenance.is_file():
                shutil.copyfile(provenance, destination.with_suffix(destination.suffix + ".json"))
        archive_framework(output)
        archive_implementation(store, source, config.domain, sequential=True)
        lockfile = Path("uv.lock").resolve()
        if not lockfile.is_file():
            lockfile = Path(__file__).resolve().parents[3] / "uv.lock"
        if lockfile.exists():
            shutil.copyfile(lockfile, output / "uv.lock")
        save_report()
        factory = roles_factory or (OmnigentRoles if backend == "omnigent" else AnyJevRoles)
        roles = factory(sources, store, config)
        roles.deadline = budget.started + config.max_seconds
        announce("Read the seed and extract up to three source-backed directions")
        with store.stage("reader"):
            proposals = roles.ask(
                "reader",
                {
                    "source": source.payload(),
                    "experiment_catalog": RECIPES,
                    "scope": "Hypotheses must use these fixed-p, finite-size wrapping experiments.",
                },
                ProposalBatch,
            )
            for proposal in proposals.proposals:
                check_evidence(proposal.evidence, [source])
            store.write("proposals.json", proposals.model_dump())
        announce("Critique every direction before any experiments")
        with store.stage("critic"):
            critiques = roles.ask(
                "critic",
                {**proposals.model_dump(), "preferred_experiment": config.preferred_experiment},
                CritiqueBatch,
            )
            expected = {p.id for p in proposals.proposals}
            actual = [c.proposal_id for c in critiques.critiques]
            if set(actual) != expected or len(actual) != len(expected):
                raise ValueError("Critic must review each proposal exactly once")
            store.write("critiques.json", critiques.model_dump())
            accepted = {c.proposal_id for c in critiques.critiques if c.decision == "accept"}
            if backend in {"anyjev", "omnigent"}:
                selected_id = critiques.selected_proposal_id
                if selected_id is not None and selected_id not in accepted:
                    raise ValueError("Model selected an unaccepted proposal")
                selected = next((p for p in proposals.proposals if p.id == selected_id), None)
                if (
                    selected
                    and config.preferred_experiment
                    and (selected.experiment != config.preferred_experiment)
                ):
                    raise ValueError("Model selected outside the requested experiment boundary")
            else:
                selected = next(
                    (
                        p
                        for p in proposals.proposals
                        if p.id in accepted
                        and (
                            config.preferred_experiment is None
                            or p.experiment == config.preferred_experiment
                        )
                    ),
                    None,
                )
            if selected is None:
                report["status"] = "needs_decision_review" if accepted else "all_proposals_rejected"
                return report
        announce("Run and validate seeded baseline simulations")
        with store.stage("baseline"):
            jobs = [
                (model, "bond", size, p, config.trials, config.seed)
                for model, p in BENCHMARKS.items()
                for size in config.sizes
            ]
            baseline_rows, hits = _jobs(jobs, config, budget, cache)
            _save_trials(store, "baseline/trials.csv", baseline_rows)
            summary = summarize(baseline_rows)
            baseline = baseline_validation(summary, config.finite_size_tolerance)
            baseline["numerical"] = numerical_checks(baseline_rows, budget)
            baseline["passed"] &= baseline["numerical"]["passed"]
            store.write("baseline/summary.json", summary)
            store.write("baseline/validation.json", baseline)
            report["baseline"] = baseline
            report["cache_hits"] = hits
            report["acceptance"]["baseline_simulations"] = baseline["passed"]
            save_report()
        if not baseline["passed"]:
            report["status"] = "baseline_failed"
            return report
        report["selected_proposal"] = selected.model_dump()
        save_report()
        for round_index in range(1, config.max_rounds + 1):
            prefix = f"rounds/{round_index:02d}"
            announce(f"Round {round_index}: read literature and plan a bounded experiment")
            with store.stage(f"{prefix}/literature"):
                review = roles.ask(
                    "literature",
                    {
                        "proposal": selected.model_dump(),
                        "sources": [s.payload() for s in sources],
                        "previous_rounds": report["rounds"],
                    },
                    LiteratureReview,
                )
                for evidence in review.sources:
                    check_evidence(evidence, sources)
                store.write(f"{prefix}/literature.json", review.model_dump())
            trials = min(config.trials * 2 ** (round_index - 1), 4096)
            test_options = {
                "screen": {"trials_per_size": trials, "purpose": "Screen for a finite-size effect"},
                "precision": {
                    "trials_per_size": min(trials * 2, 8192),
                    "purpose": "Reduce sampling uncertainty at the same fixed p",
                },
            }
            for option in test_options.values():
                option["simulation_cost"] = (option["trials_per_size"] + 1) * len(config.sizes)
                option["within_simulation_budget"] = (
                    option["simulation_cost"] <= config.max_simulations - budget.simulations
                )
            with store.stage(f"{prefix}/planner"):
                plan = roles.ask(
                    "planner",
                    {
                        "proposal": selected.model_dump(),
                        "literature": review.model_dump(),
                        "recipe": RECIPES[selected.experiment],
                        "test_options": test_options,
                        "previous_rounds": report["rounds"],
                        "remaining_seconds": max(
                            0, config.max_seconds - (time.monotonic() - budget.started)
                        ),
                    },
                    DiscoveryPlan if backend == "omnigent" else ExperimentPlan,
                )
                if plan.proposal_id != selected.id or plan.experiment != selected.experiment:
                    raise ValueError("Planner changed the reviewed proposal")
                if isinstance(plan, DiscoveryPlan):
                    chosen_test = test_options[plan.selected_test_id]
                    if not chosen_test["within_simulation_budget"]:
                        raise RunBudgetExceeded("Selected test exceeds remaining simulation budget")
                    trials = chosen_test["trials_per_size"]
                    store.write(f"{prefix}/test_options.json", test_options)
                store.write(f"{prefix}/plan.json", plan.model_dump())
            recipe = RECIPES[plan.experiment]
            model, mode, control_model, p = (
                recipe["model"],
                recipe["mode"],
                recipe["control"],
                recipe["p"],
            )
            store.write(f"{prefix}/experiment.json", recipe)
            announce(f"Round {round_index}: simulate {plan.experiment} and independently validate")
            with store.stage(f"{prefix}/experiment"):
                jobs = [
                    (model, mode, size, p, trials, config.seed + round_index)
                    for size in config.sizes
                ]
                rows, hits = _jobs(jobs, config, budget, cache)
                report["cache_hits"] += hits
                _save_trials(store, f"{prefix}/trials.csv", rows)
                store.write(f"{prefix}/summary.json", summarize(rows))
                numerical = numerical_checks(rows, budget)
                control = [r for r in baseline_rows if r["model"] == control_model]
                effect = effect_validation(control, rows, config)
                checks = {"passed": numerical["passed"], "numerical": numerical, "effect": effect}
                store.write(f"{prefix}/checks.json", checks)
                report["acceptance"]["followup_implemented"] = True
                save_report()
            with store.stage(f"{prefix}/validation"):
                evaluation = None
                validation = roles.ask(
                    "validator",
                    {
                        "proposal": selected.model_dump(),
                        "plan": plan.model_dump(),
                        "baseline": baseline,
                        "summary": summarize(rows),
                        "checks": checks,
                        "literature": review.model_dump(),
                        "source_evidence": [s.payload() for s in sources],
                    },
                    ValidationReview,
                )
                store.write(f"{prefix}/validation.json", validation.model_dump())
                if backend == "omnigent":
                    evaluation = roles.ask(
                        "novelty_evaluator",
                        {
                            "proposal": selected.model_dump(),
                            "recipe": recipe,
                            "sources": [s.payload() for s in sources],
                            "retrieval": retrieval_report,
                            "baseline": baseline,
                            "effect": effect,
                            "numerical": numerical,
                            "validation": validation.model_dump(),
                            "literature": review.model_dump(),
                        },
                        NoveltyReview,
                    )
                    known = {s.source_id for s in sources}
                    if set(evaluation.reviewed_source_ids) != known:
                        raise ValueError(
                            "Evaluator must review every supplied source, without invented IDs"
                        )
                    for comparison in evaluation.comparisons:
                        for evidence in comparison.evidence:
                            check_evidence(evidence, sources)
                    cited = {e.source_id for c in evaluation.comparisons for e in c.evidence}
                    if not known.issubset(cited):
                        raise ValueError(
                            "Evaluator must ground its assessment in every reviewed source"
                        )
                    store.write(f"{prefix}/novelty_review.json", evaluation.model_dump())
                    report["automated_review"] = evaluation.model_dump()
                gate = novelty_gate(
                    baseline, numerical, effect, review, validation, backend, evaluation
                )
                store.write(f"{prefix}/gate.json", gate)
                report["rounds"].append(
                    {
                        "round": round_index,
                        "trials_per_size": trials,
                        "effect": effect,
                        "gate": gate,
                    }
                )
                report["acceptance"]["live_agents_executed"] = (
                    isinstance(roles, OmnigentRoles) and roles.calls > 0
                )
                save_report()
                if backend == "omnigent":
                    decision = roles.ask(
                        "next_decision",
                        {
                            "hypothesis": selected.hypothesis,
                            "plan": plan.model_dump(),
                            "effect": effect,
                            "validation": validation.model_dump(),
                            "literature": review.model_dump(),
                            "gate": gate,
                            "reference_review": evaluation.model_dump() if evaluation else None,
                            "remaining_rounds": config.max_rounds - round_index,
                            "remaining_simulations": config.max_simulations - budget.simulations,
                            "previous_rounds": report["rounds"],
                            "repeat_preconditions": "Repeat the same allowlisted treatment only; "
                            "baseline controls remain fixed. Requires a literature candidate gap, "
                            "two independently cited sources and remaining rounds. Other proposed "
                            "experiments are future recommendations, not executable plans.",
                        },
                        NextDecision,
                    )
                    store.write(f"{prefix}/next_decision.json", decision.model_dump())
                    report["rounds"][-1]["next_decision"] = decision.model_dump()
                    report["next_decision"] = decision.model_dump()
                    save_report()
            if backend == "omnigent":
                transition = discovery_transition(
                    decision, gate, validation, review, config.max_rounds - round_index
                )
                store.write(f"{prefix}/transition.json", transition)
                report["rounds"][-1]["transition"] = transition
                report["status"] = transition["status"]
                save_report()
                if transition["applied_action"] != "repeat":
                    break
                continue
            if gate["met"]:
                report["status"] = "automated_candidate"
                break
            if validation.decision == "reject":
                report["status"] = "validation_rejected"
                break
            # More simulations cannot repair absent literature/model evidence.
            if (
                review.assessment != "candidate_gap"
                or backend == "fixture"
                or len({e.source_id for e in review.sources}) < 2
            ):
                report["status"] = (
                    "review_complete"
                    if evaluation is not None and len(sources) > 1
                    else "needs_literature_review"
                )
                break
        else:
            report["status"] = "round_budget_exhausted"
        report["role_calls"] = roles.calls
    except (RunBudgetExceeded, AgentBudgetExceeded, TimeoutError) as exc:
        report["status"] = "budget_exhausted"
        report["reason"] = type(exc).__name__
    except DecisionAbstained as exc:
        report["status"] = "needs_decision_review"
        report["reason"] = str(exc)
    except AgentUnavailable as exc:
        report["status"] = "blocked_live_backend"
        report["reason"] = str(exc)
    except Exception as exc:
        report["status"] = "failed"
        report["reason"] = type(exc).__name__
        raise
    finally:
        if roles is not None:
            report["role_calls"] = roles.calls
            report["decision_calls"] = getattr(roles, "decision_calls", 0)
            if backend == "anyjev":
                report["decision_usage"] = {
                    "prefills": getattr(roles, "prefills", 0),
                    "input_tokens": getattr(roles, "input_tokens", 0),
                    "generated_tokens": 0,
                }
                report["acceptance"]["live_agents_executed"] = (
                    report["decision_usage"]["prefills"] > 0
                )
            if hasattr(roles, "close"):
                roles.close()
        save_comparisons(store, report, config.model_dump(), [s.payload() for s in sources])
        save_report()
        store.event("run_finished", {"status": report["status"]})
        store.seal()
    return report
