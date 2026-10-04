"""Verify repository runs and their handoffs without executing archived code."""

import ast
import hashlib
import json
import re

from .agent_visualization import agent_process
from .code_sandbox import SimulationSample, paper_implementation
from .legacy_audit import process_from_trials, validate_process_variation
from .models import RunConfig
from .process_visualization import checked_process
from .repository_models import (
    RepositoryBrief,
    RepositoryLiterature,
    RepositoryPlan,
    RepositoryReview,
)
from .repository_workflow import summarize_trials
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
            review = RepositoryReview.model_validate(read(name))
            for evidence in review.evidence:
                check_evidence(evidence, sources)
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
        plan = RepositoryPlan.model_validate(read("planner.json"))
        if any(test.replicates > min(config.trials, 32) for test in plan.tests):
            raise ValueError("Plan exceeds the paired-replicate budget")
        for row in report["rounds"]:
            prefix = row["artifact_prefix"]
            if prefix != f"rounds/{row['round']:02d}":
                raise ValueError("Invalid result path")
            result = read(prefix + "/trials.json")
            spec = read(prefix + "/specification.json")
            n = next(t.replicates for t in plan.tests if t.id == plan.selected_test_id)
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
    from hacknation_databricks.tracking import Journal, read_artifact

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
                        r"repository|reader|reader_repair|literature|literature_repair|critic|critic_repair|planner|implementation|rounds/\d+/(experiment|decision)",
                        stage,
                    )
                ):
                    raise ValueError("Unknown or repeated stage")
                if any(states.get(p) != "completed" for p in data["parents"]):
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
                raw = read_artifact(directory, name)
                if len(raw) != item["bytes"] or hashlib.sha256(raw).hexdigest() != item["sha256"]:
                    raise ValueError("Artifact changed")
            journal.issues.extend(
                verify_repository_outputs(directory, journal.report, journal.artifacts)
            )
    except (ValueError, KeyError, OSError, TypeError):
        journal.issues.append("Repository run failed its artifact or handoff contract")
    return journal
