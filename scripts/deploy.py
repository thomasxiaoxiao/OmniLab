#!/usr/bin/env python3
"""Deploy CI-approved main commits into isolated releases; leave the checkout alone."""

import argparse
import fcntl
import json
import os
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(os.environ.get("PROJECT_ROOT", Path(__file__).resolve().parents[1]))
RUNTIME = ROOT / ".runtime"
APP_NAME = "hacknation-app"


def run(*args: str, cwd: Path = ROOT, env: dict | None = None) -> str:
    return subprocess.run(
        args, cwd=cwd, env=env, check=True, text=True, stdout=subprocess.PIPE, timeout=300
    ).stdout.strip()


def ci_passed(runs: list[dict], revision: str) -> bool:
    """Only the newest push run on main can approve this exact revision."""
    matching = [
        item
        for item in runs
        if item["headSha"] == revision and item["headBranch"] == "main" and item["event"] == "push"
    ]
    return bool(
        matching and matching[0]["status"] == "completed" and matching[0]["conclusion"] == "success"
    )


def health_matches(url: str, revision: str) -> bool:
    try:
        processes = json.loads(run("bash", str(ROOT / "scripts/pm2.sh"), "jlist"))
        running = any(
            process["name"] == APP_NAME
            and process["pm2_env"]["status"] == "online"
            and process["pm2_env"].get("APP_REVISION") == revision
            and process["pm2_env"].get("APP_DIR") is not None
            and process["pm2_env"].get("pm_cwd") == process["pm2_env"]["APP_DIR"]
            and process["pm2_env"].get("pm_exec_path")
            == str(Path(process["pm2_env"]["APP_DIR"]) / ".venv/bin/python")
            for process in processes
        )
        if not running:
            return False
        with urllib.request.urlopen(url, timeout=2) as response:
            return response.status == 200 and response.read().strip() == b"ok"
    except (OSError, ValueError, urllib.error.URLError, subprocess.SubprocessError):
        return False


def wait_healthy(url: str, revision: str) -> None:
    for _ in range(30):
        if health_matches(url, revision):
            return
        time.sleep(1)
    raise RuntimeError(f"Health check failed for {revision} at {url}")


def activate(release: dict) -> None:
    env = {
        **os.environ,
        "PROJECT_ROOT": str(ROOT),
        "PM2_HOME": str(RUNTIME / "pm2"),
        "APP_DIR": release["path"],
        "APP_REVISION": release["revision"],
    }
    # PM2 restart preserves the previous executable and cwd across release paths.
    processes = json.loads(run("bash", str(ROOT / "scripts/pm2.sh"), "jlist"))
    if any(process["name"] == APP_NAME for process in processes):
        run("bash", str(ROOT / "scripts/pm2.sh"), "delete", APP_NAME)
    print(
        run(
            "bash",
            str(ROOT / "scripts/pm2.sh"),
            "start",
            str(Path(release["path"]) / "ecosystem.config.js"),
            "--only",
            APP_NAME,
            "--update-env",
            env=env,
        ),
        flush=True,
    )


def promote(candidate: dict, previous: dict | None, health_url: str) -> None:
    try:
        activate(candidate)
        wait_healthy(health_url, candidate["revision"])
    except Exception:
        if previous:
            print(f"Restoring previous release {previous['revision']}", flush=True)
            activate(previous)
            wait_healthy(health_url, previous["revision"])
        else:
            run("bash", str(ROOT / "scripts/pm2.sh"), "delete", APP_NAME)
        raise
    temporary = RUNTIME / "current.json.tmp"
    temporary.write_text(json.dumps(candidate) + "\n")
    temporary.replace(RUNTIME / "current.json")
    run("bash", str(ROOT / "scripts/pm2.sh"), "save")


def deploy(health_url: str) -> None:
    run("git", "fetch", "origin", "+refs/heads/main:refs/remotes/origin/main")
    revision = run("git", "rev-parse", "refs/remotes/origin/main^{commit}")
    current_file = RUNTIME / "current.json"
    previous = json.loads(current_file.read_text()) if current_file.exists() else None
    if previous and previous["revision"] == revision and health_matches(health_url, revision):
        return

    runs = json.loads(
        run(
            "gh",
            "run",
            "list",
            "--workflow",
            "ci.yml",
            "--commit",
            revision,
            "--branch",
            "main",
            "--event",
            "push",
            "--limit",
            "1",
            "--json",
            "headSha,headBranch,event,status,conclusion",
        )
    )
    if not ci_passed(runs, revision):
        print(f"Waiting for successful CI on main at {revision[:12]}", flush=True)
        return

    releases = RUNTIME / "releases"
    releases.mkdir(parents=True, exist_ok=True)
    release = Path(tempfile.mkdtemp(prefix=f"{revision[:12]}-", dir=releases))
    archive = release / "source.tar"
    run("git", "archive", "--format=tar", "--output", str(archive), revision)
    run("tar", "-xf", str(archive), "-C", str(release))
    archive.unlink()
    # Clear inherited virtualenv selection; each release owns its own environment.
    env = dict(os.environ)
    env.pop("VIRTUAL_ENV", None)
    env.pop("UV_PROJECT_ENVIRONMENT", None)
    run("uv", "sync", "--locked", "--no-dev", "--no-editable", cwd=release, env=env)
    candidate = {"revision": revision, "path": str(release)}
    promote(candidate, previous, health_url)
    print(f"Deployed {revision} at {health_url}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--once", action="store_true")
    mode.add_argument("--watch", action="store_true")
    parser.add_argument("--interval", type=int, default=60)
    parser.add_argument(
        "--health-url",
        default=os.environ.get("DEPLOY_HEALTH_URL", "http://127.0.0.1:8010/_stcore/health"),
    )
    args = parser.parse_args()
    if args.interval < 10:
        parser.error("--interval must be at least 10 seconds")
    RUNTIME.mkdir(parents=True, exist_ok=True)
    with (RUNTIME / "deploy.lock").open("w") as lock:
        while True:
            acquired = False
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
                deploy(args.health_url)
            except BlockingIOError:
                if args.once:
                    raise SystemExit("Another deployment is in progress") from None
            except Exception as error:
                if args.once:
                    raise
                print(f"Deployment failed: {error}", flush=True)
            finally:
                if acquired:
                    fcntl.flock(lock, fcntl.LOCK_UN)
            if args.once:
                break
            time.sleep(args.interval)


if __name__ == "__main__":
    main()
