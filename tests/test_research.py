import json
from pathlib import Path

import pytest
from fixture_roles import FixtureRoles as FixtureRoles
from fixture_roles import run_fixture as run_research
from pydantic import ValidationError

from hacknation_databricks.research.artifacts import verify_artifacts
from hacknation_databricks.research.cli import fixture_source as default_source
from hacknation_databricks.research.cli import main
from hacknation_databricks.research.models import Evidence, ProposalBatch, RunConfig
from hacknation_databricks.research.sources import check_evidence, read_source


@pytest.fixture
def source():
    return read_source(default_source())


@pytest.fixture
def config():
    return RunConfig(sizes=[8, 16], trials=32, max_seconds=60)


def test_run_is_reproducible_audited_and_honest(tmp_path, source, config):
    cache = tmp_path / "cache"
    a = run_research(source, tmp_path / "a", config, cache=cache)
    b = run_research(source, tmp_path / "b", config, cache=cache)
    assert a["status"] == b["status"] == "needs_literature_review"
    assert a["acceptance"]["baseline_simulations"]
    assert a["acceptance"]["followup_implemented"]
    assert not a["acceptance"]["live_agents_executed"]
    assert a["scientific_novelty"] == "unverified"
    assert b["cache_hits"] == 8
    for name in ["baseline/trials.csv", "rounds/01/trials.csv", "proposals.json"]:
        assert (tmp_path / "a" / name).read_bytes() == (tmp_path / "b" / name).read_bytes()
    assert not verify_artifacts(tmp_path / "a")
    events = [json.loads(line) for line in (tmp_path / "a/events.jsonl").read_text().splitlines()]
    stages = [e["data"]["stage"] for e in events if e["event"] == "stage_started"]
    assert stages == [
        "reader",
        "critic",
        "baseline",
        "rounds/01/literature",
        "rounds/01/planner",
        "rounds/01/experiment",
        "rounds/01/validation",
    ]
    with pytest.raises(ValueError, match="not empty"):
        run_research(source, tmp_path / "a", config)
    (tmp_path / "a/proposals.json").write_text("tampered")
    assert verify_artifacts(tmp_path / "a") == ["Hash mismatch: proposals.json"]


def test_fabricated_quote_rejected_before_experiments(tmp_path, source, config):
    class Fabricator(FixtureRoles):
        def _respond(self, role, payload):
            result = super()._respond(role, payload)
            if role == "reader":
                result["proposals"][0]["evidence"]["quote"] = "a fabricated source quotation"
            return result

    with pytest.raises(ValueError, match="Untraceable"):
        run_research(source, tmp_path / "run", config, roles_factory=Fabricator)
    report = json.loads((tmp_path / "run/report.json").read_text())
    assert report["status"] == "failed"
    assert report["computed_simulations"] == 0
    assert not verify_artifacts(tmp_path / "run")


def test_rejected_proposals_do_not_launch_experiments(tmp_path, source, config):
    class Rejector(FixtureRoles):
        def _respond(self, role, payload):
            result = super()._respond(role, payload)
            if role == "critic":
                for critique in result["critiques"]:
                    critique["decision"] = "reject"
                result["selected_proposal_id"] = None
            return result

    report = run_research(source, tmp_path / "run", config, roles_factory=Rejector)
    assert report["status"] == "all_proposals_rejected"
    assert report["computed_simulations"] == 0


def test_critic_must_cover_every_proposal(tmp_path, source, config):
    class MissingCritic(FixtureRoles):
        def _respond(self, role, payload):
            result = super()._respond(role, payload)
            if role == "critic":
                result["critiques"] = result["critiques"][:1]
            return result

    with pytest.raises(ValueError, match="each proposal"):
        run_research(source, tmp_path / "run", config, roles_factory=MissingCritic)


def test_call_budget_produces_valid_partial_report(tmp_path, source, config):
    report = run_research(
        source, tmp_path / "run", config.model_copy(update={"max_agent_calls": 1})
    )
    assert report["status"] == "budget_exhausted"
    assert not report["acceptance"]["followup_implemented"]
    assert not verify_artifacts(tmp_path / "run")


def test_simulation_budget_is_enforced_across_workers(tmp_path, source, config):
    report = run_research(
        source, tmp_path / "run", config.model_copy(update={"max_simulations": 16})
    )
    assert report["status"] == "budget_exhausted"
    assert report["computed_simulations"] == 16


def test_no_local_fallback_when_omnigent_fails(tmp_path, source, config, monkeypatch):
    from hacknation_databricks.research.agents import AgentUnavailable, OmnigentRoles

    async def unavailable(self, role, prompt):
        raise AgentUnavailable("No online Omnigent runner")

    monkeypatch.setattr(OmnigentRoles, "_request", unavailable)
    report = run_research(source, tmp_path / "run", config, backend="omnigent")
    assert report["status"] == "blocked_live_backend"
    assert not report["acceptance"]["followup_implemented"]


def test_quote_checks_page_and_document(source):
    good = Evidence(page=1, quote="randomly-oriented Manhattan lattice")
    check_evidence(good, [source])
    for bad in [
        good.model_copy(update={"page": 2}),
        good.model_copy(update={"source_id": "invented"}),
        good.model_copy(update={"quote": "this does not exist"}),
    ]:
        with pytest.raises(ValueError):
            check_evidence(bad, [source])


@pytest.mark.parametrize(
    "change",
    [
        {"sizes": [3, 5]},
        {"sizes": [8, 8]},
        {"sizes": [8, 1000]},
        {"max_workers": 17},
        {"trials": 0},
        {"max_rounds": 99},
        {"unexpected": True},
    ],
)
def test_invalid_or_unbounded_configs_rejected(change):
    with pytest.raises(ValidationError):
        RunConfig(**change)


def test_proposals_reject_executable_experiments(source, tmp_path, config):
    from hacknation_databricks.research.artifacts import RunStore

    roles = FixtureRoles([source], RunStore(tmp_path / "roles"), config)
    batch = roles._respond("reader", {})
    batch["proposals"][0]["experiment"] = "eval('untrusted code')"
    with pytest.raises(ValidationError):
        ProposalBatch.model_validate(batch)


def test_max_three_directions(source, tmp_path, config):
    from hacknation_databricks.research.artifacts import RunStore

    batch = FixtureRoles([source], RunStore(tmp_path / "roles"), config)._respond("reader", {})
    batch["proposals"].append(batch["proposals"][0])
    with pytest.raises(ValidationError):
        ProposalBatch.model_validate(batch)


def test_cli_verifies_manifest_and_returns_failure_for_missing_config(tmp_path, capsys):
    assert main(["run", "--config", str(tmp_path / "missing.json")]) == 2
    assert "FileNotFoundError" in capsys.readouterr().err


def test_runtime_spec_preserves_token_budget():
    from omnigent.spec import load

    spec = load(Path("agents/research-worker"), expand_env=False)
    assert spec.executor.config["harness"] == "openai-agents"
    assert spec.llm.extra["max_tokens"] == 2048
    assert spec.llm.extra["max_turns"] == 1
    assert spec.executor.max_iterations == 1
    assert spec.llm.retry.max_retries == 0
    assert not spec.tools.agents and not spec.tools.builtins


@pytest.mark.parametrize("experiment", ["site_percolation", "resistor_diode"])
def test_other_followup_recipes_execute_without_model_code(tmp_path, source, config, experiment):
    report = run_research(
        source,
        tmp_path / experiment,
        config.model_copy(update={"preferred_experiment": experiment}),
    )
    assert report["acceptance"]["followup_implemented"]
    assert report["selected_proposal"]["experiment"] == experiment
    assert report["status"] == "needs_literature_review"


def test_candidate_loop_is_bounded_even_when_effect_fails(tmp_path, source, config, monkeypatch):
    from hacknation_databricks.research import workflow

    related_path = tmp_path / "related.txt"
    related_path.write_text("Synthetic related-work fixture: randomly-oriented Manhattan lattice.")
    related = read_source(related_path, source_id="related")

    class ReviewedRoles(FixtureRoles):
        def _respond(self, role, payload):
            result = super()._respond(role, payload)
            if role == "literature":
                result["assessment"] = "candidate_gap"
                result["sources"].append(
                    {
                        "source_id": "related",
                        "page": 1,
                        "quote": "randomly-oriented Manhattan lattice",
                    }
                )
            return result

    monkeypatch.setattr(
        workflow, "effect_validation", lambda *args: {"passed": False, "checks": []}
    )
    report = run_research(
        source,
        tmp_path / "run",
        config,
        backend="omnigent",
        literature=[related],
        roles_factory=ReviewedRoles,
    )
    assert report["status"] == "round_budget_exhausted"
    assert len(report["rounds"]) == config.max_rounds
    assert report["role_calls"] == 2 + 5 * config.max_rounds


def test_gate_stops_on_candidate_but_never_claims_discovery(tmp_path, source, config, monkeypatch):
    from hacknation_databricks.research import workflow

    related_path = tmp_path / "related.txt"
    related_path.write_text("Synthetic related-work fixture: randomly-oriented Manhattan lattice.")
    related = read_source(related_path, source_id="related")

    class ReviewedRoles(FixtureRoles):
        def _respond(self, role, payload):
            result = super()._respond(role, payload)
            if role == "literature":
                result["assessment"] = "candidate_gap"
                result["sources"].append(
                    {
                        "source_id": "related",
                        "page": 1,
                        "quote": "randomly-oriented Manhattan lattice",
                    }
                )
            return result

    monkeypatch.setattr(workflow, "effect_validation", lambda *args: {"passed": True, "checks": []})
    report = run_research(
        source,
        tmp_path / "run",
        config,
        backend="omnigent",
        literature=[related],
        roles_factory=ReviewedRoles,
    )
    assert report["status"] == "automated_candidate"
    assert len(report["rounds"]) == 1
    assert report["scientific_novelty"] == "unverified"


def test_paper_checksum_prevents_cache_poisoning(tmp_path):
    path = tmp_path / "source.txt"
    path.write_text("Original source text that is long enough.")
    path.with_suffix(".txt.json").write_text(json.dumps({"sha256": "wrong"}))
    with pytest.raises(ValueError, match="checksum"):
        read_source(path)


def test_configure_agent_preserves_databricks_profile_and_limits(tmp_path, capsys):
    from omnigent.spec import load

    output = tmp_path / "agent"
    assert (
        main(
            [
                "configure-agent",
                "--model",
                "test-endpoint",
                "--databricks-profile",
                "test-profile",
                "--output",
                str(output),
            ]
        )
        == 0
    )
    spec = load(output)
    assert spec.executor.model == spec.llm.model == "test-endpoint"
    assert spec.executor.auth.profile == "test-profile"
    assert spec.executor.config["use_responses"] == "False"
    assert spec.llm.extra["max_tokens"] == 2048
    assert spec.executor.timeout == 300
    assert "no credentials" in capsys.readouterr().out


def test_repeated_source_is_not_independent_literature(tmp_path, source, config):
    from dataclasses import replace

    with pytest.raises(ValueError, match="Duplicate source"):
        run_research(
            source, tmp_path / "run", config, literature=[replace(source, source_id="copy")]
        )


def test_baseline_failure_prevents_followup(tmp_path, source, config, monkeypatch):
    from hacknation_databricks.research import workflow

    monkeypatch.setattr(workflow, "baseline_validation", lambda *args: {"passed": False})
    report = run_research(source, tmp_path / "run", config)
    assert report["status"] == "baseline_failed"
    assert not report["acceptance"]["followup_implemented"]
