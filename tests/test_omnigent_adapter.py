import asyncio
import json
from types import SimpleNamespace

import httpx
import pytest
from omnigent_client import OmnigentClient as RealClient

from hacknation_databricks.research.agents import AgentUnavailable, OmnigentRoles
from hacknation_databricks.research.artifacts import RunStore
from hacknation_databricks.research.models import RunConfig


class FakeChat:
    def __init__(self, namespace, files_uploader, files_getter, session):
        self.session = session

    async def send(self, prompt):
        yield SimpleNamespace(type="response.output_text.delta", delta='{"answer":')
        yield SimpleNamespace(type="response.output_text.delta", delta='"ok"}')
        yield SimpleNamespace(type="response.completed", response=SimpleNamespace(usage=None))


@pytest.fixture
def mock_server(monkeypatch):
    import omnigent_client

    requests = []
    state = {"online": True}

    def handle(request):
        requests.append(
            (
                request.method,
                request.url.path,
                json.loads(request.content) if request.content else None,
            )
        )
        path = request.url.path
        if path == "/v1/agents":
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"id": "ag_test", "name": "research-worker", "harness": "openai-agents"}
                    ]
                },
            )
        if path == "/v1/runners":
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "runner_id": "runner_test",
                            "online": state["online"],
                            "harnesses": ["openai-agents"],
                        }
                    ]
                },
            )
        if path == "/v1/sessions" or (request.method == "PATCH" and path.endswith("conv_test")):
            return httpx.Response(
                200,
                json={
                    "id": "conv_test",
                    "session_id": "conv_test",
                    "agent_id": "ag_test",
                    "status": "idle",
                    "created_at": 1,
                    "updated_at": 1,
                },
            )
        if "events" in path or "interrupt" in path:
            return httpx.Response(200, json={})
        raise AssertionError(f"Unexpected request: {request.method} {path}")

    def factory(base_url, **kwargs):
        client = RealClient(base_url, **kwargs)
        client._http = httpx.AsyncClient(transport=httpx.MockTransport(handle))
        # Namespaces hold the HTTP client passed during construction.
        client.sessions._http = client._http
        return client

    monkeypatch.setattr(omnigent_client, "OmnigentClient", factory)
    monkeypatch.setattr(omnigent_client, "SessionsChat", FakeChat)
    monkeypatch.setenv("OMNIGENT_SERVER_URL", "http://localhost:6767")
    monkeypatch.delenv("OMNIGENT_API_TOKEN", raising=False)
    monkeypatch.delenv("OMNIGENT_HOST_ID", raising=False)
    return requests, state


def test_sdk_resolves_role_agent_binds_runner_and_collects_output(tmp_path, mock_server):
    requests, _ = mock_server
    roles = OmnigentRoles([], RunStore(tmp_path / "run"), RunConfig())
    text, metadata = asyncio.run(roles._request("reader", "source text"))
    assert json.loads(text) == {"answer": "ok"}
    assert metadata == {"session_id": "conv_test", "usage": None}
    assert requests[0][:2] == ("GET", "/v1/agents")
    assert requests[1][:2] == ("GET", "/v1/runners")
    assert requests[2][2]["labels"] == {"role": "reader", "research_run": "run"}
    assert requests[3][2] == {"runner_id": "runner_test"}


def test_missing_runner_stops_before_session_creation(tmp_path, mock_server):
    requests, state = mock_server
    state["online"] = False
    roles = OmnigentRoles([], RunStore(tmp_path / "run"), RunConfig())
    with pytest.raises(AgentUnavailable, match="No online"):
        asyncio.run(roles._request("reader", "source text"))
    assert len(requests) == 2


def test_truncated_stream_cancels_session(tmp_path, mock_server, monkeypatch):
    import omnigent_client

    class TruncatedChat(FakeChat):
        async def send(self, prompt):
            yield SimpleNamespace(type="response.output_text.delta", delta="partial")

    requests, _ = mock_server
    monkeypatch.setattr(omnigent_client, "SessionsChat", TruncatedChat)
    roles = OmnigentRoles([], RunStore(tmp_path / "run"), RunConfig())
    with pytest.raises(AgentUnavailable, match="without a complete"):
        asyncio.run(roles._request("reader", "source text"))
    assert requests[-1][0] == "POST"
    assert requests[-1][2]["type"] == "interrupt"


def test_timeout_cancels_session(tmp_path, mock_server, monkeypatch):
    import omnigent_client

    class StalledChat(FakeChat):
        async def send(self, prompt):
            await asyncio.sleep(10)
            yield

    requests, _ = mock_server
    monkeypatch.setattr(omnigent_client, "SessionsChat", StalledChat)
    roles = OmnigentRoles([], RunStore(tmp_path / "run"), RunConfig(agent_timeout_seconds=1))
    with pytest.raises(TimeoutError):
        asyncio.run(roles._request("reader", "source text"))
    assert requests[-1][2]["type"] == "interrupt"


@pytest.mark.parametrize(
    "url",
    [
        "http://remote.example",
        "https://user:pass@example.com",
        "https://example.com?token=secret",
        "file:///tmp/server",
    ],
)
def test_remote_urls_must_not_leak_credentials(tmp_path, monkeypatch, url):
    monkeypatch.setenv("OMNIGENT_SERVER_URL", url)
    with pytest.raises(ValueError):
        OmnigentRoles([], RunStore(tmp_path / "run"), RunConfig())
