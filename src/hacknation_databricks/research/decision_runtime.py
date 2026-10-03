"""Pinned local open-weight decision runtime; no model-generated text or tools."""

import hashlib
import json
import os
import selectors
import subprocess
import sys
import time
from importlib.util import find_spec
from pathlib import Path

from .agents import AgentUnavailable

MODEL_ID = "mlx-community/Qwen3-4B-Instruct-2507-4bit"
MODEL_REVISION = "50d427756c6b1b2fe0c0a10f67fbda1fc8e82c1b"
MAX_DECISION_TOKENS = 4096


def model_directory() -> Path:
    return Path(os.environ.get("RESEARCH_DECISION_MODEL_DIR", "data/models/qwen3-4b-decision"))


def runtime_status() -> dict:
    installed = all(find_spec(name) is not None for name in ("anyjev", "mlx_lm"))
    present = (model_directory() / "decision-model.json").is_file()
    return {
        "installed": installed,
        "model_present": present,
        "ready": installed and present,
        "model": MODEL_ID,
        "revision": MODEL_REVISION,
    }


def prepare_model() -> Path:
    """Explicit setup command. Downloads data files only, never remote Python code."""
    from huggingface_hub import snapshot_download

    root = model_directory()
    snapshot_download(
        MODEL_ID,
        revision=MODEL_REVISION,
        local_dir=root,
        token=False,
        allow_patterns=["*.json", "*.safetensors", "*.txt", "*.jinja"],
        max_workers=2,
    )
    files = {}
    for path in sorted(root.iterdir()):
        if path.is_file() and path.name != "decision-model.json":
            with path.open("rb") as stream:
                files[path.name] = {
                    "sha256": hashlib.file_digest(stream, "sha256").hexdigest(),
                    "bytes": path.stat().st_size,
                }
    (root / "decision-model.json").write_text(
        json.dumps(
            {
                "model": MODEL_ID,
                "revision": MODEL_REVISION,
                "files": files,
            },
            indent=2,
        )
        + "\n"
    )
    return root


def verify_model() -> dict:
    root = model_directory()
    try:
        manifest = json.loads((root / "decision-model.json").read_text())
        if manifest["model"] != MODEL_ID or manifest["revision"] != MODEL_REVISION:
            raise ValueError("Model pin changed")
        for name in ("model.safetensors", "config.json", "tokenizer.json", "tokenizer_config.json"):
            if name not in manifest["files"]:
                raise ValueError("Model manifest is incomplete")
        for name, item in manifest["files"].items():
            path = root / name
            if Path(name).name != name or path.is_symlink() or path.stat().st_size != item["bytes"]:
                raise ValueError("Invalid model file")
            with path.open("rb") as stream:
                if hashlib.file_digest(stream, "sha256").hexdigest() != item["sha256"]:
                    raise ValueError("Model checksum mismatch")
        return manifest
    except (OSError, ValueError, KeyError, TypeError):
        raise AgentUnavailable(
            "Local decision model missing or invalid. Run research prepare-model."
        ) from None


class DecisionProcess:
    """A persistent, killable inference process; no HTTP service or arbitrary tool surface."""

    def __init__(self, deadline: float, timeout: int):
        if not runtime_status()["installed"]:
            raise AgentUnavailable(
                "Install the pinned runtime with uv sync on an Apple Silicon Mac"
            )
        self.manifest = verify_model()
        self.deadline, self.timeout = deadline, timeout
        environment = {
            **os.environ,
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "TOKENIZERS_PARALLELISM": "false",
        }
        self.process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "hacknation_databricks.research.decision_worker",
                str(model_directory().resolve()),
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
            env=environment,
        )
        self.selector = selectors.DefaultSelector()
        self.selector.register(self.process.stdout, selectors.EVENT_READ)

    def decide(self, state: dict, question: str, choices: dict[str, str]) -> dict:
        if not 2 <= len(choices) <= 8 or any(not isinstance(k, str) for k in choices):
            raise ValueError("A decision needs 2–8 named options")
        request = {"state": state, "question": question, "choices": choices}
        body = json.dumps(request, allow_nan=False)
        if len(body) > 20000:
            raise ValueError("Decision context exceeds its explicit budget; nothing truncated")
        timeout = min(self.timeout, self.deadline - time.monotonic())
        if timeout <= 0:
            raise TimeoutError("Decision deadline exhausted")
        try:
            self.process.stdin.write(body + "\n")
            self.process.stdin.flush()
            if not self.selector.select(timeout):
                self.close()
                raise TimeoutError("Local decision inference timed out")
            line = self.process.stdout.readline(1000000)
            result = json.loads(line)
            if "error" in result:
                raise AgentUnavailable("Local decision inference failed: " + result["error"])
            probabilities = result["probabilities"]
            if set(probabilities) != set(choices) or result["answer"] not in choices:
                raise ValueError("Model returned an undeclared choice")
            if (
                any(type(p) is not float or not 0 <= p <= 1 for p in probabilities.values())
                or abs(sum(probabilities.values()) - 1) > 1e-6
            ):
                raise ValueError("Invalid model distribution")
            if (
                result["answer"] != max(probabilities, key=probabilities.get)
                or result["level"] != "L0"
                or result["calibrated"] is not False
                or result["model"] != MODEL_ID
                or result["revision"] != MODEL_REVISION
                or result["usage"]["generated_tokens"] != 0
                or result["usage"]["prefills"] != len(choices)
            ):
                raise ValueError("Decision runtime violated its inference contract")
            return result
        except (BrokenPipeError, json.JSONDecodeError, KeyError) as exc:
            raise AgentUnavailable(f"Decision worker unavailable ({type(exc).__name__})") from None

    def close(self) -> None:
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=3)
        self.selector.close()
        self.process.stdin.close()
        self.process.stdout.close()
