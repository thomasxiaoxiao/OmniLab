"""Bounded Python/C tool dispatched from structured Omnigent specialist handoffs."""

import hashlib
import json
import os
import selectors
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from pydantic import Field, model_validator

from .process_visualization import DataContract
from .repository_source import safe_repo_path

CODE_CAPABILITY = {
    "languages": ["Python 3.12", "C17 shared library via ctypes"],
    "libraries": [
        "Python standard library",
        "numpy",
        "scipy",
        "ephem==4.2.1",
        "pinned repository source",
    ],
    "interface": "simulate(parameters: dict, seed: int, library: str | None) -> "
    "{metric: float, times: list[float], values: list[float], scene?: recorded scene data, "
    "measurements?: additional computed results and metadata}",
    "purpose": "Offline numerical simulations, algorithms, and parameter sweeps "
    "grounded in the submitted paper and repository.",
    "limits": {
        "network": False,
        "output_bytes": 32_000_000,
        "writable": "disposable scratch only",
        "package_installation": False,
        "shell_commands_from_agent": False,
    },
    "required": "Call repository Python functions or compile and load repository C sources. "
    "Return recorded process samples on a strictly increasing "
    "time/step axis, plus agent-designed scene data when meaningful; no HTML or fabricated states. "
    "Flat computed results are valid. Repeating an "
    "identical deterministic input with different unused seeds does not create "
    "independent evidence.",
}


def paper_implementation(manifest):
    """An explicit paper-only input has no repository identity or source files."""
    if manifest.get("origin") != "paper_implementation":
        return False
    if manifest["url"] or manifest["commit"] or manifest["files"]:
        raise ValueError("Paper implementation cannot claim a repository identity")
    return True


def code_capability(paper_only=False):
    if not paper_only:
        return CODE_CAPABILITY
    return {
        **CODE_CAPABILITY,
        "libraries": CODE_CAPABILITY["libraries"][:-1],
        "purpose": "Implement a scoped numerical experiment from the supplied paper's "
        "equations or algorithm. There is no author repository in this run.",
        "required": "Use only the supplied paper and supporting evidence; disclose assumptions "
        "and omitted physics/data. Return actual computed samples and an "
        "evidence-grounded scene on a strictly "
        "increasing time/step axis. No fabricated results or claims of author-code reproduction.",
    }


class SimulationSample(DataContract):
    metric: float
    times: list[float] = Field(min_length=2, max_length=120)
    values: list[float] = Field(min_length=2, max_length=120)
    # Scene failures are reported separately and cannot erase valid numerical results.
    scene: dict | None = None
    measurements: dict | None = None

    @model_validator(mode="after")
    def coherent(self):
        if len(self.times) != len(self.values) or any(
            b <= a for a, b in zip(self.times, self.times[1:], strict=False)
        ):
            raise ValueError("Process samples require matching values and increasing steps")
        return self


def sandbox_policy(inputs, scratch):
    from omnigent.inner.datamodel import OSEnvSandboxSpec, OSEnvSpec
    from omnigent.sandbox import resolve_sandbox

    if sys.platform not in {"darwin", "linux"}:
        raise OSError("Repository execution requires Omnigent Seatbelt or bubblewrap")
    backend = "darwin_seatbelt" if sys.platform == "darwin" else "linux_bwrap"
    # Only the isolated inputs, Python installation and standard compiler SDK are readable.
    read_paths = [
        str(inputs),
        str(Path(sys.prefix).resolve()),
        str(Path(sys.base_prefix).resolve()),
    ]
    if sys.platform == "darwin":
        read_paths += [
            "/Library/Developer/CommandLineTools",
            "/Applications/Xcode.app/Contents/Developer",
        ]
    policy = resolve_sandbox(
        OSEnvSpec(
            sandbox=OSEnvSandboxSpec(
                type=backend,
                read_paths=read_paths,
                write_paths=[str(scratch)],
                allow_network=False,
                cwd_allow_hidden=[],
                cwd_hidden_scan_recursive=False,
                env_passthrough=[],
            )
        ),
        inputs,
    )
    if not policy.active or policy.backend_type not in {"darwin_seatbelt", "linux_bwrap"}:
        raise OSError("A real OS sandbox is required; execution was not attempted")
    return policy


def run_bounded(argv, *, cwd, env, timeout, output_limit=32_000_000):
    """Drain both pipes with a combined byte limit and kill the process group on every exit."""
    process = subprocess.Popen(
        argv,
        cwd=cwd,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    streams = {"stdout": bytearray(), "stderr": bytearray()}
    reason, start = None, time.monotonic()
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ, "stdout")
            selector.register(process.stderr, selectors.EVENT_READ, "stderr")
            while selector.get_map():
                if time.monotonic() - start >= timeout:
                    reason = "timeout"
                    break
                for key, _ in selector.select(timeout=min(0.1, timeout)):
                    chunk = os.read(key.fileobj.fileno(), 65536)
                    if not chunk:
                        selector.unregister(key.fileobj)
                    else:
                        if sum(map(len, streams.values())) + len(chunk) > output_limit:
                            reason = "output_limit"
                            break
                        streams[key.data].extend(chunk)
                if reason:
                    break
            if not reason:
                try:
                    process.wait(timeout=max(0.01, timeout - (time.monotonic() - start)))
                except subprocess.TimeoutExpired:
                    reason = "timeout"
    finally:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()
        process.stdout.close()
        process.stderr.close()
    return {
        **{k: bytes(v).decode("utf-8", errors="replace") for k, v in streams.items()},
        "returncode": process.returncode,
        "failure": reason,
        "seconds": time.monotonic() - start,
    }


def execute_code(store, implementation, manifest, jobs, *, stage, timeout):
    """Never execute in the repository checkout or expose authentication to the child."""
    from omnigent.sandbox import get_backend

    # Reject syntax errors before launching a compiler or sandbox process.
    compile(implementation.python_code, "experiment.py", "exec")
    paper_only = paper_implementation(manifest)
    if not paper_only and not implementation.repository_files:
        raise ValueError("Repository experiments must use pinned source files")
    inventory = {item["path"]: item for item in manifest["files"]}
    for name in implementation.repository_files + implementation.c_repository_files:
        safe_repo_path(name)
        if name not in inventory:
            raise ValueError("Implementation references code outside the pinned repository")
    if any(not name.endswith(".c") for name in implementation.c_repository_files):
        raise ValueError("Only .c source files can be compiled")
    compiler = shutil.which("cc")
    if (implementation.c_code or implementation.c_repository_files) and not compiler:
        raise OSError("A C compiler is required for this implementation")
    with tempfile.TemporaryDirectory(prefix="paper-code-") as temporary:
        root = Path(temporary).resolve()
        inputs, scratch = root / "inputs", root / "scratch"
        inputs.mkdir()
        scratch.mkdir()
        repository = inputs / "repository"
        repository.mkdir()
        for name, item in inventory.items():
            path = store.directory / "repository/source" / name
            raw = path.read_bytes()
            if hashlib.sha256(raw).hexdigest() != item["sha256"]:
                raise ValueError("Pinned repository content changed before execution")
            dest = repository / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(raw)
        code = inputs / "experiment.py"
        code.write_text(implementation.python_code)
        c_sources = [str(repository / name) for name in implementation.c_repository_files]
        if implementation.c_code:
            c_path = inputs / "experiment.c"
            c_path.write_text(implementation.c_code)
            c_sources.append(str(c_path))
        worker = inputs / "worker.py"
        worker.write_bytes(Path(__file__).with_name("code_worker.py").read_bytes())
        request = {
            "jobs": jobs,
            "repository": str(repository),
            "work": str(scratch),
            "implementation": str(code),
            "c_sources": c_sources,
            "compiler": compiler,
            "timeout": max(1, int(timeout)),
            "trace_repository": bool(manifest["files"]),
        }
        request_path = inputs / "request.json"
        request_path.write_text(json.dumps(request, allow_nan=False))
        policy = sandbox_policy(inputs, scratch)
        argv = get_backend(policy.backend_type).wrap_launcher_argv(
            [sys.executable, "-I", str(worker), str(request_path)], policy, inputs
        )
        env = {
            "PATH": "/usr/bin:/bin",
            "TMPDIR": str(scratch),
            "PYTHONDONTWRITEBYTECODE": "1",
            "OPENBLAS_NUM_THREADS": "1",
            "OMP_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
        }
        execution = run_bounded(argv, cwd=inputs, env=env, timeout=timeout)
        audit = {
            **execution,
            "backend": policy.backend_type,
            "omnigent_version": "0.16.0",
            "capability": code_capability(paper_only),
            "code_origin": "paper_implementation" if paper_only else "repository",
            "jobs": jobs,
            "source_sha256": manifest["source_sha256"],
            "repository_commit": manifest["commit"],
            "memory_limit_bytes": 2_147_483_648 if sys.platform == "linux" else None,
            "memory_limit_note": "macOS has no enforced resident-memory cap"
            if sys.platform == "darwin"
            else "RLIMIT_AS",
            "python_sha256": hashlib.sha256(implementation.python_code.encode()).hexdigest(),
            "c_sha256": hashlib.sha256(implementation.c_code.encode()).hexdigest(),
        }
        store.write(f"{stage}/execution.json", audit)
        if execution["failure"] or execution["returncode"]:
            reason = execution["failure"] or f"exit code {execution['returncode']}"
            raise RuntimeError(f"Sandbox execution failed ({reason}); see saved execution.json")
        result = json.loads(execution["stdout"])
        if len(result["trials"]) != len(jobs):
            raise ValueError("Execution omitted requested simulation jobs")
        for job, trial in zip(jobs, result["trials"], strict=True):
            if {k: trial[k] for k in job} != job:
                raise ValueError("Simulation changed its parameters or seed")
            trial["output"] = SimulationSample.model_validate(trial["output"]).model_dump(
                exclude_none=True
            )
        observed = set(result["repository_calls"]) & set(implementation.repository_files)
        if (
            not paper_only
            and not observed
            and not (implementation.c_repository_files and result["compiled_library_loaded"])
        ):
            raise ValueError("No use of the pinned repository implementation was observed")
        store.write(f"{stage}/trials.json", result)
        return result
