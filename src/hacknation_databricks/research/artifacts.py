"""Append-only run directories, content hashes, and audit events."""

import hashlib
import json
import platform
import subprocess
import threading
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path


def canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n"


def code_digest() -> str:
    digest = hashlib.sha256()
    for path in sorted(Path(__file__).parent.glob("*.py")):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


class RunStore:
    def __init__(self, directory: Path):
        directory.mkdir(parents=True, exist_ok=True)
        if any(directory.iterdir()):
            raise ValueError(f"Output directory is not empty: {directory}; use a fresh run path")
        self.directory = directory
        self.started = time.monotonic()
        self._local = threading.local()
        self._lock = threading.RLock()
        self.event("run_created", {})

    def write(self, name: str, value: object) -> Path:
        target = self.directory / name
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(target.suffix + ".tmp")
        temporary.write_text(canonical(value))
        temporary.replace(target)
        if name != "manifest.json":
            self.event("artifact_written", {"path": name})
        return target

    def event(self, name: str, data: dict) -> None:
        with self._lock:
            self._event(name, data)

    def write_text(self, name: str, value: str) -> Path:
        target = self.directory / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(value, encoding="utf-8")
        self.event("artifact_written", {"path": name})
        return target

    @property
    def active_stage(self):
        return getattr(self._local, "stage", None)

    @active_stage.setter
    def active_stage(self, value):
        self._local.stage = value

    def _event(self, name: str, data: dict) -> None:
        if self.active_stage:
            data = {"stage": self.active_stage, **data}
        with (self.directory / "events.jsonl").open("a") as stream:
            stream.write(
                json.dumps(
                    {
                        "time": datetime.now(UTC).isoformat(),
                        "event": name,
                        "data": data,
                    },
                    sort_keys=True,
                )
                + "\n"
            )

    @contextmanager
    def stage(self, name: str, *, parents: list[str] | None = None):
        start = time.monotonic()
        previous = self.active_stage
        self.active_stage = name
        self.event(
            "stage_started",
            {"stage": name, **({"parents": parents} if parents is not None else {})},
        )
        try:
            yield
        except BaseException as exc:
            # Do not serialize provider error bodies: they may contain credentials.
            self.event("stage_failed", {"stage": name, "error_type": type(exc).__name__})
            raise
        else:
            self.event("stage_completed", {"stage": name, "seconds": time.monotonic() - start})
        finally:
            self.active_stage = previous

    def seal(self) -> None:
        entries = {}
        for path in sorted(self.directory.rglob("*")):
            if path.is_file() and path != self.directory / "manifest.json":
                entries[str(path.relative_to(self.directory))] = {
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "bytes": path.stat().st_size,
                }
        self.write("manifest.json", {"artifacts": entries})


def environment() -> dict:
    packages = {
        name: version(name) for name in ["numpy", "scipy", "ephem", "pypdf", "omnigent", "anyjev"]
    }
    try:
        packages["mlx-lm"] = version("mlx-lm")
    except PackageNotFoundError:
        packages["mlx-lm"] = None
    try:
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        revision = "unavailable"
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "git_revision": revision,
        "code_sha256": code_digest(),
        "packages": packages,
    }


def verify_artifacts(directory: Path) -> list[str]:
    manifest = json.loads((directory / "manifest.json").read_text())
    failures = []
    for name, item in manifest["artifacts"].items():
        path = (directory / name).resolve()
        if not path.is_relative_to(directory.resolve()):
            failures.append(f"Unsafe manifest path: {name}")
        elif not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != item["sha256"]:
            failures.append(f"Hash mismatch: {name}")
    if not failures and "report.json" in manifest["artifacts"]:
        from .repository_audit import verify_repository_outputs

        failures.extend(
            verify_repository_outputs(
                directory,
                json.loads((directory / "report.json").read_text()),
                manifest["artifacts"],
            )
        )
        from .process_visualization import verify_process_outputs

        report = json.loads((directory / "report.json").read_text())
        failures.extend(verify_process_outputs(directory, report, manifest["artifacts"]))
    return failures
