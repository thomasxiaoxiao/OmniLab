"""Validate the parallel handoff DAG and expose it to the existing artifact viewer."""

import csv
import hashlib
import json
import re
from pathlib import Path

from .adaptive_experiments import summarize_branch
from .models import (
    InvestmentDecision,
    PaperBrief,
    PortfolioSelection,
    ResearchContext,
    ResearchDirection,
    RunConfig,
)
from .sources import Source, check_evidence


def validate_parallel_trace(events):
    states = {}
    finished = False
    for event in events:
        kind, data = event["event"], event["data"]
        if kind == "run_finished":
            if finished or any(s[0] == "running" for s in states.values()):
                raise ValueError("Run ended with active stages")
            finished = True
        elif kind == "stage_started":
            name = data["stage"]
            if finished or name in states:
                raise ValueError("Stage reused or started after termination")
            if not re.fullmatch(
                r"sources/seed/context|sources/[a-zA-Z0-9_-]+/"
                r"(paper_reader|researcher|repair_researcher)|consolidation|baseline|"
                r"branches/b\d+_\d+/batches/\d+/[a-z_]+|checkpoints/\d+/(decision|validation)",
                name,
            ):
                raise ValueError("Unknown parallel stage")
            if any(p not in states or states[p][0] != "recorded" for p in data["parents"]):
                raise ValueError("Handoff references an incomplete dependency")
            states[name] = ("running", event["time"])
        elif kind in {"stage_completed", "stage_failed"}:
            name = data["stage"]
            if name not in states or states[name][0] != "running":
                raise ValueError("Stage completion without matching start")
            states[name] = ("recorded" if kind == "stage_completed" else "blocked", event["time"])
    return states


def trial_rows(path: Path):
    rows = list(csv.DictReader(path.open()))
    boolean_fields = {"wrap_x", "wrap_y", "wrap_both", "truth", "control_alert", "treatment_alert"}
    integer_fields = {"size", "trial", "seed", "largest", "occupied_sites"}
    float_fields = {
        "p",
        "largest_fraction",
        "nominal_y_deg",
        "nominal_time_s",
        "true_y_deg",
        "true_time_s",
    }
    for row in rows:
        for key, value in row.items():
            if key in boolean_fields:
                if value not in {"True", "False"}:
                    raise ValueError("Invalid trial boolean")
                row[key] = value == "True"
            elif key in integer_fields:
                row[key] = int(value)
            elif key in float_fields:
                row[key] = float(value)
    return rows


def load_adaptive_journal(directory):
    from hacknation_databricks.tracking import Decision, Journal, read_artifact

    journal = Journal(directory.name, directory)

    def read(name):
        return json.loads(read_artifact(directory, name))

    try:
        config = RunConfig.model_validate(read("config.json"))
        journal.config, journal.report = config.model_dump(), read("report.json")
        journal.sources, journal.environment = read("sources.json"), read("environment.json")
        sources = [Source(**{**s, "pages": tuple(s["pages"])}) for s in journal.sources]
        report = journal.report
        for count, limit in (
            ("role_calls", config.max_agent_calls),
            ("decision_calls", config.max_decision_calls),
            ("computed_simulations", config.max_simulations),
        ):
            if not isinstance(report.get(count, 0), int) or not 0 <= report.get(count, 0) <= limit:
                raise ValueError("Declared budget exceeded")
        events = [
            json.loads(line) for line in read_artifact(directory, "events.jsonl").splitlines()
        ]
        if len(events) > 20000:
            raise ValueError("Event limit exceeded")
        states = validate_parallel_trace(events)
        if (directory / "paper_briefs.json").exists():
            briefs = read("paper_briefs.json")
            for source_id, raw in briefs.items():
                brief = PaperBrief.model_validate(raw)
                for direction in brief.directions:
                    for evidence in direction.evidence:
                        check_evidence(evidence, [s for s in sources if s.source_id == source_id])
            if (directory / "research_briefs.json").exists():
                for source_id, mapped in read("research_briefs.json").items():
                    original = {d["id"]: d for d in briefs[source_id]["directions"]}
                    for direction in mapped["directions"]:
                        if {
                            k: v for k, v in direction.items() if k != "experiment"
                        } != original.get(direction["id"]):
                            raise ValueError("Implementation changed a paper-first direction")
        if (directory / "implementation.json").exists():
            implementation = read("implementation.json")
            seed = next(s for s in sources if s.source_id == "seed")
            if (
                implementation["source_sha256"] != seed.sha256
                or implementation["domain"] != config.domain
            ):
                raise ValueError("Implementation belongs to a different source or context")
        if (directory / "research_context.json").exists():
            context = ResearchContext.model_validate(read("research_context.json"))
            for evidence in context.evidence:
                check_evidence(evidence, [s for s in sources if s.source_id == "seed"])
            if context.domain != "unsupported" and config.domain != context.domain:
                raise ValueError("Experiment domain differs from the paper-derived context")
            if context.domain == "unsupported" and report.get("computed_simulations", 0):
                raise ValueError("Unsupported paper executed simulations")
        if (directory / "candidates.json").exists():
            candidates = read("candidates.json")
            for item in candidates:
                direction = ResearchDirection.model_validate(
                    {k: v for k, v in item.items() if k != "source_id"}
                )
                for evidence in direction.evidence:
                    check_evidence(evidence, sources)
        if (directory / "consolidation.json").exists():
            selection = PortfolioSelection.model_validate(read("consolidation.json"))
            accepted = {c.proposal_id for c in selection.critiques if c.decision == "accept"}
            if not set(selection.invest) <= accepted or len(set(selection.invest)) != len(
                selection.invest
            ):
                raise ValueError("Invalid investments")
            journal.proposals = report.get("proposals", [])
            if {p["id"] for p in journal.proposals} != set(selection.invest):
                raise ValueError("Unapproved portfolio branch")
        recomputed = {}
        for key, branch in report.get("branches", {}).items():
            rows = []
            paths = sorted((directory / "branches" / key / "batches").glob("*/cumulative.json"))
            # A running worker can atomically publish its next result while this
            # viewer is reading an earlier report snapshot.
            paths = [path for path in paths if int(path.parent.name) <= branch["batches"]]
            for path in paths:
                rows.extend(trial_rows(path.with_name("trials.csv")))
                number = int(path.parent.name)
                measured = summarize_branch(config.domain, rows, config, number)
                if measured != read(path.relative_to(directory).as_posix()):
                    raise ValueError("Cumulative result disagrees with raw trials")
                recomputed[(key, number)] = measured
            if paths and any(branch.get(k) != v for k, v in measured.items()):
                raise ValueError("Report disagrees with branch measurements")
        observed_batches = {key: 0 for key in report.get("branches", {})}
        for item in report.get("checkpoints", []):
            prefix = f"checkpoints/{item['checkpoint']:03d}"
            decision = InvestmentDecision.model_validate(read(f"{prefix}/decision.json"))
            transition_path = f"{prefix}/transition.json"
            partial_validation_failure = (
                not (directory / transition_path).exists()
                and states.get(f"{prefix}/validation", (None,))[0] == "blocked"
                and not item["goal_accepted"]
            )
            if decision.model_dump() != item["decision"] or (
                not partial_validation_failure and read(transition_path) != item
            ):
                raise ValueError("Decision changed after execution")
            payload = read(f"{prefix}/input.json")
            if config.decision_backend == "anyjev" and report["backend"] == "omnigent":
                from .hybrid_roles import verify_investment_handoff

                handoff = read(f"{prefix}/anyjev-handoff.json")
                verify_investment_handoff(
                    payload, decision.model_dump(), handoff, read(handoff["decision_artifact"])
                )
            expected = {
                "branch_id": item["branch_id"],
                **recomputed[(item["branch_id"], item["batch"])],
            }
            if payload["latest_result"] != expected:
                raise ValueError("Decision did not consume the recorded result")
            observed_batches[item["branch_id"]] += 1
            if set(payload["branches"]) != set(observed_batches):
                raise ValueError("Decision omitted a portfolio branch")
            for branch_key, snapshot in payload["branches"].items():
                number = observed_batches[branch_key]
                if snapshot["batches"] != number:
                    raise ValueError("Decision consumed an unavailable batch")
                if number and any(
                    snapshot.get(k) != v for k, v in recomputed[(branch_key, number)].items()
                ):
                    raise ValueError("Decision snapshot disagrees with raw measurements")
            if not set(decision.invest) <= set(report["branches"]):
                raise ValueError("Decision invested outside the portfolio")
            if item["goal_accepted"]:
                key = decision.goal_branch_id
                if (
                    not payload["branches"][key]["goal_eligible"]
                    or read(f"{prefix}/validation.json")["decision"] != "supported"
                ):
                    raise ValueError("Goal finalized without evidence and validation")
            journal.decisions.append(
                Decision(
                    f"D-{item['checkpoint']:03d}",
                    f"{prefix}/decision",
                    "validation",
                    item["batch"],
                    "recorded",
                    "",
                    decision.action,
                    decision.rationale,
                    [
                        f"{prefix}/decision.json",
                        f"{prefix}/input.json",
                    ]
                    + ([transition_path] if not partial_validation_failure else []),
                    {
                        "investment": decision.model_dump(),
                        "partial_result": payload["latest_result"],
                    },
                )
            )
        expected_goal = any(c["goal_accepted"] for c in report["checkpoints"])
        if "output_contract" in report:
            expected_goal &= report["output_contract"]["passed"]
        if report["goal"]["achieved"] != expected_goal:
            raise ValueError("False goal completion")
        if (directory / "manifest.json").exists():
            journal.artifacts = read("manifest.json")["artifacts"]
            journal.sealed = True
            required = {"config.json", "report.json", "sources.json", "events.jsonl", "goal.json"}
            required.update(e["data"]["path"] for e in events if e["event"] == "artifact_written")
            if not required <= set(journal.artifacts) or not any(
                e["event"] == "run_finished" for e in events
            ):
                raise ValueError("Manifest missing recorded evidence or termination")
            for name, item in journal.artifacts.items():
                raw = read_artifact(directory, name)
                if len(raw) != item["bytes"] or hashlib.sha256(raw).hexdigest() != item["sha256"]:
                    journal.issues.append(f"Artifact changed: {name}")
            if not journal.issues:
                from .process_visualization import verify_process_outputs

                journal.issues.extend(verify_process_outputs(directory, report, journal.artifacts))
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        journal.issues.append("Parallel run failed contract, evidence or handoff verification.")
    return journal
