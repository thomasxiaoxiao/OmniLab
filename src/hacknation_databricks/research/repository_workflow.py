"""Paper/repository-driven specialist loop with a bounded Omnigent Python/C tool."""

import hashlib
import math
import time
from pathlib import Path

import numpy as np
from pydantic import ValidationError
from scipy.stats import t

from .agents import AgentBudgetExceeded, AgentUnavailable, OmnigentRoles
from .artifacts import RunStore, canonical, environment
from .code_archive import archive_framework
from .code_sandbox import code_capability, execute_code
from .process_player import process_html
from .process_visualization import checked_process
from .repository_models import (
    RepositoryBrief,
    RepositoryDecision,
    RepositoryImplementation,
    RepositoryPlan,
    RepositoryReview,
)
from .repository_source import fetch_repository, read_repository_files, repository_links
from .sources import check_evidence

PROJECT_DEADLINE = 1791097620  # 2026-10-04 07:07 UTC; original project hard stop.


def summarize_trials(result, plan):
    trials = result["trials"]
    samples = {
        arm: [r["output"]["metric"] for r in trials if r["arm"] == arm]
        for arm in ("control", "proposed")
    }
    for row in trials:
        if not plan.metric_lower <= row["output"]["metric"] <= plan.metric_upper:
            raise ValueError("Measured metric is outside its preregistered bounds")
    sanity = next(r["output"]["metric"] for r in trials if r["arm"] == "sanity")
    if abs(sanity - plan.sanity_expected) > plan.sanity_tolerance:
        raise ValueError("Preregistered baseline sanity check failed")
    replay = next(r["output"] for r in trials if r["arm"] == "replay")
    original = next(r["output"] for r in trials if r["arm"] == "control")
    if replay != original:
        raise ValueError("Identical seeded baseline did not replay exactly")
    diffs = np.asarray(samples["proposed"]) - np.asarray(samples["control"])
    mean = float(np.mean(diffs))
    half = float(t.ppf(0.975, len(diffs) - 1) * np.std(diffs, ddof=1) / math.sqrt(len(diffs)))
    return {
        "metric": plan.metric,
        "units": plan.units,
        "samples_per_arm": len(diffs),
        "control_mean": float(np.mean(samples["control"])),
        "proposed_mean": float(np.mean(samples["proposed"])),
        "difference": mean,
        "interval": [mean - half, mean + half],
        "sanity_passed": True,
        "replay_passed": True,
        "interval_method": "Paired-seed Student t interval, 95%; exploratory, no sequential "
        "or multiple-testing correction.",
        "meaningful_difference": plan.meaningful_difference,
    }


def validate_process_variation(result):
    """Prevent scalar identities from being promoted as simulated processes."""
    displayed = [
        next(r for r in result["trials"] if r["arm"] == arm) for arm in ("control", "proposed")
    ]
    if all(
        np.allclose(row["output"]["values"], row["output"]["values"][0], rtol=1e-10, atol=1e-12)
        for row in displayed
    ):
        raise ValueError(
            "Both displayed trajectories are constant; "
            "retain as a diagnostic, not a process simulation"
        )


def process_from_trials(result, plan, *, provenance, artifact):
    """Map actual scalar trajectories to the shared player without a domain-specific model."""
    control = next(r for r in result["trials"] if r["arm"] == "control")
    proposed = next(r for r in result["trials"] if r["arm"] == "proposed")
    times = control["output"]["times"]
    if proposed["output"]["times"] != times:
        raise ValueError("Control and proposed trajectories must share recorded sample times")
    values = control["output"]["values"] + proposed["output"]["values"]
    trajectory_units = plan.trajectory_units or plan.units
    lo, hi = min(values), max(values)
    margin = max((hi - lo) * 0.08, 0.01)

    def world(row, label, color):
        values = row["output"]["values"]
        return {
            "label": label,
            "description": f"Recorded seed {row['seed']}: {row['parameters']}",
            "geometry": [
                {
                    "kind": "line",
                    "x": times[i - 1],
                    "y": values[i - 1],
                    "x2": times[i],
                    "y2": values[i],
                    "color": color,
                    "start": i,
                }
                for i in range(1, len(times))
            ],
            "frames": [
                {"caption": f"Step {step:g}: {value:g} {trajectory_units}", "glyphs": []}
                for step, value in zip(times, values, strict=True)
            ],
        }

    return checked_process(
        {
            "title": plan.trajectory_label or plan.metric,
            "description": "Recorded process samples from a paper-based implementation."
            if not provenance["repository_url"]
            else "Recorded process samples from the pinned repository experiment.",
            "x_label": "Recorded time / simulation step",
            "y_label": trajectory_units,
            "timeline_label": "Recorded time / simulation step",
            "times": times,
            "bounds": [times[0], times[-1], lo - margin, hi + margin],
            "original": world(control, "Original / control", "control"),
            "proposed": world(proposed, "Proposed", "proposed"),
            "selection": "First preregistered seed in each arm; all seeds are retained in "
            "raw trials.",
            "limitations": "A recorded scalar trajectory, not a spatial reconstruction. "
            + " ".join(plan.limitations),
            "replayed_trials": 0,
            "inputs": [{"artifact": artifact, "seed": control["seed"]}],
            "provenance": provenance,
        }
    )


def run_repository(
    source,
    output,
    config,
    *,
    backend="omnigent",
    literature=None,
    progress=None,
    roles_factory=None,
    retrieval_report=None,
    repository_fetcher=fetch_repository,
    code_executor=execute_code,
):
    if backend != "omnigent" and not (backend == "fixture" and roles_factory):
        raise ValueError(
            "Repository research requires live Omnigent; there is no alternate backend"
        )
    sources = [source, *(literature or [])]
    if (
        source.source_id != "seed"
        or len(sources) > 8
        or len({s.source_id for s in sources}) != len(sources)
        or len({s.sha256 for s in sources}) != len(sources)
        or sum(sum(map(len, s.pages)) for s in sources) > 180_000
    ):
        raise ValueError("Invalid or over-budget research sources; nothing was truncated")
    store = RunStore(output)
    started = time.monotonic()
    deadline = started + config.max_seconds
    if backend != "fixture":
        deadline = min(deadline, started + PROJECT_DEADLINE - time.time())
    roles = None
    report = {
        "workflow_version": "5",
        "workflow": "repository",
        "backend": backend,
        "status": "running",
        "rounds": [],
        "proposals": [],
        "computed_simulations": 0,
        "scientific_novelty": "unverified",
        "process_validation": "changing_recorded_states_v1",
        "final_experiment": None,
        "goal": {"achieved": False},
        "acceptance": {
            "live_agents_executed": False,
            "baseline_simulations": False,
            "followup_implemented": False,
            "simulated_world_comparison": False,
            "full_paper_reproduction": False,
        },
        "acceleration": {
            "bottleneck": "Repository result to next scientific decision",
            "observed_decision_seconds": [],
            "multiplier": None,
            "status": "No comparable manual baseline measured",
        },
    }

    def save():
        report["elapsed_seconds"] = round(time.monotonic() - started, 3)
        report["role_calls"] = roles.calls if roles else 0
        store.write("report.json", report)

    def check():
        if time.monotonic() >= deadline or (
            backend != "fixture" and time.time() >= PROJECT_DEADLINE
        ):
            raise TimeoutError("Run or project deadline reached")

    def ask(stage, role, data, contract, parents):
        check()
        if progress:
            progress(role.replace("_", " ").capitalize())
        with store.stage(stage, parents=parents):
            try:
                value = roles.ask(role, data, contract)
            except ValidationError as exc:
                errors = exc.errors(include_input=False, include_url=False, include_context=False)
                store.write(stage + "_contract_failure.json", {"errors": errors, "max_repairs": 1})
                value = roles.ask(
                    role,
                    {
                        **data,
                        "contract_repair": {
                            "errors": errors,
                            "instruction": "One correction attempt for the rejected structured "
                            "response. Return a complete object matching the supplied schema and "
                            "these validation requirements. Preserve the reviewed hypothesis "
                            "and evidence; do not claim execution or relax scientific checks.",
                        },
                    },
                    contract,
                )
            store.write(stage + ".json", value.model_dump())
        save()
        return value

    def grounded(stage, role, data, contract, parents, extract_evidence, evidence_sources):
        value = ask(stage, role, data, contract, parents)
        accepted_stage = stage
        try:
            for item in extract_evidence(value):
                check_evidence(item, evidence_sources)
        except ValueError:
            store.write(
                stage + "_evidence_failure.json",
                {
                    "rejected": value.model_dump(),
                    "reason": "Evidence is outside the allowed sources or is not exact on its page",
                    "allowed_source_ids": [s.source_id for s in evidence_sources],
                    "maximum_repairs": 1,
                },
            )
            accepted_stage = stage + "_repair"
            value = ask(
                accepted_stage,
                role,
                {
                    **data,
                    "rejected": value.model_dump(),
                    "allowed_evidence_source_ids": [s.source_id for s in evidence_sources],
                    "repair": "One correction attempt. Preserve the scientific intent, but replace "
                    "every evidence quote with a short exact contiguous passage on its stated "
                    "1-based page in an allowed evidence source. Remove citations to all other "
                    "source IDs. Do not paraphrase, join pages, or silently alter hyphenation.",
                },
                contract,
                [stage],
            )
            for item in extract_evidence(value):
                check_evidence(item, evidence_sources)
        store.write("approved_" + stage + ".json", value.model_dump())
        return value, accepted_stage

    store.write("config.json", config.model_dump())
    store.write("environment.json", environment())
    store.write("sources.json", [s.payload() for s in sources])
    store.write("capability.json", code_capability())
    archive_framework(output)
    for item in sources:
        store.write_text(f"sources/{item.source_id}.txt", "\n\f\n".join(item.pages))
        original = Path(item.path)
        if original.is_file():
            target = output / "sources" / (item.source_id + original.suffix)
            target.write_bytes(original.read_bytes())
    save()
    try:
        check()
        links = repository_links(source)
        url = config.repository_url or (
            next(iter(links)) if len(links) == 1 and not config.allow_paper_implementation else ""
        )
        if not url and not config.allow_paper_implementation:
            report.update(
                status="repository_required",
                reason="Supply the paper's GitHub repository. No unique repository link "
                "was found in the saved paper.",
            )
            return report
        with store.stage("repository", parents=[]):
            if url:
                manifest = repository_fetcher(source, url, config.repository_ref, store)
                report["repository"] = {k: v for k, v in manifest.items() if k != "files"}
                report["code_origin"] = "repository"
            else:
                manifest = {
                    "url": "",
                    "commit": "",
                    "files": [],
                    "source_sha256": source.sha256,
                    "origin": "paper_implementation",
                }
                store.write("repository/manifest.json", manifest)
                report["code_origin"] = "paper_implementation"
        paper_only = report["code_origin"] == "paper_implementation"
        store.write("capability.json", code_capability(paper_only))
        roles = (roles_factory or OmnigentRoles)(sources, store, config)
        if isinstance(roles, OmnigentRoles):
            roles.deadline = min(roles.deadline, deadline)
        common = {
            "source": source.payload(),
            "literature": [s.payload() for s in sources[1:]],
            "repository": manifest,
            "research_areas": config.research_areas,
            "capability": code_capability(paper_only),
            "code_origin": report["code_origin"],
        }
        brief, reader_stage = grounded(
            "reader",
            "repository_reader",
            common,
            RepositoryBrief,
            ["repository"],
            lambda b: [e for d in b.directions for e in d.evidence],
            [source],
        )
        report["proposals"] = [d.model_dump() for d in brief.directions]
        if not paper_only and not brief.repository_files:
            raise ValueError("Repository reader must select source files")
        code = read_repository_files(store, manifest, brief.repository_files)
        store.write(
            "repository/read_files.json",
            {
                "paths": brief.repository_files,
                "characters": sum(map(len, code.values())),
                "truncated": False,
            },
        )
        review, critic_stage = grounded(
            "critic",
            "repository_critic",
            {
                **common,
                "brief": brief.model_dump(),
                "code": code,
                "literature": [s.payload() for s in sources[1:]],
                "retrieval": retrieval_report,
            },
            RepositoryReview,
            [reader_stage],
            lambda r: r.evidence,
            sources,
        )
        ids = {d.id for d in brief.directions}
        if {c.proposal_id for c in review.critiques} != ids or len(review.critiques) != len(ids):
            raise ValueError("Critic must assess each paper direction exactly once")
        accepted = {c.proposal_id for c in review.critiques if c.decision == "accept"}
        if review.selected_proposal_id is None:
            report.update(
                status="research_stopped",
                reason="Critic did not accept a feasible repository experiment.",
            )
            return report
        if review.selected_proposal_id not in accepted:
            raise ValueError("Critic selected an unaccepted proposal")
        proposal = next(d for d in brief.directions if d.id == review.selected_proposal_id)
        report["selected_proposal"] = proposal.model_dump()
        plan = ask(
            "planner",
            "repository_planner",
            {
                **common,
                "proposal": proposal.model_dump(),
                "review": review.model_dump(),
                "code": code,
                "budget": config.model_dump(),
            },
            RepositoryPlan,
            [critic_stage],
        )
        if plan.proposal_id != proposal.id or plan.hypothesis != proposal.hypothesis:
            raise ValueError("Planner changed the reviewed hypothesis")
        if any(test.replicates > min(config.trials, 32) for test in plan.tests):
            raise ValueError("Planner exceeded the paired-replicate budget")
        permitted = {"numpy", "scipy", "ephem"}
        for dependency in plan.dependencies:
            if dependency.split("==")[0].lower() not in permitted | {plan.primary_module.lower()}:
                raise ValueError(
                    "Experiment requires packages outside the available numerical environment"
                )
            if "==" in dependency and dependency.split("==")[0].lower() in permitted:
                from importlib.metadata import version

                name, pin = dependency.split("==")
                if version(name) != pin:
                    raise ValueError(
                        "Requested numerical dependency differs from installed version"
                    )
        implementation = ask(
            "implementation",
            "repository_experimenter",
            {
                **common,
                "plan": plan.model_dump(),
                "code": code,
                "execution_contract": {
                    "seed": "Use the seed argument for all randomness. Accept every integer "
                    "from 0 through 2**32-1, including sanity/replay seeds. Never hardcode or "
                    "validate against a planner-authored list of seeds in parameter prose.",
                    "first_seed": (config.seed + 1009) % 2**32,
                    "followup": "Accept revised numerical parameters from the evaluator "
                    "without restricting them to the first baseline/treatment pair.",
                },
            },
            RepositoryImplementation,
            ["planner"],
        )
        if not paper_only and not implementation.repository_files:
            raise ValueError("Repository implementation must use selected source files")
        if not set(implementation.repository_files).issubset(code):
            raise ValueError("Implementation references unread repository files")
        if not set(implementation.c_repository_files).issubset(code):
            raise ValueError("C compilation references unread repository files")
        store.write_text("code/experiment.py", implementation.python_code)
        if implementation.c_code:
            store.write_text("code/experiment.c", implementation.c_code)
        store.write(
            "code/provenance.json",
            {
                "source_sha256": source.sha256,
                "repository_commit": manifest["commit"],
                "files": [
                    "code/experiment.py",
                    *(["code/experiment.c"] if implementation.c_code else []),
                ],
                "repository_files": implementation.repository_files,
                "origin": "Omnigent experimenter implemented from paper evidence"
                if paper_only
                else "Omnigent experimenter generated from pinned repository source",
            },
        )
        replicates = next(t.replicates for t in plan.tests if t.id == plan.selected_test_id)
        treatment = plan.treatment
        parent = "implementation"
        for number in range(1, config.max_rounds + 1):
            check()
            prefix = f"rounds/{number:02d}"
            seeds = [(config.seed + number * 1009 + i) % 2**32 for i in range(replicates)]
            jobs = [
                {"arm": arm, "seed": seed, "parameters": params}
                for seed in seeds
                for arm, params in [("control", plan.baseline), ("proposed", treatment)]
            ]
            jobs += [
                {"arm": "sanity", "seed": seeds[0], "parameters": plan.sanity},
                {"arm": "replay", "seed": seeds[0], "parameters": plan.baseline},
            ]
            if report["computed_simulations"] + len(jobs) > config.max_simulations:
                report.update(
                    status="budget_exhausted",
                    reason="The chosen test exceeds the remaining simulation budget.",
                )
                break
            # Reserve all requested work, including failed jobs, before starting the tool.
            report["computed_simulations"] += len(jobs)
            with store.stage(prefix + "/experiment", parents=[parent]):
                store.write(
                    prefix + "/specification.json",
                    {"plan": plan.model_dump(), "treatment": treatment, "seeds": seeds},
                )
                result = code_executor(
                    store,
                    implementation,
                    manifest,
                    jobs,
                    stage=prefix,
                    timeout=min(config.code_timeout_seconds, max(1, deadline - time.monotonic())),
                )
                summary = summarize_trials(result, plan)
                store.write(prefix + "/summary.json", summary)
                validate_process_variation(result)
                raw_name = prefix + "/trials.json"
                process = process_from_trials(
                    result,
                    plan,
                    artifact=raw_name,
                    provenance={
                        "run_id": output.name,
                        "source_sha256": source.sha256,
                        "repository_url": manifest["url"],
                        "repository_commit": manifest["commit"],
                        "artifacts": [
                            {
                                "path": raw_name,
                                "sha256": hashlib.sha256(
                                    (output / raw_name).read_bytes()
                                ).hexdigest(),
                            }
                        ],
                    },
                )
                envelope = {"status": "ready", "process": process}
                store.write(prefix + "/process.json", envelope)
                store.write_text(prefix + "/process.html", process_html(process, scalar_axes=True))
                store.write("comparison/process.json", envelope)
                store.write_text("comparison/process.html", process_html(process, scalar_axes=True))
                report["acceptance"].update(
                    baseline_simulations=True,
                    followup_implemented=True,
                    simulated_world_comparison=True,
                )
                report["rounds"].append(
                    {
                        "round": number,
                        "summary": summary,
                        "artifact_prefix": prefix,
                        "treatment": treatment,
                    }
                )
                save()
            decision_started = time.monotonic()
            decision = ask(
                prefix + "/decision",
                "repository_evaluator",
                {
                    "plan": plan.model_dump(),
                    "current_treatment": treatment,
                    "summary": summary,
                    "prior_results": report["rounds"],
                    "remaining_rounds": config.max_rounds - number,
                    "limitations": review.missing_evidence,
                    "implementation": implementation.model_dump(),
                },
                RepositoryDecision,
                [prefix + "/experiment"],
            )
            report["acceleration"]["observed_decision_seconds"].append(
                time.monotonic() - decision_started
            )
            report["rounds"][-1]["next_decision"] = decision.model_dump()
            report["next_decision"] = decision.model_dump()
            parent = prefix + "/decision"
            if decision.action == "stop":
                report["status"] = "research_stopped"
                break
            if not decision.next_treatment or decision.next_treatment in (treatment, plan.baseline):
                raise ValueError("A result-driven follow-up must change the treatment parameters")
            if set(decision.next_treatment) != set(plan.baseline):
                raise ValueError("Follow-up must supply the complete approved parameter keys")
            if len(canonical(decision.next_treatment)) > 16_000:
                raise ValueError("Follow-up parameters exceed their budget")
            treatment = decision.next_treatment
            save()
        else:
            report.update(
                status="budget_exhausted",
                reason="Finite iteration budget reached; proposed next step remains unexecuted.",
            )
    except (AgentUnavailable, AgentBudgetExceeded) as exc:
        report.update(
            status="blocked_live_backend",
            reason=f"Omnigent request stopped ({type(exc).__name__}).",
        )
    except (TimeoutError, KeyboardInterrupt):
        report.update(status="interrupted", reason="Run interrupted or time limit reached.")
    except Exception as exc:
        message = str(exc)[:1000]
        store.write("failure.json", {"error_type": type(exc).__name__, "message": message})
        report.update(
            status="failed",
            reason=f"Repository workflow failed ({type(exc).__name__}): {message[:300]}",
        )
    finally:
        if roles:
            roles.close()
        if report["status"] in {"research_stopped", "budget_exhausted"} and report["rounds"]:
            last = report["rounds"][-1]
            if last.get("next_decision"):
                report["final_experiment"] = last["round"]
        report["acceptance"]["live_agents_executed"] = (
            backend == "omnigent"
            and roles_factory is None
            and bool(report["rounds"])
            and "next_decision" in report
        )
        save()
        store.event("run_finished", {"status": report["status"]})
        store.seal()
    return report
