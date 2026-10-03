import json

import pytest
from fixture_roles import FixtureRoles, run_fixture

from hacknation_databricks.research.activity import activity_dot, activity_export, load_activity
from hacknation_databricks.research.agents import OmnigentRoles
from hacknation_databricks.research.cli import fixture_source
from hacknation_databricks.research.models import RunConfig
from hacknation_databricks.research.sources import read_source
from hacknation_databricks.research.workflow import run_research
from hacknation_databricks.tracking import load_journal


def test_fixture_graph_has_no_invented_omnigent_sessions(tmp_path):
    run_fixture(
        read_source(fixture_source()), tmp_path / "run", RunConfig(sizes=[8, 16], trials=32)
    )
    journal = load_journal(tmp_path / "run")
    assert journal.verified, journal.issues
    nodes = load_activity(journal)
    assert len(nodes) == 7
    assert all(n.session_id is None for n in nodes)
    assert {n.round for n in nodes} == {0, 1}
    assert "baseline/trials.csv" in nodes[2].artifacts
    assert "roles/01-reader.json" in nodes[0].artifacts
    dot = activity_dot(nodes)
    assert "Test fixture" in dot and "Omnigent session" not in dot
    assert "Round 2" not in dot
    assert json.loads(activity_export(journal, nodes))["verified"]


def test_mocked_omnigent_sessions_correlate_rounds_responses_and_outputs(tmp_path, monkeypatch):
    from hacknation_databricks.research import workflow

    source = read_source(fixture_source())
    related = tmp_path / "related.md"
    related.write_text("Related work: randomly-oriented Manhattan lattice.")
    literature = read_source(related, source_id="related")

    class MockedOmnigent(OmnigentRoles):
        async def _request(self, role, prompt):
            fake = FixtureRoles(self.sources, self.store, self.config)
            answer = fake._respond(role, json.loads(prompt)["data"])
            if role == "literature":
                answer["assessment"] = "candidate_gap"
                answer["sources"].append(
                    {
                        "source_id": "related",
                        "page": 1,
                        "quote": "randomly-oriented Manhattan lattice",
                    }
                )
            session = f"mock-session-{self.calls}"
            self.store.event(
                "agent_session",
                {
                    "session_id": session,
                    "role": role,
                    "agent_id": "mock-agent",
                    "runner_id": "mock-runner",
                },
            )
            return json.dumps(answer), {"session_id": session, "usage": {"total_tokens": 10}}

    monkeypatch.setattr(
        workflow, "effect_validation", lambda *args: {"passed": False, "checks": []}
    )
    run_research(
        source,
        tmp_path / "run",
        RunConfig(sizes=[8, 16], trials=32),
        backend="omnigent",
        literature=[literature],
        roles_factory=MockedOmnigent,
    )
    journal = load_journal(tmp_path / "run")
    assert journal.verified, journal.issues
    nodes = load_activity(journal)
    assert len(nodes) == 13
    agents = [node for node in nodes if node.session_id]
    assert len(agents) == 10
    assert all(n.schema_valid and n.status == "completed" for n in agents)
    assert agents[0].runner_id == "mock-runner"
    assert "roles/01-reader-request.json" in agents[0].artifacts
    assert "roles/01-reader-response.json" in agents[0].artifacts
    assert "proposals.json" in agents[0].artifacts
    second_literature = next(n for n in agents if n.round == 2 and n.role == "literature")
    assert "rounds/02/literature.json" in second_literature.artifacts
    assert "repeat recorded" in activity_dot(nodes)
    assert "Round 2" in activity_dot(nodes)


def test_invalid_agent_output_remains_visible_as_failed(tmp_path):
    class InvalidOutput(OmnigentRoles):
        async def _request(self, role, prompt):
            self.store.event("agent_session", {"role": role, "session_id": "mock-failed"})
            return '{"invalid": true}', {"session_id": "mock-failed", "usage": None}

    with pytest.raises(ValueError):
        run_research(
            read_source(fixture_source()),
            tmp_path / "run",
            backend="omnigent",
            roles_factory=InvalidOutput,
        )
    journal = load_journal(tmp_path / "run")
    assert journal.verified, journal.issues
    nodes = load_activity(journal)
    assert len(nodes) == 1 and nodes[0].status == "failed"
    assert nodes[0].session_id == "mock-failed"
    assert nodes[0].error_type == "ValidationError"
    assert "roles/01-reader-response.json" in nodes[0].artifacts
    assert not nodes[0].schema_valid


def test_running_and_quarantined_traces_do_not_claim_completion(tmp_path):
    from hacknation_databricks.research.artifacts import RunStore
    from hacknation_databricks.tracking import Journal

    store = RunStore(tmp_path / "run")
    store.event("stage_started", {"stage": "reader"})
    store.event("agent_session", {"session_id": "mock-live", "role": "reader"})
    journal = Journal("run", tmp_path / "run", report={"backend": "omnigent"})
    node = load_activity(journal)[0]
    assert node.status == "running" and node.finished_at is None
    journal.issues.append("hash mismatch")
    assert load_activity(journal) == []


def test_multiple_sessions_in_one_stage_are_all_visible(tmp_path):
    from hacknation_databricks.research.artifacts import RunStore
    from hacknation_databricks.tracking import Journal

    store = RunStore(tmp_path / "run")
    with store.stage("rounds/01/validation"):
        for index, role in enumerate(["validator", "novelty_evaluator"], 1):
            call_id = f"roles/{index:02d}-{role}"
            store.write(f"{call_id}-request.json", {"input": role})
            store.event("agent_call_started", {"role": role, "call_id": call_id})
            store.event("agent_session_created", {"role": role, "session_id": f"mock-{index}"})
            store.write(f"{call_id}-response.json", {"output": role})
            store.event("agent_call_completed", {"role": role, "schema_valid": True})
    journal = Journal("run", store.directory, report={"backend": "omnigent"})
    nodes = load_activity(journal)
    assert [n.session_id for n in nodes] == ["mock-1", "mock-2"]
    assert [n.role for n in nodes] == ["validator", "novelty_evaluator"]
    assert all(n.status == n.stage_status == "completed" for n in nodes)
    assert nodes[0].artifacts == [
        "roles/01-validator-request.json",
        "roles/01-validator-response.json",
    ]
    assert nodes[1].artifacts == [
        "roles/02-novelty_evaluator-request.json",
        "roles/02-novelty_evaluator-response.json",
    ]


def test_svg_escapes_labels_and_only_marks_observed_repeats():
    import xml.etree.ElementTree as ET

    from hacknation_databricks.research.activity import Activity, activity_svg

    nodes = [
        Activity(
            "rounds/01/validation",
            "<script>bad</script>",
            1,
            "omnigent",
            "now",
            session_id="mock-session",
        ),
        Activity("rounds/02/literature", "literature", 2, "omnigent", "later"),
    ]
    svg = activity_svg(nodes, nodes[0].key)
    ET.fromstring(svg)
    assert "<script>" not in svg and "&lt;script&gt;" in svg
    assert "Repeat recorded" in svg and "Round 3" not in svg
