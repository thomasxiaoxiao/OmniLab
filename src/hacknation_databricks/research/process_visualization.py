"""Paper-independent, data-only contract for simulated original/proposed worlds.

Adapters return geometry and states, never executable HTML or model-written code.
The same validator/player/exporter serves every scientific implementation.
"""

import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

VISUALIZATION_REQUIREMENT = {
    "required": True,
    "contract": "simulation-process/v1",
    "output": "Synchronized original and proposed simulated worlds with playable states.",
    "evidence": "Use recorded parameters, seeds and raw results; disclose selection and limits.",
    "gate": "Summary charts alone cannot complete the final output. Missing or invalid "
    "process visualization blocks completion; never invent an unsupported simulation.",
    "limits": {"frames": 120, "geometry_per_world": 60000, "export_bytes": 18000000},
}


class DataContract(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Glyph(DataContract):
    kind: Literal["line", "arrow", "circle"]
    x: float
    y: float
    x2: float = 0
    y2: float = 0
    radius: float = Field(default=0, ge=0)
    color: Literal["control", "proposed", "truth", "muted", "field"] = "muted"
    filled: bool = False
    start: int = Field(default=0, ge=0, lt=120)
    highlight: list[int] = Field(default_factory=list, max_length=120)


class Frame(DataContract):
    caption: str = Field(max_length=1000)
    glyphs: list[Glyph] = Field(default_factory=list, max_length=1024)


class World(DataContract):
    label: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=2000)
    geometry: list[Glyph] = Field(default_factory=list, max_length=60000)
    frames: list[Frame] = Field(min_length=2, max_length=120)


class ProcessComparison(DataContract):
    schema_version: Literal["simulation-process/v1"] = "simulation-process/v1"
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(min_length=1, max_length=3000)
    x_label: str = Field(min_length=1, max_length=100)
    y_label: str = Field(min_length=1, max_length=100)
    timeline_label: str = Field(min_length=1, max_length=200)
    bounds: list[float] = Field(min_length=4, max_length=4)
    times: list[float] = Field(min_length=2, max_length=120)
    original: World
    proposed: World
    selection: str = Field(min_length=1, max_length=2000)
    limitations: str = Field(min_length=1, max_length=3000)
    replayed_trials: int = Field(ge=0, le=2)
    inputs: list[dict] = Field(min_length=1, max_length=8)
    provenance: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def synchronized(self):
        x0, x1, y0, y1 = self.bounds
        if x0 >= x1 or y0 >= y1:
            raise ValueError("Both worlds require nonempty shared coordinate bounds")
        if any(b <= a for a, b in zip(self.times, self.times[1:], strict=False)):
            raise ValueError("Simulation steps must strictly increase")
        changed = False
        for world in (self.original, self.proposed):
            if len(world.frames) != len(self.times):
                raise ValueError("Original and proposed frames must share the timeline")
            glyphs = world.geometry + [g for f in world.frames for g in f.glyphs]
            if not glyphs or any(
                g.start >= len(self.times)
                or any(i < 0 or i >= len(self.times) for i in g.highlight)
                for g in glyphs
            ):
                raise ValueError("World geometry is empty or outside the timeline")
            changed |= any(g.start > 0 for g in world.geometry) or any(
                f.glyphs != world.frames[0].glyphs for f in world.frames[1:]
            )
        if not changed:
            raise ValueError("A static summary is not a simulated process")
        return self


def checked_process(value):
    process = ProcessComparison.model_validate(value)
    # Also reject non-finite values hidden in adapter input/provenance dictionaries.
    encoded = json.dumps(process.model_dump(), allow_nan=False, separators=(",", ":"))
    if len(encoded.encode()) > VISUALIZATION_REQUIREMENT["limits"]["export_bytes"]:
        raise ValueError("Process visualization exceeds its bounded export budget")
    return process.model_dump()


def build_process(bundle, read_bytes, *, run_id):
    """Bind an allowlisted adapter's states to the exact selected checkpoint inputs."""
    from .artifacts import code_digest
    from .process_adapters import PROCESS_ADAPTERS

    if not bundle.get("recipe_artifact"):
        return {"status": "unavailable", "reason": "No completed simulation inputs are available."}
    adapter = PROCESS_ADAPTERS.get(bundle.get("domain"))
    if adapter is None:
        return {"status": "unavailable", "reason": "No process adapter for this implementation."}
    evidence = {}

    def read(name):
        path = Path(name)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("Unsafe simulation input path")
        raw = read_bytes(name)
        evidence[name] = {"path": name, "sha256": hashlib.sha256(raw).hexdigest()}
        return raw

    try:
        # The adapter uses archived parameters, never the current recipe catalog.
        read(bundle["recipe_artifact"])
        process = adapter(bundle, read)
        if any(item.get("artifact") not in evidence for item in process["inputs"]):
            raise ValueError("Simulation states must reference inputs actually read")
        if len(evidence) < 2:
            raise ValueError("A recipe alone is not a simulated result")
        process["provenance"] = {
            "run_id": run_id,
            "branch_id": bundle["branch_id"],
            "checkpoint": bundle["checkpoint"],
            "batch": bundle["batch"],
            "artifacts": list(evidence.values()),
            "sources": bundle["sources"],
            "recipe": bundle["recipe"],
            "renderer_code_sha256": code_digest(),
        }
        return {"status": "ready", "process": checked_process(process)}
    except Exception as exc:
        # Preserve a terminal report even when an adapter fails. Do not echo inputs
        # or arbitrary exception bodies into exports.
        return {
            "status": "invalid",
            "reason": f"Process construction or validation failed ({type(exc).__name__}).",
        }


def enforce_process_output(report, outputs):
    """An unsuccessful run stays unsuccessful; a missing output cannot be final."""
    missing = [name for name, item in outputs.items() if item["process_status"] != "ready"]
    report["output_contract"] = {
        **VISUALIZATION_REQUIREMENT,
        "passed": not missing,
        "incomplete": missing,
    }
    report.setdefault("acceptance", {})["simulated_world_comparison"] = not missing
    if missing and (
        report.get("rounds")
        or report.get("goal", {}).get("achieved")
        or report.get("status") in {"goal_achieved", "automated_candidate", "review_complete"}
    ):
        report["scientific_status_before_output_gate"] = report["status"]
        if report.get("status") not in {
            "failed",
            "interrupted",
            "blocked_live_backend",
            "budget_exhausted",
        }:
            report["status"] = "visualization_incomplete"
        if report.get("goal", {}).get("achieved"):
            report["goal"]["achieved"] = False
        if report["status"] == "visualization_incomplete":
            report["reason"] = "Required original/proposed process output is incomplete."


def verify_process_outputs(directory, report, manifest):
    """Audit required process states and their links, including resealed omissions."""
    if "output_contract" not in report:
        return []  # Historical archives did not promise this contract.
    issues, incomplete = [], []
    outputs = report.get("comparison_artifacts", {})
    expected = {"comparison", *(f"comparisons/{r['round']:03d}" for r in report.get("rounds", []))}
    if set(outputs) != expected:
        issues.append("Required comparison output inventory is incomplete")
    for prefix, item in outputs.items():
        try:
            name = f"{prefix}/process.json"
            if item["process_data"] != name or name not in manifest:
                raise ValueError("Unsealed process data")
            envelope = json.loads((directory / name).read_text())
            if envelope["status"] != item["process_status"]:
                raise ValueError("Process status mismatch")
            if envelope["status"] != "ready":
                incomplete.append(prefix)
                continue
            process = checked_process(envelope["process"])
            html = f"{prefix}/process.html"
            if item["process_visualization"] != html or html not in manifest:
                raise ValueError("Missing playable export")
            evidence = process["provenance"]["artifacts"]
            if not evidence:
                raise ValueError("Missing simulation provenance")
            for reference in evidence:
                if manifest.get(reference["path"], {}).get("sha256") != reference["sha256"]:
                    raise ValueError("Process input hash disagrees with run manifest")
            measured = json.loads((directory / f"{prefix}/comparison.json").read_text())
            for key in ("branch_id", "checkpoint", "batch"):
                if process["provenance"][key] != measured[key]:
                    raise ValueError("Process belongs to a different result checkpoint")
            references = {r["path"] for r in evidence}
            if len(references) < 2 or any(
                i.get("artifact") not in references for i in process["inputs"]
            ):
                raise ValueError("Simulation states lack their recorded input artifacts")
        except (ValueError, KeyError, TypeError, OSError):
            issues.append(f"Invalid required process output: {prefix}")
    passed = not incomplete and not issues
    if report["output_contract"].get("passed") != passed:
        issues.append("Process output gate disagrees with saved artifacts")
    if report.get("acceptance", {}).get("simulated_world_comparison") != passed:
        issues.append("Process acceptance disagrees with saved artifacts")
    if not passed and (
        report.get("goal", {}).get("achieved")
        or report.get("status") in {"goal_achieved", "automated_candidate", "review_complete"}
    ):
        issues.append("Completion claimed without the required simulated worlds")
    if set(report["output_contract"].get("incomplete", [])) != set(incomplete):
        issues.append("Process output gate omitted incomplete comparisons")
    return issues
