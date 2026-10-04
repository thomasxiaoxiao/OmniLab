"""Repeat sealed repository experiments without requesting another model response."""

import json
import re
from pathlib import Path

from .artifacts import RunStore, verify_artifacts
from .code_sandbox import execute_code
from .repository_models import RepositoryImplementation


def saved_implementation(directory):
    value = json.loads((directory / "implementation.json").read_text())
    if "python_code" in value:
        return RepositoryImplementation.model_validate(value)
    # Early v5 archives kept the implementation response in the role transcript.
    responses = list(directory.glob("roles/*-repository_experimenter-response.json"))
    if len(responses) != 1:
        raise ValueError("No unambiguous archived implementation response")
    raw = json.loads(responses[0].read_text())["raw"]
    return RepositoryImplementation.model_validate_json(
        re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip())
    )


def replay_repository(directory, output, number=None):
    failures = verify_artifacts(directory)
    if failures:
        raise ValueError("Cannot replay an archive that failed verification")
    report = json.loads((directory / "report.json").read_text())
    if report.get("workflow") != "repository" or not report.get("rounds"):
        raise ValueError("Select a completed repository experiment")
    row = (
        next((r for r in report["rounds"] if r["round"] == number), None)
        if number
        else report["rounds"][-1]
    )
    if not row:
        raise ValueError("Unknown experiment number")
    prefix = row["artifact_prefix"]
    execution = json.loads((directory / prefix / "execution.json").read_text())
    manifest = json.loads((directory / "repository/manifest.json").read_text())
    implementation = saved_implementation(directory)
    config = json.loads((directory / "config.json").read_text())
    store = RunStore(output)
    status = {
        "status": "running",
        "source_run": str(directory),
        "round": row["round"],
        "new_model_calls": 0,
    }
    try:
        for item in manifest["files"]:
            path = Path("repository/source") / item["path"]
            target = output / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((directory / path).read_bytes())
        store.write("repository/manifest.json", manifest)
        store.write("implementation.json", implementation.model_dump())
        result = execute_code(
            store,
            implementation,
            manifest,
            execution["jobs"],
            stage="replay",
            timeout=config["code_timeout_seconds"],
        )
        original = json.loads((directory / prefix / "trials.json").read_text())
        status["status"] = "matched" if result["trials"] == original["trials"] else "mismatch"
    except Exception as exc:
        status.update(status="failed", error_type=type(exc).__name__)
    finally:
        store.write("replay.json", status)
        store.seal()
    return status
