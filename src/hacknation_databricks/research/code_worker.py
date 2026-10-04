"""Trusted child entry point, invoked only inside an active Omnigent OS sandbox."""

import contextlib
import ctypes
import importlib.util
import json
import os
import resource
import subprocess
import sys
from pathlib import Path


def main():
    request = json.loads(Path(sys.argv[1]).read_text())
    seconds = request["timeout"]
    resource.setrlimit(resource.RLIMIT_CPU, (seconds, seconds))
    resource.setrlimit(resource.RLIMIT_FSIZE, (8_000_000, 8_000_000))
    resource.setrlimit(resource.RLIMIT_NOFILE, (128, 128))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    # RLIMIT_AS is usable on Linux; macOS does not offer an equivalent reliable
    # per-process resident-memory cap. This gap is explicitly recorded.
    if sys.platform == "linux":
        resource.setrlimit(resource.RLIMIT_AS, (2_147_483_648, 2_147_483_648))
        resource.setrlimit(resource.RLIMIT_NPROC, (256, 256))
    repository = Path(request["repository"]).resolve()
    work = Path(request["work"]).resolve()
    sys.path.insert(0, str(repository))
    sys.path.insert(0, str(repository / "src"))
    visited = set()

    def trace(frame, event, arg):
        if event == "call":
            name = frame.f_code.co_filename
            prefix = str(repository) + os.sep
            if name.startswith(prefix):
                visited.add(name[len(prefix) :])

    library, loaded = None, []
    if request["c_sources"]:
        library = work / ("experiment.dylib" if sys.platform == "darwin" else "experiment.so")
        command = [
            request["compiler"],
            "-std=c17",
            "-O2",
            "-fPIC",
            "-shared",
            *request["c_sources"],
            "-I",
            str(repository),
            "-lm",
            "-o",
            str(library),
        ]
        compiled = subprocess.run(command, stdout=sys.stderr, stderr=sys.stderr, timeout=seconds)
        if compiled.returncode:
            raise ValueError("C compilation failed")
        original = ctypes.CDLL

        def load(name, *args, **kwargs):
            result = original(name, *args, **kwargs)
            if Path(str(name)).resolve() == library:
                loaded.append(str(library.name))
            return result

        ctypes.CDLL = load
    os.chdir(work)
    sys.setprofile(trace)
    with contextlib.redirect_stdout(sys.stderr):
        spec = importlib.util.spec_from_file_location("paper_experiment", request["implementation"])
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        trials = []
        for job in request["jobs"]:
            value = module.simulate(
                job["parameters"], job["seed"], str(library) if library else None
            )
            trials.append({**job, "output": value})
    sys.setprofile(None)
    print(
        json.dumps(
            {
                "trials": trials,
                "repository_calls": sorted(visited),
                "compiled_library_loaded": bool(loaded),
            },
            allow_nan=False,
        )
    )


if __name__ == "__main__":
    main()
