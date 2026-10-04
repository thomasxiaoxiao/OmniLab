"""Parallel Omnigent research branches with decisions on every partial batch."""

import hashlib
import json
import queue
import re
import shutil
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path

from hacknation_databricks.research.agents import (
    AgentBudgetExceeded,
    AgentUnavailable,
    OmnigentRoles,
)
from hacknation_databricks.research.artifacts import RunStore, environment
from hacknation_databricks.research.decision_roles import DecisionAbstained
from hacknation_databricks.research.hybrid_roles import (
    NUMERICAL_DECISION_POLICY,
    HybridOmnigentRoles,
)
from hacknation_databricks.research.models import (
    BranchPlan,
    InvestmentDecision,
    PaperBrief,
    PortfolioSelection,
    ResearchBrief,
    ResearchContext,
    ValidationReview,
)
from hacknation_databricks.research.sources import check_evidence

from .adaptive_experiments import (
    ASTROSAT_RECIPES,
    MEASUREMENT_CONTRACTS,
    astrosat_baseline,
    audit_statistics,
    batch_cost,
    execute_batch,
    seed_for,
    summarize_branch,
)
from .code_archive import archive_framework, archive_implementation
from .comparison import save_comparisons
from .simulation import BENCHMARKS, summarize
from .workflow import (
    RECIPES,
    Budget,
    RunBudgetExceeded,
    _jobs,
    _save_trials,
    baseline_validation,
    numerical_checks,
)

# The replacement brief did not restart the project clock.
PROJECT_DEADLINE = datetime(2026, 10, 4, 7, 7, tzinfo=UTC).timestamp()


def run_adaptive(
    source,
    output,
    config,
    *,
    backend="omnigent",
    literature=None,
    cache=None,
    progress=None,
    roles_factory=None,
    retrieval_report=None,
):
    if backend != "omnigent" and not (backend == "fixture" and roles_factory):
        raise ValueError("Backend must be Omnigent for adaptive research; there is no fallback")
    sources = [source, *(literature or [])]
    if (
        source.source_id != "seed"
        or len(sources) > 8
        or len({s.source_id for s in sources}) != len(sources)
        or len({s.sha256 for s in sources}) != len(sources)
        or any(not re.fullmatch(r"[a-zA-Z0-9_-]{1,60}", s.source_id) for s in sources)
        or sum(sum(map(len, s.pages)) for s in sources) > 180_000
    ):
        raise ValueError("Invalid, duplicate or over-budget sources; nothing was truncated")
    store, budget = RunStore(output), Budget(config)
    cancelled = threading.Event()
    original_check = budget.check
    # Offline fixtures must remain reproducible after the event has ended.
    project_deadline = PROJECT_DEADLINE if backend != "fixture" else float("inf")

    def check():
        original_check()
        if cancelled.is_set() or time.time() >= project_deadline:
            raise RunBudgetExceeded("Run cancelled or project hard stop reached")

    budget.check = check
    catalog = {}
    context = None
    context_parents = []
    paper_briefs = {}
    report = {
        "workflow_version": "4",
        "workflow": "adaptive",
        "domain": config.domain,
        "backend": backend,
        "source_kind": source.kind,
        "status": "running",
        "scientific_novelty": "unverified",
        "rounds": [],
        "branches": {},
        "checkpoints": [],
        "goal": {
            "description": "Resolve a source-grounded mechanism with fresh controls, "
            "independent seed batches and a simultaneous interval narrow enough to decide.",
            "minimum_batches": config.goal_min_batches,
            "maximum_interval_width": config.goal_max_interval_width,
            "minimum_effect": config.minimum_effect,
            "independent_validation_required": True,
            "achieved": False,
        },
        "acceptance": {
            "baseline_simulations": False,
            "followup_implemented": False,
            "live_agents_executed": False,
            "full_paper_reproduction": False,
        },
        "control_policy": {
            "max_invested_directions": 3,
            "max_parallel_agent_calls": config.max_workers,
            "evaluation_frequency": "Every completed simulation batch",
            "in_flight_policy": "Finish already authorized batches; retain late results",
            "seed_policy": "Recorded master seed; independent branch/batch/arm streams",
            "tool_policy": "Omnigent structured plans dispatch allowlisted Python tools",
        },
    }
    roles = None
    all_rows, counts, latest_stages = {}, {}, {}
    validation_versions = set()
    reserved = 0

    def save():
        report["elapsed_seconds"] = round(time.monotonic() - budget.started, 3)
        report["computed_simulations"] = budget.simulations
        report["role_calls"] = roles.calls if roles else 0
        report["decision_calls"] = getattr(roles, "decision_calls", 0)
        if isinstance(roles, HybridOmnigentRoles):
            report["decision_usage"] = {
                "prefills": roles.scorer.prefills,
                "input_tokens": roles.scorer.input_tokens,
                "generated_tokens": 0,
            }
        report["acceleration"] = {
            "bottleneck": "Partial simulation result to next investment decision",
            "observed_decision_seconds": [c["decision_seconds"] for c in report["checkpoints"]],
            "observed_result_to_decision_seconds": [
                c["result_to_decision_seconds"] for c in report["checkpoints"]
            ],
            "baseline_seconds": None,
            "multiplier": None,
            "status": "No comparable manual baseline measured",
        }
        store.write("report.json", report)

    def announce(message):
        budget.check()
        if progress:
            progress(message)

    def ask(stage, role, payload, contract, parents):
        if role != "paper_reader" and config.domain in MEASUREMENT_CONTRACTS:
            payload["measurement_contract"] = MEASUREMENT_CONTRACTS[config.domain]
        with store.stage(stage, parents=parents):
            result = roles.ask(role, payload, contract)
            store.write(f"{stage}.json", result.model_dump())
            return result

    def research(item):
        stage = f"sources/{item.source_id}/researcher"
        paper_brief = paper_briefs.get(item.source_id)
        role = "implementation_mapper" if paper_brief else "researcher"
        payload = {
            "source": item.payload(),
            "experiment_catalog": catalog,
            "seed_question": context.research_question if context else source.title,
            "research_context": context.model_dump() if context else None,
            "domain": config.domain,
            "retrieval_scope": retrieval_report,
        }
        if paper_brief:
            payload["paper_first_directions"] = paper_brief.model_dump()
        brief = ask(
            stage,
            role,
            payload,
            ResearchBrief,
            context_parents,
        )

        def validate_brief(candidate):
            originals = (
                {d.id: d.model_dump() for d in paper_brief.directions} if paper_brief else {}
            )
            for direction in candidate.directions:
                if direction.experiment not in catalog:
                    raise ValueError("Researcher selected outside the domain catalog")
                if paper_brief and direction.model_dump(exclude={"experiment"}) != originals.get(
                    direction.id
                ):
                    raise ValueError("Implementation fit changed a paper-first direction")
                for evidence in direction.evidence:
                    check_evidence(evidence, [item])

        try:
            validate_brief(brief)
        except ValueError:
            store.write(
                f"sources/{item.source_id}/evidence_failure.json",
                {
                    "rejected_brief": brief.model_dump(),
                    "reason": "Invalid catalog choice or exact page-local evidence",
                    "repair_limit": 1,
                },
            )
            previous_stage = stage
            stage = f"sources/{item.source_id}/repair_researcher"
            brief = ask(
                stage,
                role,
                {
                    **payload,
                    "rejected_brief": brief.model_dump(),
                    "repair": "One correction attempt. Every quote must be an exact contiguous "
                    "substring on its stated 1-based source page. Use short complete passages. "
                    "Do not join lines across pages or paraphrase. Remove unsupported directions.",
                },
                ResearchBrief,
                [previous_stage],
            )
            validate_brief(brief)
        return stage, brief

    try:
        store.write("requested_config.json", config.model_dump())
        store.write("config.json", config.model_dump())
        store.write("environment.json", environment())
        store.write("sources.json", [s.payload() for s in sources])
        store.write("goal.json", report["goal"])
        if retrieval_report is not None:
            store.write("reference_retrieval.json", retrieval_report)
        for item in sources:
            destination = output / "inputs" / f"{item.source_id}{Path(item.path).suffix}"
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(item.path, destination)
            sidecar = Path(item.path).with_suffix(Path(item.path).suffix + ".json")
            if sidecar.exists():
                shutil.copyfile(sidecar, destination.with_suffix(destination.suffix + ".json"))
        archive_framework(output)
        lockfile = Path(__file__).resolve().parents[3] / "uv.lock"
        if lockfile.exists():
            shutil.copyfile(lockfile, output / "uv.lock")
        save()
        budget.check()
        factory = HybridOmnigentRoles if config.decision_backend == "anyjev" else OmnigentRoles
        roles = (roles_factory or factory)(sources, store, config)
        store.write(
            "agent-configuration.json",
            {
                "researcher": "Codex + Omnigent" if backend == "omnigent" else backend,
                "decision": "AnyJev + Omnigent"
                if isinstance(roles, HybridOmnigentRoles)
                else "Omnigent"
                if backend == "omnigent"
                else backend,
                "decision_integration": "Local bounded scoring tool after Omnigent assessment"
                if isinstance(roles, HybridOmnigentRoles)
                else "Session response",
            },
        )
        roles.deadline = min(
            budget.started + config.max_seconds, time.monotonic() + project_deadline - time.time()
        )
        if config.domain == "auto":
            # Establish scientific intent before any specialist sees preset tools.
            def read_paper(item):
                brief = ask(
                    f"sources/{item.source_id}/paper_reader",
                    "paper_reader",
                    {
                        "source": item.payload(),
                        "seed_question": paper_briefs["seed"].research_question
                        if item.source_id != "seed"
                        else None,
                        "retrieval_scope": retrieval_report,
                    },
                    PaperBrief,
                    ["sources/seed/paper_reader"] if item.source_id != "seed" else [],
                )
                for direction in brief.directions:
                    for evidence in direction.evidence:
                        check_evidence(evidence, [item])
                return brief

            paper_briefs["seed"] = read_paper(source)
            with ThreadPoolExecutor(max_workers=config.max_workers) as pool:
                futures = {pool.submit(read_paper, item): item for item in sources[1:]}
                for future in as_completed(futures):
                    item = futures[future]
                    paper_briefs[item.source_id] = future.result()
            store.write("paper_briefs.json", {k: v.model_dump() for k, v in paper_briefs.items()})
            context = ask(
                "sources/seed/context",
                "research_context",
                {"source": source.payload(), "paper_brief": paper_briefs["seed"].model_dump()},
                ResearchContext,
                [f"sources/{item.source_id}/paper_reader" for item in sources],
            )
            for evidence in context.evidence:
                check_evidence(evidence, [source])
            store.write("research_context.json", context.model_dump())
            context_parents = ["sources/seed/context"]
            if context.domain == "unsupported":
                report["status"] = "unsupported_source"
                report["reason"] = context.rationale
                return report
            config = config.model_copy(update={"domain": context.domain})
            report["domain"] = config.domain
            store.write("config.json", config.model_dump())
        catalog = RECIPES if config.domain == "percolation" else ASTROSAT_RECIPES
        if config.preferred_experiment:
            catalog = {k: v for k, v in catalog.items() if k == config.preferred_experiment}
        if not catalog:
            raise ValueError("No eligible experiment for this domain")
        store.write("experiment_catalog.json", catalog)
        announce(
            f"Research {len(sources)} source/citation inputs with up to {config.max_workers} agents"
        )
        briefs, parents, candidates = {}, [], {}
        with ThreadPoolExecutor(max_workers=config.max_workers) as pool:
            futures = {pool.submit(research, item): item for item in sources}
            for future in as_completed(futures):
                item = futures[future]
                stage, brief = future.result()
                briefs[item.source_id] = brief.model_dump()
                parents.append(stage)
                for index, direction in enumerate(brief.directions, 1):
                    # Source namespace prevents colliding or invented global branch identities.
                    identifier = f"b{sources.index(item) + 1}_{index}"
                    candidates[identifier] = {
                        **direction.model_dump(),
                        "id": identifier,
                        "source_id": item.source_id,
                    }
                store.write("research_briefs.json", briefs)
        if not candidates:
            report["status"] = "no_supported_directions"
            return report
        store.write("candidates.json", list(candidates.values()))
        selection = ask(
            "consolidation",
            "consolidator",
            {
                "candidates": list(candidates.values()),
                "research_briefs": briefs,
                "goal": report["goal"],
                "budget": config.model_dump(),
            },
            PortfolioSelection,
            parents,
        )
        reviewed = [c.proposal_id for c in selection.critiques]
        accepted = {c.proposal_id for c in selection.critiques if c.decision == "accept"}
        if (
            set(reviewed) != set(candidates)
            or len(reviewed) != len(candidates)
            or len(set(selection.invest)) != len(selection.invest)
            or not set(selection.invest) <= accepted
        ):
            raise ValueError("Consolidation did not critique and select valid candidates")
        # All later investments stay inside the three initially consolidated directions.
        branches = {key: candidates[key] for key in selection.invest}
        if not branches:
            report["status"] = "all_proposals_rejected"
            return report
        if len({b["experiment"] for b in branches.values()}) != len(branches):
            raise ValueError("Consolidator must merge duplicate experiment directions")
        implementation_paths = archive_implementation(store, source, config.domain)
        report["proposals"] = list(branches.values())
        store.write("proposals.json", {"proposals": list(branches.values())})
        for key, branch in branches.items():
            all_rows[key], counts[key] = [], 0
            report["branches"][key] = {
                "proposal": branch,
                "status": "ready",
                "batches": 0,
                "goal_eligible": False,
            }
        announce("Validate the source-grounded baseline before opening simulation branches")
        with store.stage("baseline", parents=["consolidation"]):
            if config.domain == "astrosat":
                baseline = astrosat_baseline()
            else:
                jobs = [
                    (m, "bond", size, p, config.trials, config.seed)
                    for m, p in BENCHMARKS.items()
                    for size in config.sizes
                ]
                rows, _ = _jobs(jobs, config, budget, cache)
                _save_trials(store, "baseline/trials.csv", rows)
                store.write("baseline/summary.json", summarize(rows))
                baseline = baseline_validation(summarize(rows), config.finite_size_tolerance)
                baseline["numerical"] = numerical_checks(rows, budget)
                baseline["passed"] &= baseline["numerical"]["passed"]
            store.write("baseline/validation.json", baseline)
            report["baseline"] = baseline
            report["acceptance"]["baseline_simulations"] = baseline["passed"]
        if not baseline["passed"]:
            report["status"] = "baseline_failed"
            return report
        save()

        def run_batch(key, number, guidance, parent, max_cost):
            branch = branches[key]
            prefix = f"branches/{key}/batches/{number:02d}"
            trial_count = min(config.trials * 2 ** (number - 1), 4096)
            options = {}
            for test, multiplier in (("screen", 1), ("precision", 2)):
                trials = min(trial_count * multiplier, 8192)
                cost = batch_cost(config.domain, trials, config.sizes)
                options[test] = {
                    "trials_per_group": trials,
                    "simulation_cost": cost,
                    "within_simulation_budget": cost <= max_cost,
                }
            plan = ask(
                f"{prefix}/planner",
                "branch_planner",
                {
                    "branch": branch,
                    "branch_id": key,
                    "batch": number,
                    "recipe": catalog[branch["experiment"]],
                    "test_options": options,
                    "previous_result": report["branches"][key],
                    "decision_guidance": guidance,
                    "goal": report["goal"],
                },
                BranchPlan,
                [parent],
            )
            if plan.branch_id != key or plan.experiment != branch["experiment"]:
                raise ValueError("Planner changed the approved branch")
            option = options[plan.selected_test_id]
            if not option["within_simulation_budget"]:
                raise RunBudgetExceeded("Plan exceeds reserved simulation budget")
            store.write(f"{prefix}/test_options.json", options)
            seed = seed_for(config.seed, key, number)
            recipe = catalog[branch["experiment"]]
            specification = {
                "branch_id": key,
                "batch": number,
                "seed": seed,
                "trials_per_group": option["trials_per_group"],
                "recipe": recipe,
            }
            stage = f"{prefix}/experiment"
            with store.stage(stage, parents=[f"{prefix}/planner"]):
                store.write(f"{prefix}/specification.json", specification)
                store.event(
                    "tool_dispatched",
                    {"tool": "execute_batch", "specification": f"{prefix}/specification.json"},
                )
                observed = []
                try:
                    rows = execute_batch(
                        config.domain,
                        recipe,
                        config.sizes,
                        option["trials_per_group"],
                        seed,
                        budget,
                        on_row=observed.append,
                    )
                except BaseException as exc:
                    if observed:
                        _save_trials(store, f"{prefix}/partial-trials.csv", observed)
                    store.write(
                        f"{prefix}/partial-result.json",
                        {
                            "complete": False,
                            "rows_retained": len(observed),
                            "error_type": type(exc).__name__,
                        },
                    )
                    raise
                _save_trials(store, f"{prefix}/trials.csv", rows)
                # Replay complete batch with identical seeds: no extra model call.
                # Charged compute is reserved separately, just like original trials.
                replay = execute_batch(
                    config.domain, recipe, config.sizes, option["trials_per_group"], seed, budget
                )
                if replay != rows:
                    raise ValueError("Independent deterministic batch replay mismatch")
                store.write(f"{prefix}/checks.json", {"passed": True, "replayed_trials": len(rows)})
                store.event(
                    "tool_result",
                    {
                        "tool": "execute_batch",
                        "rows": len(rows),
                        "artifact": f"{prefix}/trials.csv",
                    },
                )
            return key, number, stage, rows, specification, time.monotonic()

        investment = list(branches)
        latest_decision = {"rationale": selection.rationale, "next_experiment": "Initial screening"}
        decision_parent = "baseline"
        checkpoint = 0
        futures = {}
        completions = queue.Queue()
        with ThreadPoolExecutor(max_workers=config.max_workers) as pool:
            while True:
                budget.check()
                # Slots and reservations cover all authorized work, including seed replay.
                in_flight = {v[0] for v in futures.values()}
                for key in investment if report["status"] == "running" else []:
                    if key in in_flight or counts[key] >= config.max_rounds:
                        continue
                    if len(futures) >= config.max_workers:
                        break
                    # Reserve one decision per in-flight result plus this planner/decision.
                    if roles.calls + 2 * len(futures) + 3 > config.max_agent_calls:
                        continue
                    number = counts[key] + 1
                    trials = min(config.trials * 2 ** (number - 1), 4096)
                    minimum = 2 * batch_cost(config.domain, trials, config.sizes)
                    maximum = 2 * batch_cost(config.domain, min(trials * 2, 8192), config.sizes)
                    available = config.max_simulations - budget.simulations - reserved
                    if minimum > available:
                        continue
                    reservation = min(maximum, available)
                    reserved += reservation
                    counts[key] = number
                    report["branches"][key]["status"] = "running"
                    future = pool.submit(
                        run_batch,
                        key,
                        number,
                        dict(latest_decision),
                        decision_parent,
                        reservation // 2,
                    )
                    futures[future] = (key, reservation)
                    future.add_done_callback(completions.put)
                    in_flight.add(key)
                save()
                if not futures:
                    if report["status"] != "running":
                        break
                    if all(counts[k] >= config.max_rounds for k in investment):
                        report["status"] = "round_budget_exhausted"
                    else:
                        report["status"] = "budget_exhausted"
                    break
                try:
                    future = completions.get(timeout=0.5)
                except queue.Empty:
                    continue
                # Arrival order prevents a fast branch starving another completed result.
                _, reservation = futures.pop(future)
                reserved -= reservation
                key, number, stage, rows, specification, result_ready = future.result()
                all_rows[key].extend(rows)
                latest_stages[key] = stage
                summary = summarize_branch(config.domain, all_rows[key], config, number)
                report["branches"][key].update(summary, status="evaluating")
                report["acceptance"]["followup_implemented"] = True
                store.write(f"branches/{key}/batches/{number:02d}/cumulative.json", summary)
                checkpoint += 1
                snapshot = json.loads(json.dumps(report["branches"]))
                remaining = {
                    "seconds": max(0, config.max_seconds - (time.monotonic() - budget.started)),
                    "simulations": config.max_simulations - budget.simulations - reserved,
                    "agent_calls": config.max_agent_calls - roles.calls,
                }
                payload = {
                    "checkpoint": checkpoint,
                    "measurement_contract": MEASUREMENT_CONTRACTS[config.domain],
                    "decision_policy": NUMERICAL_DECISION_POLICY,
                    "goal": report["goal"],
                    "latest_result": {"branch_id": key, **summary},
                    "branches": snapshot,
                    "in_flight": [v[0] for v in futures.values()],
                    "remaining_budget": remaining,
                    "max_batches_per_branch": config.max_rounds,
                    "previous_decision": latest_decision,
                    "previous_validation": report.get("validation"),
                    "previous_validation_branch": report.get("validation_branch_id"),
                }
                prefix = f"checkpoints/{checkpoint:03d}"
                store.write(f"{prefix}/input.json", payload)
                announce(
                    f"Decision agent evaluates {key} batch {number}; "
                    f"{len(futures)} other branches pending"
                )
                started = time.monotonic()
                decision_stage = f"{prefix}/decision"
                prior_status = report["status"]
                decision = ask(
                    decision_stage,
                    "decision_agent",
                    payload,
                    InvestmentDecision,
                    list(latest_stages.values()) + ([decision_parent] if checkpoint > 1 else []),
                )
                if (
                    len(set(decision.invest)) != len(decision.invest)
                    or not set(decision.invest) <= set(branches)
                    or decision.goal_branch_id is not None
                    and decision.goal_branch_id not in branches
                    or decision.action == "invest"
                    and not decision.invest
                ):
                    raise ValueError(
                        "Decision references an unauthorized branch or empty investment"
                    )
                record = {
                    "checkpoint": checkpoint,
                    "branch_id": key,
                    "batch": number,
                    "decision": decision.model_dump(),
                    "input": f"{prefix}/input.json",
                    "decision_seconds": round(time.monotonic() - started, 3),
                    "result_to_decision_seconds": round(time.monotonic() - result_ready, 3),
                    "pending_branches": payload["in_flight"],
                    "goal_accepted": False,
                }
                report["checkpoints"].append(record)
                report["rounds"].append(
                    {
                        "round": checkpoint,
                        "branch_id": key,
                        "batch": number,
                        "effect": summary,
                        "trials_per_size": specification["trials_per_group"],
                        "next_decision": decision.model_dump(),
                    }
                )
                latest_decision, decision_parent = decision.model_dump(), decision_stage
                report["next_decision"] = latest_decision
                report["acceptance"]["live_agents_executed"] = isinstance(roles, OmnigentRoles)
                # Preserve a complete checkpoint even if its final validator fails.
                store.write(f"{prefix}/transition.json", record)
                save()
                if prior_status != "running":
                    record["observation_after_stop"] = True
                    report["status"] = prior_status
                elif decision.action == "finalize":
                    goal_key = decision.goal_branch_id
                    version = (goal_key, report["branches"].get(goal_key, {}).get("batches"))
                    if (
                        goal_key
                        and report["branches"][goal_key]["goal_eligible"]
                        and version not in validation_versions
                    ):
                        validation_versions.add(version)
                        artifacts = []
                        for number in range(1, report["branches"][goal_key]["batches"] + 1):
                            batch_path = f"branches/{goal_key}/batches/{number:02d}"
                            artifacts.append(
                                {
                                    "specification": json.loads(
                                        (output / batch_path / "specification.json").read_text()
                                    ),
                                    "replay_checks": json.loads(
                                        (output / batch_path / "checks.json").read_text()
                                    ),
                                    "raw_trials": batch_path + "/trials.csv",
                                    "sha256": hashlib.sha256(
                                        (output / batch_path / "trials.csv").read_bytes()
                                    ).hexdigest(),
                                }
                            )
                        validation = ask(
                            f"{prefix}/validation",
                            "validator",
                            {
                                "proposal": branches[goal_key],
                                "measurements": report["branches"][goal_key],
                                "baseline": baseline,
                                "goal": report["goal"],
                                "sources": [s.payload() for s in sources],
                                "recipe": catalog[branches[goal_key]["experiment"]],
                                "batch_artifacts": artifacts,
                                "sufficient_statistics": audit_statistics(
                                    config.domain, all_rows[goal_key], config
                                ),
                                "comparison_branches": report["branches"],
                                "implementation": {
                                    name: (output / name).read_text()
                                    for name in implementation_paths
                                },
                                "scope_instruction": (
                                    "Judge the numerical goal for the actual recipe. Separate "
                                    "broader untested proposal claims from that limited result. "
                                    "Baseline scope and checks are supplied in baseline. "
                                    "Follow-up replays are in batch_artifacts. "
                                    "Raw CSVs are retained locally. "
                                    "Exact sufficient statistics and full implementation are "
                                    "supplied for review. Do not claim to have read CSVs."
                                ),
                                "claim_scope": "Scoped simulation result only; no global novelty, "
                                "real-world prediction, universality or full-paper reproduction.",
                            },
                            ValidationReview,
                            [decision_stage],
                        )
                        report["validation"] = validation.model_dump()
                        report["validation_branch_id"] = goal_key
                        if validation.decision == "supported":
                            report["goal"].update(achieved=True, branch_id=goal_key)
                            record["goal_accepted"] = True
                            report["status"] = "goal_achieved"
                        elif validation.decision == "reject":
                            report["status"] = "validation_rejected"
                    if report["status"] == "running":
                        record["finalization_blocked"] = (
                            "Numerical goal or independent validation unmet"
                        )
                        investment = decision.invest or [goal_key or key]
                elif decision.action == "stop":
                    report["status"] = "research_stopped"
                else:
                    investment = decision.invest
                for branch_key, state in report["branches"].items():
                    if branch_key not in {v[0] for v in futures.values()}:
                        state["status"] = "ready" if branch_key in investment else "paused"
                store.write(f"{prefix}/transition.json", record)
                save()
        if report["status"] == "running":
            report["status"] = "round_budget_exhausted"
    except (RunBudgetExceeded, AgentBudgetExceeded, TimeoutError) as exc:
        cancelled.set()
        report["status"], report["reason"] = "budget_exhausted", type(exc).__name__
    except AgentUnavailable as exc:
        cancelled.set()
        report["status"], report["reason"] = "blocked_live_backend", str(exc)
    except DecisionAbstained as exc:
        cancelled.set()
        report["status"], report["reason"] = "needs_decision_review", str(exc)
    except KeyboardInterrupt:
        cancelled.set()
        report["status"] = "interrupted"
    except Exception as exc:
        cancelled.set()
        report["status"], report["reason"] = "failed", type(exc).__name__
        raise
    finally:
        if roles:
            roles.close()
        save_comparisons(store, report, config.model_dump(), [s.payload() for s in sources])
        save()
        store.event("run_finished", {"status": report["status"]})
        store.seal()
    return report
