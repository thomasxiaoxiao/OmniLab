import importlib.util
import io
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "deploy", Path(__file__).resolve().parents[1] / "scripts" / "deploy.py"
)
deploy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deploy)


def ci_run(**overrides):
    return {
        "headSha": "candidate",
        "headBranch": "main",
        "event": "push",
        "status": "completed",
        "conclusion": "success",
        **overrides,
    }


@pytest.mark.parametrize(
    "runs",
    [
        [],
        [ci_run(headSha="another")],
        [ci_run(headBranch="feature")],
        [ci_run(event="pull_request")],
        [ci_run(status="in_progress", conclusion="")],
        [ci_run(conclusion="failure"), ci_run()],
    ],
)
def test_deploy_requires_latest_successful_main_push(runs):
    assert not deploy.ci_passed(runs, "candidate")


def test_deploy_accepts_success_for_exact_revision():
    assert deploy.ci_passed([ci_run()], "candidate")


@pytest.mark.parametrize("running_revision, expected", [("older", False), ("candidate", True)])
def test_health_requires_http_success_and_matching_pm2_revision(
    monkeypatch, running_revision, expected
):
    processes = [
        {
            "name": deploy.APP_NAME,
            "pm2_env": {
                "status": "online",
                "APP_REVISION": running_revision,
                "APP_DIR": "/releases/candidate",
                "pm_cwd": "/releases/candidate",
                "pm_exec_path": "/releases/candidate/.venv/bin/python",
            },
        }
    ]
    monkeypatch.setattr(deploy, "run", lambda *args: json.dumps(processes))
    response = io.BytesIO(b"ok")
    response.status = 200
    monkeypatch.setattr(deploy.urllib.request, "urlopen", lambda *args, **kwargs: response)
    assert deploy.health_matches("http://localhost/_stcore/health", "candidate") is expected


def test_health_rejects_stale_executable_despite_updated_revision(monkeypatch):
    processes = [
        {
            "name": deploy.APP_NAME,
            "pm2_env": {
                "status": "online",
                "APP_REVISION": "candidate",
                "APP_DIR": "/releases/new",
                "pm_cwd": "/releases/old",
                "pm_exec_path": "/releases/old/.venv/bin/python",
            },
        }
    ]
    monkeypatch.setattr(deploy, "run", lambda *args: json.dumps(processes))
    assert not deploy.health_matches("http://localhost/_stcore/health", "candidate")


def test_activate_replaces_existing_pm2_process(monkeypatch):
    calls = []

    def run(*args, **kwargs):
        calls.append(args)
        return json.dumps([{"name": deploy.APP_NAME}]) if args[-1] == "jlist" else ""

    monkeypatch.setattr(deploy, "run", run)
    deploy.activate({"revision": "candidate", "path": "/releases/new"})
    assert calls[1][-2:] == ("delete", deploy.APP_NAME)
    assert calls[2][2:4] == ("start", str(deploy.ROOT / "ecosystem.config.js"))


def test_failed_health_restores_previous_release(monkeypatch, tmp_path):
    previous = {"revision": "good", "path": "/releases/good"}
    candidate = {"revision": "bad", "path": "/releases/bad"}
    state = tmp_path / "current.json"
    state.write_text(json.dumps(previous))
    activated = []
    monkeypatch.setattr(deploy, "RUNTIME", tmp_path)
    monkeypatch.setattr(deploy, "activate", activated.append)

    def health(url, revision):
        if revision == "bad":
            raise RuntimeError("unhealthy")

    monkeypatch.setattr(deploy, "wait_healthy", health)
    with pytest.raises(RuntimeError, match="unhealthy"):
        deploy.promote(candidate, previous, "http://localhost/healthz")
    assert activated == [candidate, previous]
    assert json.loads(state.read_text()) == previous


def test_success_records_release_after_health(monkeypatch, tmp_path):
    candidate = {"revision": "good", "path": "/releases/good"}
    monkeypatch.setattr(deploy, "RUNTIME", tmp_path)
    monkeypatch.setattr(deploy, "activate", lambda release: None)
    monkeypatch.setattr(deploy, "wait_healthy", lambda url, revision: None)
    monkeypatch.setattr(deploy, "run", lambda *args: "")
    deploy.promote(candidate, None, "http://localhost/healthz")
    assert json.loads((tmp_path / "current.json").read_text()) == candidate


@pytest.mark.parametrize("require_ci", [False, True])
def test_ci_gate_is_optional_and_default_promotion_skips_github(monkeypatch, tmp_path, require_ci):
    monkeypatch.setattr(deploy, "RUNTIME", tmp_path)
    if require_ci:
        monkeypatch.setenv("DEPLOY_REQUIRE_CI", "1")
    else:
        monkeypatch.delenv("DEPLOY_REQUIRE_CI", raising=False)
    calls = []
    promoted = []

    def run(*args, **kwargs):
        calls.append(args)
        if args[:2] == ("git", "rev-parse"):
            return "candidate"
        if args[0] == "gh":
            return "[]"
        if args[:2] == ("git", "archive"):
            Path(args[4]).touch()
        return ""

    monkeypatch.setattr(deploy, "run", run)
    monkeypatch.setattr(deploy, "promote", lambda *args: promoted.append(args))
    deploy.deploy("http://localhost/health")
    assert any(call[0] == "gh" for call in calls) is require_ci
    assert bool(promoted) is not require_ci
    if promoted:
        assert promoted[0][0]["revision"] == "candidate"
