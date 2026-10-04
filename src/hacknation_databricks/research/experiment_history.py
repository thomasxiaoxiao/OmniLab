"""Read bounded same-paper experiment history before selecting a new direction."""

import hashlib
import json
from pathlib import Path


def experiment_history(source_hash, roots, *, exclude=None, limit=12):
    entries, skipped, seen = [], [], set()
    paths = sorted(
        {p for root in roots if Path(root).is_dir() for p in Path(root).rglob("report.json")},
        key=str,
        reverse=True,
    )
    for path in paths[:300]:
        if exclude and path.parent.resolve() == Path(exclude).resolve():
            continue
        try:
            manifest = json.loads((path.parent / "manifest.json").read_text())["artifacts"]
            needed = ["report.json", "sources.json"]
            if any(
                hashlib.sha256((path.parent / name).read_bytes()).hexdigest()
                != manifest[name]["sha256"]
                for name in needed
            ):
                raise ValueError("History hash mismatch")
            report = json.loads(path.read_text())
            sources = json.loads((path.parent / "sources.json").read_text())
            if not any(s["source_id"] == "seed" and s["sha256"] == source_hash for s in sources):
                continue
            selected = report.get("selected_proposal")
            if report.get("workflow") != "repository" or not selected:
                continue
            identity = manifest["report.json"]["sha256"]
            if identity in seen:
                continue
            seen.add(identity)
            entries.append(
                {
                    "run_id": path.parent.name,
                    "directory": str(path.parent.resolve()),
                    "report_sha256": identity,
                    "status": report["status"],
                    "direction": {k: selected[k] for k in ("id", "title", "hypothesis")},
                    "completed_comparisons": len(report.get("rounds", [])),
                    "metrics": sorted({r["summary"]["metric"] for r in report.get("rounds", [])}),
                }
            )
        except (OSError, ValueError, KeyError, TypeError):
            skipped.append(str(path.parent))
    return {
        "source_sha256": source_hash,
        "roots": [str(Path(r).resolve()) for r in roots],
        "scope": "Sealed local repository-workflow reports for the identical seed-paper hash. "
        "Only report/source hashes are checked here; this is research history, not independent "
        "scientific validation. Failed attempts are identified, not promoted to accepted results. "
        "No prior code or scientific outputs are supplied as an implementation template.",
        "entries": entries[:limit],
        "omitted_matching_runs": max(0, len(entries) - limit),
        "omitted_report_paths": max(0, len(paths) - 300),
        "unreadable_or_unsealed_count": len(skipped),
    }


def reject_repeated_direction(direction, history):
    def normalized(value):
        return " ".join(value.lower().replace("_", " ").split())

    for entry in history["entries"]:
        if any(
            normalized(getattr(direction, key)) == normalized(entry["direction"][key])
            for key in ("id", "title", "hypothesis")
        ):
            raise ValueError(
                f"This direction was already analyzed in {entry['run_id']}; "
                "select a substantively different accepted scenario, not a renamed repeat"
            )
