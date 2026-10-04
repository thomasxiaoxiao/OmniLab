import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from legacy.adaptive import run_adaptive
from legacy.adaptive_experiments import (
    ASTROSAT_RECIPES,
    astrosat_baseline,
    seed_for,
    transit_batch,
)

from hacknation_databricks.research.adaptive_audit import validate_parallel_trace
from hacknation_databricks.research.agents import OmnigentRoles, RoleBackend
from hacknation_databricks.research.artifacts import RunStore, verify_artifacts
from hacknation_databricks.research.models import Contract, RunConfig
from hacknation_databricks.research.sources import read_source
from hacknation_databricks.tracking import load_journal


class AdaptiveFixture(RoleBackend):
    def ask(self, role, payload, contract):
        with self._call_lock:
            self.calls += 1
        if role in {"researcher", "implementation_mapper", "paper_reader"}:
            source = payload["source"]
            result = {
                "directions": [
                    {
                        "id": f"margin_{k}",
                        "title": f"Test margin {k}",
                        "hypothesis": "A wider guard reduces the missed transit rate.",
                        "experiment": f"transit_margin_{k}",
                        "origin": "agent_hypothesis",
                        "evidence": [
                            {
                                "source_id": source["source_id"],
                                "page": 1,
                                "quote": source["pages"][0],
                            }
                        ],
                    }
                    for k in (1, 2, 3)
                ],
                "search_scope": "Read the full supplied fixture source",
                "missing_evidence": [],
            }
            if role == "paper_reader":
                assert "experiment_catalog" not in payload
                assert "measurement_contract" not in payload
                assert "domain" not in payload
                result.update(
                    research_question="How does uncertainty affect transit detection?",
                    summary="The source motivates checking uncertainty in transit detection.",
                )
                for direction in result["directions"]:
                    direction.pop("experiment")
        elif role == "consolidator":
            result = {
                "critiques": [
                    {
                        "proposal_id": c["id"],
                        "decision": "accept",
                        "rationale": "Testable uncertainty sensitivity comparison",
                        "risks": ["Synthetic inputs"],
                    }
                    for c in payload["candidates"]
                ],
                "invest": [c["id"] for c in payload["candidates"][:3]],
                "rationale": "Compare three competing uncertainty guards",
            }
        elif role == "branch_planner":
            time.sleep(0.015)
            result = {
                "branch_id": payload["branch_id"],
                "experiment": payload["branch"]["experiment"],
                "tests": [
                    {
                        "test_id": t,
                        "expected_learning": "Measure the uncertainty tradeoff",
                        "feasibility": "The budget supports this seeded batch",
                    }
                    for t in ("screen", "precision")
                ],
                "selected_test_id": "screen",
                "rationale": "Preserve budget for later batches",
            }
        elif role == "decision_agent":
            latest = payload["latest_result"]
            eligible = [k for k, v in payload["branches"].items() if v["goal_eligible"]]
            result = {
                "action": "finalize" if eligible else "invest",
                "invest": ["b1_2"],
                "goal_branch_id": eligible[0] if eligible else None,
                "result_interpretation": f"Observed {len(latest['checks'])} scenario results",
                "rationale": "Concentrate on the middle guard after screening",
                "next_experiment": "Increase sample precision for the middle guard",
                "missing_evidence": ["No real TLE observations"],
            }
        else:
            result = {
                "decision": "supported",
                "reasoning": "Supports the scoped synthetic result",
                "limitations": ["Not a real satellite forecast"],
            }
        return contract.model_validate(result)


def make_run(tmp_path, **kwargs):
    paper = tmp_path / "paper.txt"
    paper.write_text("Expand the field of view to account for cross-track uncertainty.")
    return run_adaptive(
        read_source(paper),
        tmp_path / "run",
        RunConfig(
            workflow="adaptive",
            domain="astrosat",
            trials=128,
            max_rounds=6,
            max_workers=6,
            max_seconds=60,
            max_simulations=100000,
            **kwargs,
        ),
        backend="fixture",
        roles_factory=AdaptiveFixture,
    )


def test_adaptive_reallocation_replay_and_artifact_audit(tmp_path):
    report = make_run(tmp_path)
    assert report["status"] == "goal_achieved"
    assert len(report["branches"]) == 3
    assert report["branches"]["b1_2"]["batches"] > 1
    assert len(report["checkpoints"]) >= 3
    assert report["checkpoints"][0]["pending_branches"]
    assert not report["acceptance"]["live_agents_executed"]
    assert report["computed_simulations"] > sum(b["samples"] for b in report["branches"].values())
    assert not verify_artifacts(tmp_path / "run")
    journal = load_journal(tmp_path / "run")
    assert journal.verified, journal.issues


def test_seed_streams_independent_and_replayable():
    assert len({seed_for(1, b, n) for b in ("a", "b") for n in range(5)}) == 10
    recipe = ASTROSAT_RECIPES["transit_margin_2"]
    rows = transit_batch(recipe, 200, 4, lambda: None)
    assert rows == transit_batch(recipe, 200, 4, lambda: None)
    assert all(not r["control_alert"] or r["treatment_alert"] for r in rows)
    assert {r["scenario"] for r in rows} == {"fresh", "stale"}
    assert astrosat_baseline()["passed"]


def test_decision_cannot_inflate_another_branch_before_its_result(tmp_path):
    report = make_run(tmp_path)
    assert report["status"] == "goal_achieved"
    directory = tmp_path / "run"
    (directory / "manifest.json").unlink()
    path = directory / "checkpoints/001/input.json"
    payload = json.loads(path.read_text())
    pending = payload["in_flight"][0]
    payload["branches"][pending]["batches"] = 1
    payload["branches"][pending]["goal_eligible"] = True
    path.write_text(json.dumps(payload))
    assert not load_journal(directory).verified


def test_parallel_trace_rejects_future_handoff():
    with pytest.raises(ValueError, match="incomplete"):
        validate_parallel_trace(
            [
                {
                    "event": "stage_started",
                    "time": "now",
                    "data": {"stage": "baseline", "parents": ["consolidation"]},
                }
            ]
        )


def test_call_ids_and_stage_context_are_thread_local(tmp_path, monkeypatch):
    class Reply(Contract):
        answer: str

    roles = OmnigentRoles([], RunStore(tmp_path / "run"), RunConfig(max_workers=8))
    barrier = threading.Barrier(8)

    async def request(role, prompt):
        barrier.wait(timeout=5)
        return '{"answer":"ok"}', {"session_id": str(roles._call_context.number), "usage": None}

    monkeypatch.setattr(roles, "_request", request)

    def one(i):
        with roles.store.stage(f"parallel-{i}"):
            return roles.ask("reader", {}, Reply)

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(one, range(8)))
    responses = list((tmp_path / "run/roles").glob("*-response.json"))
    assert len(responses) == 8
    events = [json.loads(line) for line in (tmp_path / "run/events.jsonl").read_text().splitlines()]
    completed = [e["data"] for e in events if e["event"] == "agent_call_completed"]
    assert len({e["stage"] for e in completed}) == 8
    assert len({e["call_id"] for e in completed}) == 8
    assert all(
        int(e["call_id"].split("/")[1].split("-")[0]) == int(e["session_id"]) for e in completed
    )


def test_unmet_goal_does_not_become_success_at_budget(tmp_path):
    paper = tmp_path / "paper.txt"
    paper.write_text("Expand the field of view to account for cross-track uncertainty.")
    report = run_adaptive(
        read_source(paper),
        tmp_path / "run",
        RunConfig(
            workflow="adaptive",
            domain="astrosat",
            trials=8,
            max_rounds=2,
            max_workers=3,
            max_seconds=60,
            max_simulations=10000,
        ),
        backend="fixture",
        roles_factory=AdaptiveFixture,
    )
    assert report["status"] == "round_budget_exhausted"
    assert not report["goal"]["achieved"]
    experiments = list((tmp_path / "run/branches").glob("*/batches/*/trials.csv"))
    assert len(experiments) == len(report["checkpoints"])
    assert not verify_artifacts(tmp_path / "run")


def test_agent_cannot_finalize_an_ineligible_result(tmp_path):
    class Premature(AdaptiveFixture):
        def ask(self, role, payload, contract):
            result = super().ask(role, payload, contract)
            if role == "decision_agent":
                return result.model_copy(update={"action": "finalize", "goal_branch_id": "b1_2"})
            return result

    paper = tmp_path / "paper.txt"
    paper.write_text("Expand the field of view to account for cross-track uncertainty.")
    report = run_adaptive(
        read_source(paper),
        tmp_path / "run",
        RunConfig(workflow="adaptive", domain="astrosat", trials=8, max_rounds=2, max_seconds=60),
        backend="fixture",
        roles_factory=Premature,
    )
    assert not report["goal"]["achieved"]
    assert all(c.get("finalization_blocked") for c in report["checkpoints"])


def test_simulation_budget_never_oversubscribed(tmp_path):
    paper = tmp_path / "paper.txt"
    paper.write_text("Expand the field of view to account for cross-track uncertainty.")
    report = run_adaptive(
        read_source(paper),
        tmp_path / "run",
        RunConfig(
            workflow="adaptive", domain="astrosat", trials=128, max_simulations=1100, max_seconds=60
        ),
        backend="fixture",
        roles_factory=AdaptiveFixture,
    )
    assert report["status"] == "budget_exhausted"
    assert report["computed_simulations"] <= 1100
    assert not report["goal"]["achieved"]


def test_project_deadline_stops_live_work_but_preserves_offline_fixtures(tmp_path, monkeypatch):
    monkeypatch.setattr("legacy.adaptive.PROJECT_DEADLINE", 0)
    paper = tmp_path / "paper.txt"
    paper.write_text("Expand the field of view to account for cross-track uncertainty.")
    report = run_adaptive(read_source(paper), tmp_path / "late", RunConfig())
    assert report["status"] == "budget_exhausted"
    assert report["role_calls"] == report["computed_simulations"] == 0
    assert not verify_artifacts(tmp_path / "late")
    assert make_run(tmp_path)["status"] == "goal_achieved"


def test_partial_parallel_ui_shows_goal_and_branch_handoffs(tmp_path, monkeypatch):
    from view_test import ViewTest

    from hacknation_databricks.research.activity import activity_svg, load_activity

    report = make_run(tmp_path)
    assert len(report["checkpoints"]) == sum(b["batches"] for b in report["branches"].values())
    journal = load_journal(tmp_path / "run")
    nodes = load_activity(journal)
    assert any(n.parents == ["baseline"] for n in nodes if n.role in {"branch_planner", "planner"})
    assert "Evidence → specialist handoffs" in activity_svg(nodes)

    def preview(directory):
        from pathlib import Path

        from hacknation_databricks.discovery_ui import render_discovery
        from hacknation_databricks.tracking import load_journal

        render_discovery(load_journal(Path(directory)))

    app = ViewTest.from_function(preview, args=(str(tmp_path / "run"),)).run(timeout=15)
    assert not app.exception and not app.error
    assert any(m.label == "Goal" and m.value == "Achieved" for m in app.metric)
    assert RunConfig().max_workers == 6
    assert RunConfig().max_rounds == 8


def test_interrupted_simulation_exposes_all_completed_trials():
    observed = []

    def consume():
        if len(observed) == 7:
            raise TimeoutError("Test interruption")

    with pytest.raises(TimeoutError):
        transit_batch(ASTROSAT_RECIPES["transit_margin_1"], 30, 8, consume, observed.append)
    assert len(observed) == 7
    assert observed == transit_batch(ASTROSAT_RECIPES["transit_margin_1"], 30, 8, lambda: None)[:7]


def test_runtime_retry_records_both_attempts_and_sessions(tmp_path, monkeypatch):
    from hacknation_databricks.research.activity import activity_svg, parallel_activity
    from hacknation_databricks.research.agents import AgentUnavailable
    from hacknation_databricks.tracking import Journal

    class Reply(Contract):
        answer: str

    store = RunStore(tmp_path / "run")
    roles = OmnigentRoles([], store, RunConfig(max_agent_calls=2, max_agent_retries=1))

    async def request(role, prompt):
        store.event("agent_session_created", {"session_id": f"fixture-{roles.calls}", "role": role})
        if roles.calls == 1:
            raise AgentUnavailable("Test runtime failure")
        return '{"answer":"ok"}', {"session_id": "fixture-2", "usage": None}

    monkeypatch.setattr(roles, "_request", request)
    with store.stage("sources/seed/researcher", parents=[]):
        roles.ask("researcher", {}, Reply)
    events = [
        json.loads(line) for line in (store.directory / "events.jsonl").read_text().splitlines()
    ]
    nodes = parallel_activity(
        Journal("run", store.directory, report={"backend": "fixture"}), events
    )
    assert [n.status for n in nodes] == ["failed", "completed"]
    assert [n.session_id for n in nodes] == ["fixture-1", "fixture-2"]
    assert len({n.key for n in nodes}) == 2
    assert "failed" in activity_svg(nodes)
    assert roles.calls == 2


def test_validator_gets_replay_evidence_and_objections_return_to_decision(tmp_path):
    reviews, feedback = [], []

    class RevisingFixture(AdaptiveFixture):
        def ask(self, role, payload, contract):
            result = super().ask(role, payload, contract)
            if role == "validator":
                reviews.append(json.loads(json.dumps(payload)))
                if len(reviews) == 1:
                    return result.model_copy(
                        update={"decision": "inconclusive", "reasoning": "Gather another batch"}
                    )
            if role == "decision_agent" and payload["previous_validation"]:
                feedback.append(payload["previous_validation"])
            return result

    paper = tmp_path / "paper.txt"
    paper.write_text("Expand the field of view to account for cross-track uncertainty.")
    report = run_adaptive(
        read_source(paper),
        tmp_path / "run",
        RunConfig(workflow="adaptive", domain="astrosat", trials=128, max_seconds=60),
        backend="fixture",
        roles_factory=RevisingFixture,
    )
    assert report["status"] == "goal_achieved"
    assert feedback[0]["decision"] == "inconclusive"
    assert len(reviews) >= 2
    versions = [(r["proposal"]["id"], r["measurements"]["batches"]) for r in reviews]
    assert len(set(versions)) == len(versions)
    for review in reviews:
        assert review["recipe"] and review["sufficient_statistics"]
        code = "\n".join(review["implementation"].values())
        assert "def transit_batch" in code
        assert "def simulate" not in code
        assert "percolation" not in code
        assert "simulation_primitives" not in review
        assert len(review["batch_artifacts"]) == review["measurements"]["batches"]
        for artifact in review["batch_artifacts"]:
            assert artifact["replay_checks"]
            assert (tmp_path / "run" / artifact["raw_trials"]).is_file()
    journal = load_journal(tmp_path / "run")
    assert journal.verified, journal.issues


@pytest.mark.parametrize("domain", ["astrosat", "unsupported"])
def test_paper_context_routes_tools_or_stops_without_simulation(tmp_path, domain):
    class ContextFixture(AdaptiveFixture):
        def ask(self, role, payload, contract):
            if role == "research_context":
                assert set(payload) == {"source", "paper_brief"}
                assert payload["paper_brief"]["directions"]
                self.calls += 1
                return contract.model_validate(
                    {
                        "research_question": "How does uncertainty affect transit detection?",
                        "summary": "The paper studies uncertain transit predictions.",
                        "domain": domain,
                        "rationale": "The tools support an uncertainty sensitivity check.",
                        "evidence": [
                            {"source_id": "seed", "page": 1, "quote": payload["source"]["pages"][0]}
                        ],
                    }
                )
            if role == "implementation_mapper":
                assert payload["research_context"]["domain"] == domain
                assert payload["seed_question"].startswith("How does")
            return super().ask(role, payload, contract)

    paper = tmp_path / "unrelated-filename.txt"
    paper.write_text("Expand the field of view to account for cross-track uncertainty.")
    directory = tmp_path / "run"
    report = run_adaptive(
        read_source(paper),
        directory,
        RunConfig(workflow="adaptive", domain="auto", trials=32, max_rounds=2, max_seconds=60),
        backend="fixture",
        roles_factory=ContextFixture,
    )
    assert (directory / "research_context.json").exists()
    assert not verify_artifacts(directory)
    if domain == "unsupported":
        assert report["status"] == "unsupported_source"
        assert report["computed_simulations"] == 0
        assert not (directory / "experiment_catalog.json").exists()
    else:
        assert report["domain"] == "astrosat"
        assert report["computed_simulations"] > 0
        assert json.loads((directory / "config.json").read_text())["domain"] == "astrosat"
        assert load_journal(directory).verified


def test_invented_context_evidence_stops_before_research_and_simulation(tmp_path):
    class InvalidContext(AdaptiveFixture):
        def ask(self, role, payload, contract):
            if role == "paper_reader":
                return super().ask(role, payload, contract)
            assert role == "research_context"
            self.calls += 1
            return contract.model_validate(
                {
                    "research_question": "What mechanism does the paper investigate?",
                    "summary": "An unsupported claim about the paper.",
                    "domain": "percolation",
                    "rationale": "An invented quotation must not authorize any experiments.",
                    "evidence": [
                        {
                            "source_id": "seed",
                            "page": 1,
                            "quote": "This quotation is not in the supplied source.",
                        }
                    ],
                }
            )

    paper = tmp_path / "paper.txt"
    paper.write_text("A source with no matching evidence for the proposed context.")
    directory = tmp_path / "run"
    with pytest.raises(ValueError):
        run_adaptive(
            read_source(paper),
            directory,
            RunConfig(workflow="adaptive", domain="auto"),
            backend="fixture",
            roles_factory=InvalidContext,
        )
    report = json.loads((directory / "report.json").read_text())
    assert report["status"] == "failed"
    assert report["computed_simulations"] == 0
    assert report["role_calls"] == 2
    assert not (directory / "candidates.json").exists()
    assert not verify_artifacts(directory)
