"""Read-only, evidence-backed decision ledger for the bounded research workflow.

The journal is a projection of saved engine events, never an alternate way to
approve a gate. Unknown stages, out-of-order events and damaged artifacts fail
closed. Narratives document decisions; they cannot authorize execution.
"""

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from hacknation_databricks.research.models import (
    CritiqueBatch,
    DiscoveryPlan,
    ExperimentPlan,
    LiteratureReview,
    NextDecision,
    ProposalBatch,
    RunConfig,
    ValidationReview,
)
from hacknation_databricks.research.sources import Source, check_evidence
from hacknation_databricks.research.workflow import discovery_transition, novelty_gate

POLICY_VERSION = "decision-ledger-v1"
MAX_ARTIFACT_BYTES = 20 * 1024 * 1024


@dataclass(frozen=True)
class Step:
    key: str
    title: str
    role: str
    choices: tuple[str, ...]
    gate: str
    boundary: str
    implementation: str


STEPS = (
    Step(
        "reader",
        "Read & propose",
        "Reader",
        ("Extract 1–3 directions", "Stop on invalid evidence"),
        "Every direction has a source-local quote and an allowlisted experiment.",
        "At most 3 distinct proposals. Source text cannot issue instructions.",
        "research.models.ProposalBatch · research.sources.check_evidence",
    ),
    Step(
        "critic",
        "Critique",
        "Critic",
        ("Accept", "Reject"),
        "Review each proposal once; the live critic selects an accepted direction.",
        "No new proposal, skipped review, or unreviewed implementation.",
        "research.models.CritiqueBatch · research.workflow.run_research",
    ),
    Step(
        "baseline",
        "Reproduce baseline",
        "Simulator",
        ("Pass checks", "Stop on failure"),
        "Baseline intervals meet the declared tolerance and seed replays pass.",
        "Pinned seed, lattice sizes and thresholds; no model-written code.",
        "research.workflow.baseline_validation · numerical_checks",
    ),
    Step(
        "literature",
        "Review literature",
        "Literature reviewer",
        ("Unverified", "Known overlap", "Candidate gap"),
        "Citations resolve to supplied sources; scope and uncertainty are explicit.",
        "A candidate gap is not verified scientific novelty.",
        "research.models.LiteratureReview · research.sources.check_evidence",
    ),
    Step(
        "planner",
        "Lock implementation",
        "Planner",
        ("Use reviewed experiment", "Stop on mismatch"),
        "The experiment and proposal ID exactly match the accepted proposal.",
        "Only random_manhattan, site_percolation or resistor_diode.",
        "research.models.ExperimentPlan · research.workflow.run_research",
    ),
    Step(
        "experiment",
        "Run experiment",
        "Simulator",
        ("Run fixed recipe", "Stop at budget"),
        "Save trials and summaries; replay seeds and check numerical invariants.",
        "Finite simulations, workers, time and rounds; data stays in its run directory.",
        "research.simulation.simulate · research.workflow.numerical_checks",
    ),
    Step(
        "validation",
        "Validate & decide",
        "Validator",
        ("Supported", "Inconclusive", "Reject"),
        "All recorded evidence criteria must pass to advance an automated candidate.",
        "Only a budgeted repeat of the same proposal is allowed. No discovery claim.",
        "research.models.ValidationReview · research.workflow.novelty_gate",
    ),
)
STEP_BY_KEY = {step.key: step for step in STEPS}


@dataclass
class Decision:
    id: str
    stage: str
    step: str
    round: int
    status: str
    timestamp: str
    choice: str
    rationale: str
    evidence: list[str] = field(default_factory=list)
    facts: dict[str, Any] = field(default_factory=dict)


@dataclass
class Journal:
    run_id: str
    directory: Path
    config: dict = field(default_factory=dict)
    environment: dict = field(default_factory=dict)
    report: dict = field(default_factory=dict)
    sources: list = field(default_factory=list)
    proposals: list = field(default_factory=list)
    decisions: list[Decision] = field(default_factory=list)
    artifacts: dict = field(default_factory=dict)
    issues: list[str] = field(default_factory=list)
    sealed: bool = False

    @property
    def verified(self) -> bool:
        return self.sealed and not self.issues

    def export(self) -> str:
        payload = {
            "policy_version": POLICY_VERSION,
            "run_id": self.run_id,
            "verified": self.verified,
            "sealed": self.sealed,
            "issues": self.issues,
            "backend": self.report.get("backend", "unknown"),
            "config": self.config,
            "policy": [asdict(step) for step in STEPS],
            "decisions": [
                {**asdict(decision), "contract": decision_contract(decision)}
                for decision in self.decisions
            ],
            "artifact_hashes": self.artifacts,
            "note": "Derived from saved artifacts; not an approval or a scientific novelty claim.",
        }
        return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def decision_contract(record: Decision) -> dict:
    """Jev-style closed questions. Missing probabilities stay missing, never fabricated."""
    model_decisions = record.facts.get("model_decisions", [])
    if model_decisions:
        return {
            "state": {d["id"]: d["state"] for d in model_decisions},
            "questions": {
                d["id"]: {"type": "choice", "instructions": d["question"], "criteria": d["choices"]}
                for d in model_decisions
            },
            "answers": {d["id"]: d.get("result", {}).get("answer") for d in model_decisions},
            "probabilities": {
                d["id"]: d.get("result", {}).get("probabilities") for d in model_decisions
            },
            "confidence": None,
            "provenance": "AnyJev L0 model logits, cyclic option rotations, zero generated tokens. "
            "Option weights are uncalibrated; they are not probabilities of truth.",
        }
    questions = {}
    answers = {}
    if record.step == "critic":
        for item in record.facts.get("critiques", []):
            key = item["proposal_id"]
            questions[key] = {
                "type": "choice",
                "instructions": "Is this supplied direction feasible?",
                "criteria": {
                    "accept": "Proceed to baseline checks",
                    "reject": "Do not implement",
                    "defer": "Require more evidence",
                },
            }
            answers[key] = item["decision"]
    else:
        choices, selected = {
            "reader": (
                {"extract": "Extract source-backed directions", "stop": "Invalid evidence"},
                "extract" if record.status == "recorded" else None,
            ),
            "baseline": (
                {"pass": "Baseline consistent", "stop": "Baseline check failed"},
                "pass" if record.status == "recorded" else "stop",
            ),
            "literature": (
                {
                    "unverified": "Insufficient evidence",
                    "known_overlap": "Known prior art",
                    "candidate_gap": "Gap in supplied literature",
                },
                record.facts.get("assessment"),
            ),
            "planner": (
                {
                    record.facts.get(
                        "experiment", "reviewed_experiment"
                    ): "Implement only the reviewed experiment",
                    "stop": "Stop if the plan does not match the reviewed proposal",
                },
                record.facts.get("experiment"),
            ),
            "experiment": (
                {"pass": "Numerical checks passed", "fail": "Numerical checks failed"},
                "pass" if record.facts.get("passed") is True else "fail",
            ),
            "validation": (
                {
                    "supported": "Evidence supports the measurements",
                    "inconclusive": "More evidence needed",
                    "reject": "Unsupported",
                },
                record.facts.get("review", {}).get("decision"),
            ),
        }[record.step]
        questions[record.step] = {
            "type": "choice",
            "instructions": STEP_BY_KEY[record.step].gate,
            "criteria": choices,
        }
        answers[record.step] = selected if record.facts else None
    return {
        "state": {"stage": record.stage, "round": record.round, "evidence": record.evidence},
        "questions": questions,
        "answers": answers,
        "probabilities": None,
        "confidence": None,
        "provenance": "Projected from engine artifacts; no Jev API call or calibrated scores.",
    }


def artifact_path(directory: Path, name: str) -> Path:
    root = directory.resolve()
    path = (root / name).resolve()
    if not path.is_relative_to(root) or path == root:
        raise ValueError("Artifact path leaves the run directory")
    return path


def read_artifact(directory: Path, name: str) -> bytes:
    path = artifact_path(directory, name)
    if path.stat().st_size > MAX_ARTIFACT_BYTES:
        raise ValueError("Artifact exceeds the viewer's 20 MiB limit")
    return path.read_bytes()


def _json(directory: Path, name: str) -> Any:
    return json.loads(read_artifact(directory, name))


def discover_runs(root: Path) -> list[Path]:
    """Only immediate run directories; no arbitrary server paths from UI input."""
    if not root.is_dir():
        return []
    return sorted(
        (
            p
            for p in root.iterdir()
            if p.is_dir() and not p.is_symlink() and (p / "events.jsonl").is_file()
        ),
        key=lambda p: (p.stat().st_mtime_ns, p.name),
        reverse=True,
    )[:100]


def expected_stages(max_rounds: int) -> list[str]:
    return ["reader", "critic", "baseline"] + [
        f"rounds/{index:02d}/{step.key}" for index in range(1, max_rounds + 1) for step in STEPS[3:]
    ]


def validate_trace(events: list[dict], max_rounds: int) -> dict[str, tuple[str, str]]:
    """Replay the finite path. Skipping, reopening and unknown stages are invalid."""
    allowed = expected_stages(max_rounds)
    index = 0
    active = None
    failed = False
    finished = False
    states = {}
    for event in events:
        kind = event["event"]
        if kind == "run_finished":
            if finished or active:
                raise ValueError("Invalid run termination")
            finished = True
            continue
        if not kind.startswith("stage_"):
            continue
        stage = event["data"]["stage"]
        if finished or failed:
            raise ValueError("Stage executed after termination")
        if kind == "stage_started":
            if active or index >= len(allowed) or stage != allowed[index]:
                raise ValueError("Stage does not follow the allowlisted path")
            active = stage
            states[stage] = ("running", event["time"])
        elif kind in {"stage_completed", "stage_failed"}:
            if active != stage:
                raise ValueError("Stage finished without its matching start")
            failed = kind == "stage_failed"
            states[stage] = ("blocked" if failed else "recorded", event["time"])
            active = None
            index += 1
        else:
            raise ValueError("Unknown stage event")
    return states


def _describe(journal: Journal, stage: str, status: str, timestamp: str) -> Decision:
    step = stage.rsplit("/", 1)[-1]
    round_index = int(stage.split("/")[1]) if "/" in stage else 0
    record = Decision(
        f"D-{len(journal.decisions) + 1:03d}",
        stage,
        step,
        round_index,
        status,
        timestamp,
        "Stopped" if status == "blocked" else "In progress",
        STEP_BY_KEY[step].gate,
    )
    if status != "recorded":
        return record
    directory = journal.directory
    prefix = stage.rsplit("/", 1)[0]
    sources = [Source(**{**s, "pages": tuple(s["pages"])}) for s in journal.sources]
    if step == "reader":
        batch = ProposalBatch.model_validate(_json(directory, "proposals.json"))
        for proposal in batch.proposals:
            check_evidence(proposal.evidence, sources[:1])
        journal.proposals = [p.model_dump() for p in batch.proposals]
        record.choice = f"Extracted {len(batch.proposals)} directions"
        record.rationale = (
            "Candidate directions retain exact source passages. "
            "The critic separately checks support before allowing an experiment."
        )
        record.evidence = ["proposals.json", "sources.json"]
        record.facts = {"proposals": journal.proposals}
    elif step == "critic":
        batch = CritiqueBatch.model_validate(_json(directory, "critiques.json"))
        ids = [c.proposal_id for c in batch.critiques]
        if len(ids) != len(set(ids)) or set(ids) != {p["id"] for p in journal.proposals}:
            raise ValueError("Critiques do not cover the proposal set exactly once")
        accepted = [c for c in batch.critiques if c.decision == "accept"]
        record.choice = f"Accepted {len(accepted)} / {len(ids)} directions"
        record.rationale = " ".join(dict.fromkeys(c.rationale for c in batch.critiques))
        record.evidence = ["critiques.json", "proposals.json"]
        record.facts = batch.model_dump()
        if not accepted:
            record.status = "blocked"
    elif step == "baseline":
        result = _json(directory, "baseline/validation.json")
        passed = result.get("passed") is True and result["numerical"].get("passed") is True
        record.choice = "Baseline consistent" if passed else "Baseline gate failed"
        record.status = "recorded" if passed else "blocked"
        record.rationale = result["claim"] + " " + result["limitation"]
        record.evidence = [
            "baseline/validation.json",
            "baseline/trials.csv",
            "baseline/summary.json",
        ]
        record.facts = result
    elif step == "literature":
        result = LiteratureReview.model_validate(_json(directory, f"{prefix}/literature.json"))
        for evidence in result.sources:
            check_evidence(evidence, sources)
        record.choice = result.assessment.replace("_", " ").capitalize()
        record.rationale = result.reasoning
        record.evidence = [f"{prefix}/literature.json", "sources.json"]
        record.facts = result.model_dump()
    elif step == "planner":
        plan_data = _json(directory, f"{prefix}/plan.json")
        contract = DiscoveryPlan if "tests" in plan_data else ExperimentPlan
        result = contract.model_validate(plan_data)
        critique_record = _json(directory, "critiques.json")
        critiques = critique_record["critiques"]
        accepted = {c["proposal_id"] for c in critiques if c["decision"] == "accept"}
        preferred = journal.config.get("preferred_experiment")
        selected = next(
            p
            for p in journal.proposals
            if p["id"] in accepted
            and (preferred is None or p["experiment"] == preferred)
            and (
                (
                    journal.report.get("backend") != "anyjev"
                    and not (
                        journal.report.get("backend") == "omnigent"
                        and journal.report.get("workflow_version") == "3"
                    )
                )
                or p["id"] == critique_record.get("selected_proposal_id")
            )
        )
        if (result.proposal_id, result.experiment) != (selected["id"], selected["experiment"]):
            raise ValueError("Implementation changed the reviewed proposal")
        record.choice = result.experiment.replace("_", " ").capitalize()
        record.rationale = result.rationale
        record.evidence = [f"{prefix}/plan.json", "config.json"]
        record.facts = result.model_dump()
    elif step == "experiment":
        result = _json(directory, f"{prefix}/checks.json")
        passed = result.get("passed") is True and result["numerical"].get("passed") is True
        record.choice = "Numerical checks passed" if passed else "Numerical checks failed"
        record.rationale = (
            f"{result['numerical']['seed_replays']} seeded jobs replayed. "
            "Effect size is evaluated separately from implementation correctness."
        )
        record.evidence = [
            f"{prefix}/checks.json",
            f"{prefix}/trials.csv",
            f"{prefix}/summary.json",
        ]
        record.facts = result
    elif step == "validation":
        result = ValidationReview.model_validate(_json(directory, f"{prefix}/validation.json"))
        gate = _json(directory, f"{prefix}/gate.json")
        criteria = gate["criteria"]
        required = {
            "baseline_consistent",
            "numerical_validation",
            "detectable_effect",
            "independent_review_supports",
            "literature_candidate_gap",
            "multiple_sources_reviewed",
        }
        evaluation = None
        if (directory / prefix / "novelty_review.json").exists():
            from hacknation_databricks.research.models import NoveltyReview

            evaluation = NoveltyReview.model_validate(
                _json(directory, f"{prefix}/novelty_review.json")
            )
            required.add("reference_evaluator_supports")
        if set(criteria) != required or any(type(value) is not bool for value in criteria.values()):
            raise ValueError("Unknown novelty criteria")
        if gate["met"] is not all(criteria.values()):
            raise ValueError("Novelty gate disagrees with its criteria")
        checks = _json(directory, f"{prefix}/checks.json")
        literature = LiteratureReview.model_validate(_json(directory, f"{prefix}/literature.json"))
        expected = novelty_gate(
            _json(directory, "baseline/validation.json"),
            checks["numerical"],
            checks["effect"],
            literature,
            result,
            journal.report.get("backend", "unknown"),
            evaluation,
        )
        if criteria != expected["criteria"] or gate["met"] != expected["met"]:
            raise ValueError("Novelty criteria do not follow the recorded evidence")
        record.choice = "Automated candidate" if gate["met"] else "Novelty gate held"
        record.status = "recorded" if gate["met"] else "review"
        record.rationale = result.reasoning
        record.evidence = [f"{prefix}/validation.json", f"{prefix}/gate.json"]
        record.facts = {"review": result.model_dump(), "gate": gate}
        if (
            journal.report.get("workflow_version") == "3"
            and journal.report.get("backend") == "omnigent"
        ):
            path = f"{prefix}/next_decision.json"
            decision = NextDecision.model_validate(_json(directory, path))
            record.evidence.append(path)
            record.facts["next_decision"] = decision.model_dump()
            record.rationale += " Next action: " + decision.action + ". " + decision.rationale
            recorded_round = next(r for r in journal.report["rounds"] if r["round"] == round_index)
            if recorded_round.get("next_decision") != decision.model_dump():
                raise ValueError("Report next decision disagrees with the specialist artifact")
            transition_path = f"{prefix}/transition.json"
            if (directory / transition_path).is_file():
                transition = _json(directory, transition_path)
                expected_transition = discovery_transition(
                    decision, gate, result, literature, journal.config["max_rounds"] - round_index
                )
                if (
                    transition != expected_transition
                    or recorded_round.get("transition") != transition
                ):
                    raise ValueError("Supervisor transition disagrees with recorded evidence")
                record.evidence.append(transition_path)
    return record


def _attach_model_decisions(journal: Journal, states: dict) -> None:
    from hacknation_databricks.research.artifacts import canonical
    from hacknation_databricks.research.decision_runtime import MODEL_ID, MODEL_REVISION

    paths = sorted((journal.directory / "decisions").glob("*.json"))
    if len(paths) > journal.config["max_decision_calls"]:
        raise ValueError("Decision budget exceeded")
    ids = set()
    for path in paths:
        name = path.relative_to(journal.directory).as_posix()
        item = _json(journal.directory, name)
        identity = (item["stage"], item["id"])
        if identity in ids or item["stage"] not in states or item["backend"] != "anyjev":
            raise ValueError("Invalid model decision stage or identity")
        ids.add(identity)
        choices = item["choices"]
        if not 2 <= len(choices) <= 8:
            raise ValueError("Invalid option catalog")
        request = {k: item[k] for k in ("state", "question", "choices")}
        if hashlib.sha256(canonical(request).encode()).hexdigest() != item["input_sha256"]:
            raise ValueError("Decision input changed")
        result = item.get("result")
        if result:
            weights = result["probabilities"]
            if (
                set(weights) != set(choices)
                or any(type(v) is not float or not 0 <= v <= 1 for v in weights.values())
                or abs(sum(weights.values()) - 1) > 1e-6
                or result["answer"] != max(weights, key=weights.get)
                or result["calibrated"] is not False
                or result["level"] != "L0"
                or result["model"] != MODEL_ID
                or result["revision"] != MODEL_REVISION
                or result["usage"]["generated_tokens"] != 0
                or result["usage"]["prefills"] != len(choices)
            ):
                raise ValueError("Invalid model distribution or provenance")
            values = sorted(weights.values(), reverse=True)
            passed = values[0] - values[1] >= 0.05
            if item["ambiguity_gate"] != {"minimum_margin": 0.05, "passed": passed}:
                raise ValueError("Ambiguity gate changed")
            if not passed and states[item["stage"]][0] == "recorded":
                raise ValueError("Stage continued after an ambiguous choice")
        elif states[item["stage"]][0] == "recorded":
            raise ValueError("Completed stage has no model answer")
        record = next(d for d in journal.decisions if d.stage == item["stage"])
        record.facts.setdefault("model_decisions", []).append(item)
        record.evidence.append(name)
    for record in journal.decisions:
        if (
            record.status in {"recorded", "review"}
            and record.step not in {"baseline", "experiment"}
            and not record.facts.get("model_decisions")
        ):
            raise ValueError("Completed model stage has no inference evidence")
        if states[record.stage][0] != "recorded" or record.step in {"baseline", "experiment"}:
            continue
        decisions = {d["id"]: d for d in record.facts.get("model_decisions", [])}
        if record.step == "reader":
            for proposal in journal.proposals:
                decision = decisions[f"source-{proposal['experiment']}"]
                selected = decision["result"]["answer"]
                if decision["state"]["candidate_passages"].get(selected) != proposal["evidence"]:
                    raise ValueError("Proposal does not follow the model-selected source")
        elif record.step == "critic":
            for critique in record.facts["critiques"]:
                grounding = decisions.get(f"grounding-{critique['proposal_id']}")
                answer = grounding["result"]["answer"] if grounding else "supported"
                if answer == "supported":
                    decision = decisions[f"critique-{critique['proposal_id']}"]
                    expected = decision["result"]["answer"]
                else:
                    expected = "reject" if answer == "topic_only" else "defer"
                if expected != critique["decision"]:
                    raise ValueError("Critique changed the model decision")
            selected = record.facts.get("selected_proposal_id")
            choice = decisions.get("select-direction", {}).get("result", {}).get("answer")
            if (choice if choice != "stop" else None) != selected:
                raise ValueError("Selected direction changed the model decision")
        elif record.step == "literature":
            if decisions["literature-assessment"]["result"]["answer"] != record.facts["assessment"]:
                raise ValueError("Literature assessment changed the model decision")
        elif record.step == "planner":
            if decisions["authorize-experiment"]["result"]["answer"] != "execute":
                raise ValueError("Experiment ran without model authorization")
        elif record.step == "validation":
            if (
                decisions["validate-measurements"]["result"]["answer"]
                != record.facts["review"]["decision"]
            ):
                raise ValueError("Validation changed the model decision")


def load_journal(directory: Path) -> Journal:
    if (directory / "report.json").is_file():
        try:
            if _json(directory, "report.json").get("workflow_version") == "5":
                from hacknation_databricks.research.repository_audit import load_repository_journal

                return load_repository_journal(directory)
            if _json(directory, "report.json").get("workflow_version") == "4":
                from hacknation_databricks.research.adaptive_audit import load_adaptive_journal

                return load_adaptive_journal(directory)
        except (ValueError, OSError):
            pass
    journal = Journal(directory.name, directory)
    try:
        journal.config = RunConfig.model_validate(_json(directory, "config.json")).model_dump()
        journal.environment = _json(directory, "environment.json")
        journal.sources = _json(directory, "sources.json")
        if (directory / "report.json").exists():
            journal.report = _json(directory, "report.json")
            if journal.report.get("backend") not in {"anyjev", "scripted", "omnigent", "fixture"}:
                raise ValueError("Unknown decision backend")
            for count, limit in (
                ("role_calls", "max_agent_calls"),
                ("decision_calls", "max_decision_calls"),
                ("computed_simulations", "max_simulations"),
            ):
                value = journal.report.get(count, 0)
                if type(value) is not int or not 0 <= value <= journal.config[limit]:
                    raise ValueError("Run exceeded its declared budget")
        events = [
            json.loads(line)
            for line in read_artifact(directory, "events.jsonl").splitlines()
            if line.strip()
        ]
        if len(events) > 1024:
            raise ValueError("Event budget exceeds the bounded workflow")
        states = validate_trace(events, journal.config["max_rounds"])
        for stage, (status, timestamp) in states.items():
            journal.decisions.append(_describe(journal, stage, status, timestamp))
        if journal.report.get("backend") == "anyjev":
            _attach_model_decisions(journal, states)
        # A blocked precondition must never be followed by another stage.
        for record in journal.decisions[:-1]:
            if record.status == "blocked":
                raise ValueError("Execution continued past a failed gate")
            if record.step == "validation":
                literature = next(
                    d
                    for d in journal.decisions
                    if d.step == "literature" and d.round == record.round
                )
                if (
                    record.facts.get("next_decision", {}).get("action", "repeat") != "repeat"
                    or record.facts["gate"]["met"]
                    or record.facts["review"]["decision"] == "reject"
                    or literature.facts["assessment"] != "candidate_gap"
                    or journal.report.get("backend") not in {"anyjev", "omnigent"}
                    or (
                        journal.report.get("workflow_version") in {"2", "3"}
                        and len({e["source_id"] for e in literature.facts["sources"]}) < 2
                    )
                ):
                    raise ValueError("No authorized route into another round")
        if (directory / "manifest.json").exists():
            journal.artifacts = _json(directory, "manifest.json")["artifacts"]
            if len(journal.artifacts) > 1024 or not any(
                e["event"] == "run_finished" for e in events
            ):
                raise ValueError("Manifest is unbounded or run has not finished")
            journal.sealed = True
            required_files = {
                "config.json",
                "environment.json",
                "sources.json",
                "events.jsonl",
                "report.json",
            }
            required_files.update(name for d in journal.decisions for name in d.evidence)
            if not required_files.issubset(journal.artifacts):
                raise ValueError("Manifest omits decision evidence")
            for name, item in journal.artifacts.items():
                raw = read_artifact(directory, name)
                if hashlib.sha256(raw).hexdigest() != item["sha256"] or len(raw) != item["bytes"]:
                    journal.issues.append(f"Artifact changed: {name}")
            if not journal.issues:
                from .research.process_visualization import verify_process_outputs

                journal.issues.extend(
                    verify_process_outputs(directory, journal.report, journal.artifacts)
                )
    except (OSError, ValueError, KeyError, TypeError, AttributeError, StopIteration):
        # Malformed data and provider responses must not leak into UI error bodies.
        journal.issues.append(
            "Run data failed its contract, evidence, or ordered-transition check."
        )
    return journal
