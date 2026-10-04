"""Validate scenes emitted by executed agent code; never reconstruct scientific states."""

from pydantic import Field, model_validator

from .process_visualization import DataContract, Frame, Glyph, checked_process


class SimulationScene(DataContract):
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(min_length=1, max_length=2000)
    x_label: str = Field(min_length=1, max_length=100)
    y_label: str = Field(min_length=1, max_length=100)
    timeline_label: str = Field(min_length=1, max_length=200)
    bounds: list[float] = Field(min_length=4, max_length=4)
    geometry: list[Glyph] = Field(default_factory=list, max_length=4096)
    frames: list[Frame] = Field(min_length=2, max_length=120)

    @model_validator(mode="after")
    def ordered_bounds(self):
        if self.bounds[0] >= self.bounds[1] or self.bounds[2] >= self.bounds[3]:
            raise ValueError("Scene bounds must be ordered")
        return self


def agent_process(result, plan, *, provenance, artifact):
    """First planned paired seed, unchanged recorded geometry, shared coordinate extent."""
    rows = [next(r for r in result["trials"] if r["arm"] == arm) for arm in ("control", "proposed")]
    if any(not r["output"].get("scene") for r in rows):
        return {
            "status": "unavailable",
            "reason": "The executed agent code did not emit a scene for both arms. Numerical "
            "results are retained; no replacement visualization was generated.",
        }
    try:
        scenes = [SimulationScene.model_validate(r["output"]["scene"]).model_dump() for r in rows]
        times = rows[0]["output"]["times"]
        if rows[1]["output"]["times"] != times or any(
            len(s["frames"]) != len(times) for s in scenes
        ):
            raise ValueError("Scene frames must match the recorded simulation steps")
        for key in ("x_label", "y_label", "timeline_label"):
            if scenes[0][key] != scenes[1][key]:
                raise ValueError("Paired scenes require matching coordinate units")
        bounds = [
            min(s["bounds"][0] for s in scenes),
            max(s["bounds"][1] for s in scenes),
            min(s["bounds"][2] for s in scenes),
            max(s["bounds"][3] for s in scenes),
        ]
        labels = ("Control", "Proposed")
        if getattr(plan, "comparison", None):
            labels = (
                "Baseline · " + plan.comparison.baseline_label,
                "Proposed · " + plan.comparison.proposed_label,
            )
        worlds = {
            name: {
                "label": label,
                "description": scene["description"],
                "geometry": scene["geometry"],
                "frames": scene["frames"],
            }
            for name, label, scene in zip(("original", "proposed"), labels, scenes, strict=True)
        }
        process = checked_process(
            {
                "schema_version": "simulation-process/v2",
                "title": scenes[0]["title"],
                "description": "Scene states produced by this run's executed agent-written"
                " experiment "
                "code.",
                **{k: scenes[0][k] for k in ("x_label", "y_label", "timeline_label")},
                "bounds": bounds,
                "times": times,
                **worlds,
                "selection": "First preregistered paired seed. Every other trial remains"
                " in the raw "
                "results.",
                "limitations": "Agent-designed simulation; geometry is recorded output, not "
                "independently validated physical truth. " + " ".join(plan.limitations),
                "replayed_trials": 0,
                "inputs": [{"artifact": artifact, "seed": rows[0]["seed"]}],
                "provenance": provenance,
            }
        )
        return {"status": "ready", "process": process}
    except (ValueError, TypeError, KeyError):
        return {
            "status": "invalid",
            "reason": "The agent-emitted scene failed its data contract. Raw output and "
            "numerical results are retained; no substitute was generated.",
        }
