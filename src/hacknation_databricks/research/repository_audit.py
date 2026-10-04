"""Verify repository runs and their handoffs without executing archived code."""

import ast
import hashlib
import json
import re

from .agent_visualization import agent_process
from .assessment_evidence import assessment_evidence
from .code_sandbox import SimulationSample, paper_implementation
from .experiment_history import reject_repeated_direction
from .legacy_audit import process_from_trials, validate_process_variation
from .models import RunConfig
from .process_visualization import checked_process
from .repository_decisions import decision_state, verify_handoff
from .repository_models import (
    AgentRepositoryDecision,
    AgentRepositoryPlan,
    ExplorationRepositoryPlan,
    ExplorationRepositoryReview,
    RepositoryBrief,
    RepositoryDecision,
    RepositoryLiterature,
    RepositoryPlan,
    RepositoryReview,
)
from .repository_workflow import summarize_trials, validate_trials
from .sources import Source, check_evidence


def verify_repository_outputs(directory, report, artifacts):
    if report.get("workflow") != "repository":
        return []
    try:

        def read(name):
            if name not in artifacts:
                raise ValueError("Unsealed repository evidence")
            return json.loads((directory / name).read_text())

        config = RunConfig.model_validate(read("config.json"))
        for count, limit in [
            ("role_calls", config.max_agent_calls),
            ("computed_simulations", config.max_simulations),
        ]:
            if type(report.get(count)) is not int or not 0 <= report[count] <= limit:
                raise ValueError("Repository workflow exceeded declared budget")
        if len(report["rounds"]) > config.max_rounds:
            raise ValueError("Iteration budget exceeded")
        if report.get("evaluator_backend") == "anyjev" and (
            config.decision_backend != "anyjev"
            or type(report.get("decision_calls")) is not int
            or not 0 <= report["decision_calls"] <= config.max_decision_calls
        ):
            raise ValueError("AnyJev evaluator configuration or budget is invalid")
        if "final_experiment" in report:
            expected_final = None
            if report["status"] in {"research_stopped", "budget_exhausted"} and report["rounds"]:
                last = report["rounds"][-1]
                if last.get("next_decision"):
                    expected_final = last["round"]
            if report["final_experiment"] != expected_final:
                raise ValueError("Final experiment is not the single terminal evaluated result")
        sources = [Source(**{**s, "pages": tuple(s["pages"])}) for s in read("sources.json")]
        if "approved_literature.json" in artifacts:
            literature = RepositoryLiterature.model_validate(read("approved_literature.json"))
            for evidence in literature.evidence:
                check_evidence(evidence, sources)
        if report.get("proposals"):
            name = "approved_reader.json" if "approved_reader.json" in artifacts else "reader.json"
            brief = RepositoryBrief.model_validate(read(name))
            for direction in brief.directions:
                for evidence in direction.evidence:
                    check_evidence(evidence, sources[:1])
        if "approved_critic.json" in artifacts or report.get("selected_proposal"):
            name = "approved_critic.json" if "approved_critic.json" in artifacts else "critic.json"
            review_type = (
                ExplorationRepositoryReview if report.get("scenario_contract") else RepositoryReview
            )
            review = review_type.model_validate(read(name))
            for evidence in review.evidence:
                check_evidence(evidence, sources)
            if report.get("scenario_contract"):
                history = read("prior-experiments.json")
                if history["source_sha256"] != sources[0].sha256:
                    raise ValueError("History belongs to another paper")
                if review.selected_proposal_id and config.exploration_mode == "new_direction":
                    selected = next(
                        d for d in brief.directions if d.id == review.selected_proposal_id
                    )
                    reject_repeated_direction(selected, history)
        preflights = report.get("preflight_attempts", [])
        preflight_jobs = sum(p["reserved_jobs"] for p in preflights)
        if (
            preflight_jobs != report.get("preflight_simulations", 0)
            or preflight_jobs > report["computed_simulations"]
            or len(preflights) > config.max_code_repairs + 1
        ):
            raise ValueError("Invalid preflight budget")
        for i, pilot in enumerate(preflights):
            if pilot["prefix"] != f"preflight/{i:02d}" or pilot["reserved_jobs"] != 4:
                raise ValueError("Invalid preflight history")
            if pilot["status"] == "failed":
                read(pilot["prefix"] + "/failure.json")
            elif pilot["status"] == "passed":
                read(pilot["prefix"] + "/feasibility.json")
            elif pilot["status"] != "running" or report["status"] != "interrupted":
                raise ValueError("Invalid preflight outcome")
        if not report["rounds"]:
            if report["acceptance"]["followup_implemented"]:
                raise ValueError("Experiment claim without results")
            return []
        manifest = read("repository/manifest.json")
        paper_only = paper_implementation(manifest)
        if paper_only and (
            not config.allow_paper_implementation
            or config.repository_url
            or report.get("code_origin") != "paper_implementation"
            or read("implementation.json")["repository_files"]
            or read("implementation.json").get("c_repository_files")
        ):
            raise ValueError("Paper implementation lacks its explicit authorization or provenance")
        if manifest["source_sha256"] != sources[0].sha256:
            raise ValueError("Repository bound to another paper")
        for item in manifest["files"]:
            if (
                artifacts.get("repository/source/" + item["path"], {}).get("sha256")
                != item["sha256"]
            ):
                raise ValueError("Repository source inventory does not match sealed code")
        plan_type = AgentRepositoryPlan if report.get("learning_contract") else RepositoryPlan
        if report.get("scenario_contract"):
            plan_type = ExplorationRepositoryPlan
        plan = plan_type.model_validate(read("planner.json"))
        if (
            report.get("scenario_contract")
            and config.required_sweep
            and plan.sweep != config.required_sweep
        ):
            raise ValueError("Executed plan changed the requested sweep")
        for pilot in preflights:
            if pilot["status"] == "passed":
                feasibility = read(pilot["prefix"] + "/feasibility.json")
                pilot_result = read(pilot["prefix"] + "/trials.json")
                pilot_execution = read(pilot["prefix"] + "/execution.json")
                implementation = read(pilot["prefix"] + "/implementation.json")
                jobs = [
                    {"arm": arm, "seed": (config.seed + 1009) % 2**32, "parameters": parameters}
                    for arm, parameters in [
                        ("control", plan.baseline),
                        ("proposed", plan.treatment),
                        ("sanity", plan.sanity),
                        ("replay", plan.baseline),
                    ]
                ]
                if pilot_execution["jobs"] != jobs or len(pilot_result["trials"]) != 4:
                    raise ValueError("Preflight did not execute approved jobs")
                for trial, job in zip(pilot_result["trials"], jobs, strict=True):
                    if {k: trial[k] for k in job} != job:
                        raise ValueError("Preflight changed parameters or seeds")
                    SimulationSample.model_validate(trial["output"])
                validate_trials(pilot_result, plan)
                if (
                    pilot_execution["returncode"]
                    or pilot_execution["failure"]
                    or not feasibility["sanity_passed"]
                    or not feasibility["replay_passed"]
                    or implementation != read("implementation.json")
                ):
                    raise ValueError("Preflight accepted a failed or different implementation")
                if pilot_execution["backend"] != "fixture" and any(
                    pilot_execution[key + "_sha256"]
                    != hashlib.sha256(implementation[key + "_code"].encode()).hexdigest()
                    for key in ("python", "c")
                ):
                    raise ValueError("Preflight executed different code")
            else:
                read(pilot["prefix"] + "/failure.json")
        if preflights and preflights[-1]["status"] != "passed":
            raise ValueError("Accepted experiment without passed preflight")
        computed_jobs = preflight_jobs
        if any(test.replicates > min(config.trials, 32) for test in plan.tests):
            raise ValueError("Plan exceeds the paired-replicate budget")
        n = next(t.replicates for t in plan.tests if t.id == plan.selected_test_id)
        precision_n = next(t.replicates for t in plan.tests if t.id == "precision")
        for number, row in enumerate(report["rounds"], 1):
            if row["round"] != number:
                raise ValueError("Experiment rounds must be consecutive")
            if number > 1:
                previous = report["rounds"][number - 2]
                if previous["next_decision"]["action"] == "precision":
                    if not report.get("precision_continuation") or precision_n <= n:
                        raise ValueError("Unapproved or repeated precision test")
                    n = precision_n
            prefix = row["artifact_prefix"]
            if prefix != f"rounds/{row['round']:02d}":
                raise ValueError("Invalid result path")
            result = read(prefix + "/trials.json")
            spec = read(prefix + "/specification.json")
            expected_seeds = [(config.seed + row["round"] * 1009 + i) % 2**32 for i in range(n)]
            if (
                spec["seeds"] != expected_seeds
                or RepositoryPlan.model_validate(spec["plan"]).model_dump() != plan.model_dump()
            ):
                raise ValueError("Experiment changed preregistered seeds or plan")
            if spec["treatment"] != row["treatment"]:
                raise ValueError("Treatment differs from the recorded experiment")
            expected_jobs = [
                {"arm": arm, "seed": seed, "parameters": params}
                for seed in expected_seeds
                for arm, params in [("control", plan.baseline), ("proposed", row["treatment"])]
            ]
            expected_jobs += [
                {"arm": "sanity", "seed": expected_seeds[0], "parameters": plan.sanity},
                {"arm": "replay", "seed": expected_seeds[0], "parameters": plan.baseline},
            ]
            computed_jobs += len(expected_jobs)
            diagnostics = None
            if report.get("diagnostic_handoff"):
                diagnostics = assessment_evidence(result, prefix + "/trials.json")
                if diagnostics != read(prefix + "/assessment-evidence.json"):
                    raise ValueError("Researcher diagnostics differ from measured trials")
            if row.get("next_decision") and report.get("evaluator_backend") == "anyjev":
                decision_type = (
                    AgentRepositoryDecision
                    if report.get("learning_contract")
                    else RepositoryDecision
                )
                assessment = decision_type.model_validate(read(prefix + "/assessment.json"))
                state = decision_state(
                    plan,
                    row["treatment"],
                    row["summary"],
                    assessment,
                    {
                        "rounds": config.max_rounds - row["round"],
                        "simulations": config.max_simulations - computed_jobs,
                        "jobs_per_round": len(expected_jobs),
                        **(
                            {"current_replicates": n, "precision_replicates": precision_n}
                            if report.get("precision_continuation")
                            else {}
                        ),
                    },
                    diagnostics=diagnostics,
                )
                if state != read(prefix + "/evaluation-input.json"):
                    raise ValueError("Evaluator input changed measured evidence or budget")
                decision = read(prefix + "/decision.json")
                if decision != row["next_decision"]:
                    raise ValueError("Reported decision differs from the evaluator output")
                handoff = read(prefix + "/anyjev-handoff.json")
                record = read(handoff["decision_artifact"])
                if record["stage"] != prefix + "/decision":
                    raise ValueError("AnyJev evaluation attached to another round")
                verify_handoff(state, decision, handoff, record)
            expected_treatment = (
                plan.treatment
                if row["round"] == 1
                else report["rounds"][row["round"] - 2]["treatment"]
                if report["rounds"][row["round"] - 2]["next_decision"]["action"] == "precision"
                else (report["rounds"][row["round"] - 2]["next_decision"]["next_treatment"])
            )
            if row["treatment"] != expected_treatment:
                raise ValueError("Executed treatment differs from the preceding decision")
            if len(result["trials"]) != len(expected_jobs):
                raise ValueError("Missing or additional trials")
            for trial, job in zip(result["trials"], expected_jobs, strict=True):
                if {k: trial[k] for k in job} != job:
                    raise ValueError("Trials do not match the planned jobs")
                SimulationSample.model_validate(trial["output"])
            summary = summarize_trials(result, plan)
            if report.get("process_validation") == "changing_recorded_states_v1":
                validate_process_variation(result)
            if summary != row["summary"] or summary != read(prefix + "/summary.json"):
                raise ValueError("Summary disagrees with raw results")
            execution = read(prefix + "/execution.json")
            if execution.get("jobs") != expected_jobs:
                raise ValueError("Execution handoff changed the approved jobs")
            if execution["returncode"] or execution["failure"]:
                raise ValueError("Accepted a failed simulation")
            if execution["repository_commit"] != manifest["commit"]:
                raise ValueError("Execution used another repository revision")
            if execution["source_sha256"] != sources[0].sha256:
                raise ValueError("Execution used another source")
            if execution["backend"] not in {"darwin_seatbelt", "linux_bwrap", "fixture"}:
                raise ValueError("Unknown sandbox backend")
            if execution["backend"] == "fixture" and report["backend"] != "fixture":
                raise ValueError("Test executor mislabeled as live")
            if execution["backend"] != "fixture":
                if execution["python_sha256"] != artifacts["code/experiment.py"]["sha256"]:
                    raise ValueError("Executed Python differs from the archived program")
                expected_c = artifacts.get("code/experiment.c", {}).get(
                    "sha256", hashlib.sha256(b"").hexdigest()
                )
                if execution["c_sha256"] != expected_c:
                    raise ValueError("Executed C differs from the archived program")
            if report.get("process_validation") == "agent_recorded_scene_v1":
                raw_name = prefix + "/trials.json"
                expected = agent_process(
                    result,
                    plan,
                    artifact=raw_name,
                    provenance={
                        "run_id": directory.name,
                        "source_sha256": sources[0].sha256,
                        "repository_url": manifest["url"],
                        "repository_commit": manifest["commit"],
                        "artifacts": [{"path": raw_name, "sha256": artifacts[raw_name]["sha256"]}],
                    },
                )
                if expected != read(prefix + "/process.json"):
                    raise ValueError("Visualization differs from agent-emitted scene data")
                if expected["status"] == "ready" and prefix + "/process.html" not in artifacts:
                    raise ValueError("Missing agent scene export")
            else:
                process = checked_process(read(prefix + "/process.json")["process"])
                if prefix + "/process.html" not in artifacts:
                    raise ValueError("Missing playable export")
                for reference in process["provenance"]["artifacts"]:
                    if artifacts.get(reference["path"], {}).get("sha256") != reference["sha256"]:
                        raise ValueError("Process input hash changed")
                provenance = process["provenance"]
                if (
                    provenance["source_sha256"] != sources[0].sha256
                    or provenance["repository_commit"] != manifest["commit"]
                    or provenance["repository_url"] != manifest["url"]
                ):
                    raise ValueError("Process refers to another paper or repository")
                expected_process = process_from_trials(
                    result, plan, provenance=provenance, artifact=prefix + "/trials.json"
                )
                # Early v5 captions used Python dict repr before JSON sorted its keys.
                # Compare the recorded parameter values, not their insertion order.
                for world, arm in [("original", "control"), ("proposed", "proposed")]:
                    trial = next(t for t in result["trials"] if t["arm"] == arm)
                    caption = process[world]["description"]
                    heading = f"Recorded seed {trial['seed']}: "
                    if (
                        not caption.startswith(heading)
                        or ast.literal_eval(caption[len(heading) :]) != trial["parameters"]
                    ):
                        raise ValueError("Process caption does not match the recorded parameters")
                    expected_process[world]["description"] = caption
                if expected_process != process:
                    raise ValueError("Visualization does not match recorded trajectories")
        if report.get("process_validation") == "agent_recorded_scene_v1":
            ready = read("comparison/process.json")["status"] == "ready"
            if report["acceptance"]["simulated_world_comparison"] != ready:
                raise ValueError("Visualization availability was misreported")
        if read("comparison/process.json") != read(
            report["rounds"][-1]["artifact_prefix"] + "/process.json"
        ):
            raise ValueError("Final visualization is not the latest completed experiment")
    except (ValueError, KeyError, OSError, TypeError, StopIteration, SyntaxError):
        return ["Repository evidence, measurements, or process provenance failed validation"]
    return []


def load_repository_journal(directory):
    from hacknation_databricks.tracking import Journal, artifact_path, read_artifact

    journal = Journal(directory.name, directory)
    try:

        def read(name):
            return json.loads(read_artifact(directory, name))

        journal.config = RunConfig.model_validate(read("config.json")).model_dump()
        journal.report = read("report.json")
        journal.environment, journal.sources = read("environment.json"), read("sources.json")
        journal.proposals = journal.report.get("proposals", [])
        events = [
            json.loads(line) for line in read_artifact(directory, "events.jsonl").splitlines()
        ]
        states, finished = {}, False
        for event in events:
            kind, data = event["event"], event["data"]
            if kind == "stage_started":
                stage = data["stage"]
                if (
                    finished
                    or stage in states
                    or not re.fullmatch(
                        r"repository|reader|reader_repair|literature|literature_repair|critic|critic_repair|planner|implementation|preflight/\d+/(experiment|repair)|rounds/\d+/(experiment|assessment|decision)",
                        stage,
                    )
                ):
                    raise ValueError("Unknown or repeated stage")
                allowed = (
                    {"completed", "failed"}
                    if stage.startswith("preflight/") and stage.endswith("/repair")
                    else {"completed"}
                )
                if "failed" in allowed and data["parents"] != [
                    stage.rsplit("/", 1)[0] + "/experiment"
                ]:
                    raise ValueError("Repair must follow its failed feasibility check")
                if any(states.get(p) not in allowed for p in data["parents"]):
                    raise ValueError("Handoff precedes its inputs")
                states[stage] = "running"
            elif kind in {"stage_completed", "stage_failed"}:
                if states.get(data["stage"]) != "running":
                    raise ValueError("Stage ended without start")
                states[data["stage"]] = "completed" if kind == "stage_completed" else "failed"
            elif kind == "run_finished":
                if finished or "running" in states.values():
                    raise ValueError("Run ended with active stages")
                finished = True
        if (directory / "manifest.json").is_file():
            journal.sealed = True
            journal.artifacts = read("manifest.json")["artifacts"]
            if not finished:
                raise ValueError("Unfinished sealed run")
            for name, item in journal.artifacts.items():
                path = artifact_path(directory, name)
                if path.stat().st_size != item["bytes"]:
                    raise ValueError("Artifact changed")
                # Preview limits must not quarantine valid larger simulation evidence.
                # Stream integrity checks without allocating each full artifact in memory.
                with path.open("rb") as stream:
                    if hashlib.file_digest(stream, "sha256").hexdigest() != item["sha256"]:
                        raise ValueError("Artifact changed")
            journal.issues.extend(
                verify_repository_outputs(directory, journal.report, journal.artifacts)
            )
    except (ValueError, KeyError, OSError, TypeError):
        journal.issues.append("Repository run failed its artifact or handoff contract")
    return journal
