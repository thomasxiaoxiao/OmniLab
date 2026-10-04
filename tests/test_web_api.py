"""HTTP behavior, session isolation and the scientific UI's launch boundary."""

import hashlib
from concurrent.futures import Future

import pytest
from fastapi.testclient import TestClient

from hacknation_databricks.web import server


def nodes(view):
    def walk(items):
        for item in items:
            yield item
            yield from walk(item.get("children", []))

    return list(walk(view["main"] + view["sidebar"]))


def control(view, label):
    return next(n for n in nodes(view) if n.get("widget") and n.get("label") == label)


def event(client, view, *, values=None, action=None, page=None):
    return client.post(
        "/api/event",
        headers={"X-CSRF-Token": view["csrf"]},
        json={"revision": view["revision"], "values": values or {}, "action": action, "page": page},
    )


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("RESEARCH_RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.setenv("RESEARCH_SOURCES_DIR", str(tmp_path / "sources"))
    monkeypatch.delenv("RESEARCH_PAPER_PATH", raising=False)
    monkeypatch.setattr(server, "_sessions", {})
    with TestClient(server.app) as client:
        yield client


def test_all_pages_render_without_sources_or_model_calls(client):
    for page in ["sources", "overview", "agents", "policies", "evidence"]:
        response = client.get("/api/view", params={"page": page})
        assert response.status_code == 200
        assert response.json()["page"] == page
    assert client.get("/api/view?page=../../etc/passwd").status_code == 400
    assert client.get("/health").json()["frontend"] == "react"
    assert client.get("/_stcore/health").text == "ok"


def test_csrf_origin_and_unknown_state_are_rejected_before_mutation(client):
    view = client.get("/api/view").json()
    assert client.post("/api/event", json={}).status_code == 403
    assert (
        client.post(
            "/api/event",
            headers={"X-CSRF-Token": view["csrf"], "Origin": "https://attacker.example"},
            json={},
        ).status_code
        == 403
    )
    response = event(client, view, values={"research_future": "forged"})
    assert response.status_code == 400
    assert "research_future" not in next(iter(server._sessions.values())).state
    assert client.get("/api/view", headers={"Host": "attacker.example"}).status_code == 400


def test_stale_actions_are_never_replayed(client):
    view = client.get("/api/view").json()
    client.get("/api/view")
    response = event(client, view, action=control(view, "Refresh artifacts")["widget"])
    assert response.status_code == 409


def test_form_upload_preserves_original_bytes_and_clears_form(client, tmp_path):
    view = client.get("/api/view").json()
    content = b"# Scientific paper\n\nKeep the original evidence exactly.\n"
    upload = client.post(
        "/api/upload",
        params={"widget": control(view, "PDF or Markdown")["widget"], "name": "evidence.md"},
        content=content,
        headers={"X-CSRF-Token": view["csrf"]},
    )
    assert upload.status_code == 200
    response = event(
        client,
        view,
        values={control(view, "PDF or Markdown")["widget"]: [upload.json()["token"]]},
        action=control(view, "Add files to library")["widget"],
    )
    assert response.status_code == 200
    after = response.json()
    assert any(n["type"] == "success" and "Ready:" in n["value"] for n in nodes(after))
    digest = hashlib.sha256(content).hexdigest()
    assert (tmp_path / "sources" / digest / "source.md").read_bytes() == content
    assert control(after, "PDF or Markdown")["value"] == []
    assert digest[:8] in control(after, "Uploaded paper")["options"][0]


def test_uploads_are_session_scoped_and_type_size_bounded(client):
    view = client.get("/api/view").json()
    params = {"widget": control(view, "PDF or Markdown")["widget"], "name": "script.py"}
    headers = {"X-CSRF-Token": view["csrf"]}
    assert (
        client.post("/api/upload", params=params, content=b"print(1)", headers=headers).status_code
        == 400
    )
    params["name"] = "source.md"
    assert (
        client.post(
            "/api/upload", params=params, content=b"x" * (10 * 1024 * 1024 + 1), headers=headers
        ).status_code
        == 413
    )
    token = client.post(
        "/api/upload", params=params, content=b"A valid source.", headers=headers
    ).json()["token"]
    with TestClient(server.app) as other:
        foreign = other.get("/api/view").json()
        assert (
            event(
                other, foreign, values={control(foreign, "PDF or Markdown")["widget"]: [token]}
            ).status_code
            == 400
        )


def test_numeric_bounds_and_disabled_launch_are_enforced_on_server(client):
    view = client.get("/api/view").json()
    launch = control(view, "Start bounded run")
    assert launch["disabled"]
    assert event(client, view, action=launch["widget"]).status_code == 400
    budget = control(view, "Agent request budget")
    for invalid in [0, 513, "96", True, 40.5]:
        assert event(client, view, values={budget["widget"]: invalid}).status_code == 400


def test_policy_persists_and_exact_launch_identity_survives_redirect(
    client, monkeypatch, launch_source
):
    from hacknation_databricks import tracking_ui

    submitted = []
    future = Future()

    class Executor:
        def submit(self, fn, *args, **kwargs):
            submitted.append((args, kwargs))
            return future

    monkeypatch.setattr(tracking_ui, "background_executor", lambda: Executor())
    view = client.get("/api/view?page=policies").json()
    view = event(client, view, values={control(view, "Policy workspace")["widget"]: 1}).json()
    view = event(client, view, values={control(view, "Policy profile")["widget"]: 1}).json()
    view = event(
        client,
        view,
        values={control(view, "Agent request budget")["widget"]: 40},
        action=control(view, "Save next-run policy")["widget"],
    ).json()
    view = event(client, view, page="sources").json()
    assert control(view, "Agent request budget")["value"] == 40
    action = control(view, "Start bounded run")["widget"]
    response = event(client, view, action=action)
    assert response.status_code == 200
    after = response.json()
    assert after["page"] == "agents"
    assert len(submitted) == 1
    assert submitted[0][0][2] == "omnigent"
    assert submitted[0][0][5]["workflow"] == "repository"
    assert submitted[0][0][5]["max_agent_calls"] == 40
    assert submitted[0][1]["run_name"] in next(iter(server._sessions.values())).state.values()
    assert event(client, after, action=action).status_code == 400
    future.set_exception(ValueError("Omnigent unavailable for this test"))
    failed = client.get("/api/view").json()
    assert any(n["type"] == "error" and "Run could not start" in n["value"] for n in nodes(failed))


def test_graph_click_selects_recorded_step_and_rejects_invented_steps(client, tmp_path):
    from test_adaptive import make_run

    (tmp_path / "runs").mkdir()
    make_run(tmp_path / "runs")
    view = client.get("/api/view?page=agents").json()
    graph = next(n for n in nodes(view) if n["type"] == "execution_graph")
    chosen = list(graph["graph"]["labels"])[-1]
    after = event(client, view, values={graph["widget"]: chosen}).json()
    graph = next(n for n in nodes(after) if n["type"] == "execution_graph")
    assert graph["graph"]["selected"] == chosen
    assert event(client, after, values={graph["widget"]: "invented-session"}).status_code == 400
    polled = client.get("/api/view").json()
    assert (
        next(n for n in nodes(polled) if n["type"] == "execution_graph")["graph"]["selected"]
        == chosen
    )


def test_downloads_are_exact_and_cannot_cross_sessions(client, tmp_path):
    from test_adaptive import make_run

    (tmp_path / "runs").mkdir()
    make_run(tmp_path / "runs")
    view = client.get("/api/view?page=evidence").json()
    selected = control(view, "Inspect artifact")
    name = selected["options"][selected["value"]]
    link = next(n["url"] for n in nodes(view) if n.get("label") == "Download artifact")
    response = client.get(link)
    assert response.content == (tmp_path / "runs/run" / name).read_bytes()
    assert response.headers["content-disposition"].startswith("attachment")
    with TestClient(server.app) as other:
        other.get("/api/view")
        assert other.get(link).status_code == 404


def test_tampered_archives_stay_quarantined(client, tmp_path):
    from test_adaptive import make_run

    (tmp_path / "runs").mkdir()
    make_run(tmp_path / "runs")
    (tmp_path / "runs/run/config.json").write_text("{}")
    view = client.get("/api/view?page=overview").json()
    assert any(n["type"] == "error" and "quarantined" in n["value"] for n in nodes(view))
    assert not any(n["type"] == "iframe" for n in nodes(view))


def test_players_are_sandboxed_and_archived_html_cannot_run(client):
    client.get("/api/view")
    session = next(iter(server._sessions.values()))
    session.blobs["trusted-player"] = (
        b"<html><body>Player</body></html>",
        "process.html",
        "text/html",
    )
    response = client.get("/api/embed/trusted-player")
    assert response.status_code == 200
    policy = response.headers["content-security-policy"]
    assert "sandbox allow-scripts;" in policy
    assert "allow-same-origin" not in policy
    assert "connect-src 'none'" in policy
    download = client.get("/api/download/trusted-player")
    assert download.headers["content-disposition"].startswith("attachment")
    assert "sandbox;" in download.headers["content-security-policy"]


def test_tabs_sharing_a_cookie_have_independent_state_and_revisions(client):
    first = client.get("/api/view?page=policies", headers={"X-View-ID": "tab-one"}).json()
    second = client.get("/api/view?page=sources", headers={"X-View-ID": "tab-two"}).json()
    assert first["page"] == "policies" and second["page"] == "sources"
    client.get("/api/view", headers={"X-View-ID": "tab-two"})
    response = client.post(
        "/api/event",
        headers={"X-View-ID": "tab-one", "X-CSRF-Token": first["csrf"]},
        json={"revision": first["revision"], "values": {}, "page": "overview"},
    )
    assert response.status_code == 200
    assert response.json()["page"] == "overview"
    assert client.get("/api/view", headers={"X-View-ID": "tab-two"}).json()["page"] == "sources"
    assert (
        client.post(
            "/api/event", headers={"X-View-ID": "tab-two", "X-CSRF-Token": first["csrf"]}, json={}
        ).status_code
        == 403
    )


def test_upload_without_code_enables_the_full_workflow_and_keeps_seed_menu(client, monkeypatch):
    from hacknation_databricks import tracking_ui

    submitted = []

    class Executor:
        def submit(self, fn, *args, **kwargs):
            submitted.append((fn, args, kwargs))
            return Future()

    monkeypatch.setattr(tracking_ui, "background_executor", lambda: Executor())
    view = client.get("/api/view").json()
    seeds = control(view, "Seed paper")["options"]
    content = b"Compare decay rates with a reproducible numerical model."
    token = client.post(
        "/api/upload",
        params={"widget": control(view, "PDF or Markdown")["widget"], "name": "new-paper.md"},
        content=content,
        headers={"X-CSRF-Token": view["csrf"]},
    ).json()["token"]
    view = event(
        client,
        view,
        values={control(view, "PDF or Markdown")["widget"]: [token]},
        action=control(view, "Add files to library")["widget"],
    ).json()
    assert control(view, "Seed paper")["options"] == seeds
    assert not control(view, "Start bounded run")["disabled"]
    assert control(view, "Paper's GitHub repository (optional)")["value"] == ""
    response = event(client, view, action=control(view, "Start bounded run")["widget"])
    assert response.status_code == 200
    assert response.json()["page"] == "agents"
    fn, args, kwargs = submitted[0]
    assert fn is tracking_ui.launch_run
    assert args[0].read_bytes() == content
    assert args[2] == "omnigent"
    assert args[5]["workflow"] == "repository"
    assert args[5]["allow_paper_implementation"] is True
    assert args[5]["repository_url"] == ""
    assert kwargs["run_name"]
    # Refresh/navigation cannot dispatch the same launch a second time.
    client.get("/api/view")
    assert len(submitted) == 1
