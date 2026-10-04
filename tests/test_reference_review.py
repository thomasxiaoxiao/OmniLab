import asyncio
import json

import httpx
import pytest
from fixture_roles import FixtureRoles
from legacy.workflow import run_research

from hacknation_databricks.research.agents import OmnigentRoles
from hacknation_databricks.research.artifacts import RunStore
from hacknation_databricks.research.cli import fixture_source, main
from hacknation_databricks.research.literature import cited_arxiv, retrieve_references
from hacknation_databricks.research.models import RunConfig
from hacknation_databricks.research.sources import read_source


def test_reference_retrieval_accounts_for_failures_duplicates_and_budget(tmp_path, monkeypatch):
    from hacknation_databricks.research import literature

    seed = tmp_path / "seed.txt"
    seed.write_text(
        "arXiv:2607.24975v1 cites arxiv:2605.16987 and arXiv:2412.20781, "
        "arxiv:2512.10566 and arxiv:2101.00001. Duplicate arxiv:2605.16987."
    )
    source = read_source(seed, url="https://arxiv.org/abs/2607.24975v1")
    reference = tmp_path / "reference.txt"
    reference.write_text("An independent paper about percolation with actual source text.")
    calls = []

    def fetch(identifier, destination):
        calls.append(identifier)
        if identifier == "2412.20781":
            raise TimeoutError("sensitive provider body must not be logged")
        return reference

    monkeypatch.setattr(literature, "fetch_arxiv", fetch)
    assert len(cited_arxiv(source)) == 4
    sources, audit = retrieve_references(source, tmp_path, limit=3)
    assert len(sources) == 1
    assert len(calls) == 3
    assert [r["status"] for r in audit["records"]] == [
        "retrieved_for_review",
        "unavailable",
        "duplicate",
        "not_requested_budget",
    ]
    assert "sensitive" not in json.dumps(audit)


def test_evaluator_cannot_invent_or_omit_reviewed_reference_evidence(tmp_path):
    source = read_source(fixture_source())
    related = tmp_path / "reference.txt"
    related.write_text("An independent related work source with actual text.")

    class Fabricator(FixtureRoles):
        def _respond(self, role, payload):
            result = super()._respond(role, payload)
            if role == "novelty_evaluator":
                result["comparisons"][0]["evidence"][1]["quote"] = (
                    "Invented evidence absent in source"
                )
            return result

    with pytest.raises(ValueError, match="Untraceable"):
        run_research(
            source,
            tmp_path / "run",
            RunConfig(sizes=[8, 16], trials=32),
            backend="omnigent",
            literature=[read_source(related, "related")],
            roles_factory=Fabricator,
        )
    assert json.loads((tmp_path / "run/report.json").read_text())["status"] == "failed"


def test_host_launch_waits_for_its_own_runner(tmp_path, monkeypatch):
    requests = []
    real_client = httpx.AsyncClient

    def handle(request):
        requests.append(request)
        if request.method == "POST":
            return httpx.Response(200, json={"runner_id": "runner_own", "status": "launching"})
        return httpx.Response(200, json={"data": [{"runner_id": "runner_own", "online": True}]})

    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: real_client(**kw, transport=httpx.MockTransport(handle))
    )
    monkeypatch.setenv("OMNIGENT_HOST_ID", "local_host")
    monkeypatch.setenv("RESEARCH_AGENT_WORKSPACE", str(tmp_path / "workspace"))
    roles = OmnigentRoles([], RunStore(tmp_path / "run"), RunConfig())
    assert asyncio.run(roles._launch_host("session_new", None)) == "runner_own"
    assert requests[0].url.path == "/v1/hosts/local_host/runners"
    assert json.loads(requests[0].content) == {
        "session_id": "session_new",
        "workspace": str((tmp_path / "workspace" / "session_new").resolve()),
    }


def test_subscription_and_api_configuration_write_no_keys(tmp_path, monkeypatch):
    from omnigent.spec import load

    monkeypatch.setenv("OPENAI_API_KEY", "must-not-be-saved")
    for auth, harness in [("subscription", "codex"), ("api-key", "openai-agents")]:
        target = tmp_path / auth
        assert (
            main(
                [
                    "configure-agent",
                    "--auth",
                    auth,
                    "--model",
                    "test-model",
                    "--output",
                    str(target),
                ]
            )
            == 0
        )
        spec = load(target)
        assert spec.executor.harness_kind == harness
        assert "must-not-be-saved" not in (target / "config.yaml").read_text()
        assert spec.skills_filter == "none"
