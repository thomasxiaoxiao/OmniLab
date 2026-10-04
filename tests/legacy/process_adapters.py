"""Scientific process adapters; the output contract and player have no paper IDs."""

import csv
import io
import math

import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import connected_components

from .astrosat_experiments import transit_geometry
from .simulation import lattice, measure


def rows(read, name):
    return csv.DictReader(io.StringIO(read(name).decode("utf-8")))


def boolean(value):
    if value not in ("True", "False"):
        raise ValueError("Invalid recorded boolean")
    return value == "True"


def line(x, y, x2, y2, color, start=0, *, arrow=False):
    return dict(kind="arrow" if arrow else "line", x=x, y=y, x2=x2, y2=y2, color=color, start=start)


def circle(x, y, radius, color, start=0, *, filled=False):
    return dict(kind="circle", x=x, y=y, radius=radius, color=color, start=start, filled=filled)


def percolation_process(bundle, read):
    recipe = bundle["recipe"]
    sizes = [int(c["scenario"]) for c in bundle["checks"]] or bundle["sizes"]
    size = min(sizes)
    prefix = bundle["recipe_artifact"].rsplit("/", 1)[0]
    raw_path = prefix + "/trials.csv"
    selected = {}
    if bundle["batch"] is not None:
        for row in rows(read, raw_path):
            if int(row["size"]) == size:
                selected.setdefault(row["arm"], (row, raw_path))
    else:
        for row in rows(read, raw_path):
            if int(row["size"]) == size:
                selected.setdefault("treatment", (row, raw_path))
        for row in rows(read, "baseline/trials.csv"):
            if int(row["size"]) == size and row["model"] == recipe["control"]:
                selected.setdefault("control", (row, "baseline/trials.csv"))
    worlds, inputs = {}, []
    last = 24
    for arm, key, color in (
        ("control", "original", "control"),
        ("treatment", "proposed", "proposed"),
    ):
        row, path = selected[arm]
        model = recipe["control"] if arm == "control" else recipe["model"]
        mode = "bond" if arm == "control" else recipe["mode"]
        if row["model"] != model or row["mode"] != mode or float(row["p"]) != recipe["p"]:
            raise ValueError("Recorded realization does not match the archived recipe")
        graph = lattice(size, model, float(row["p"]), int(row["seed"]), mode)
        measurement = measure(graph)
        for field in ("wrap_x", "wrap_y", "wrap_any", "wrap_both"):
            if measurement[field] != boolean(row[field]):
                raise ValueError("Percolation replay disagrees with recorded topology")
        if measurement["largest"] != int(row["largest"]):
            raise ValueError("Percolation replay disagrees with recorded component size")
        inputs.append({"artifact": path, "arm": arm, "record": row})
        rng = np.random.default_rng(int(row["seed"]))
        occupied = np.flatnonzero(graph.occupied)
        starts = np.zeros(size * size, dtype=int)
        if mode == "site" and len(occupied):
            starts[rng.permutation(occupied)] = 1 + np.arange(len(occupied)) * last // len(occupied)
        edge_starts = np.zeros(len(graph.edges), dtype=int)
        if len(edge_starts):
            edge_starts[rng.permutation(len(edge_starts))] = 1 + np.arange(
                len(edge_starts)
            ) * last // len(edge_starts)
        if mode == "site":
            edge_starts = np.max(starts[graph.edges], axis=1)
        # Recompute strong connectivity as bonds/sites are activated. These are
        # deterministic views of the recorded graph, not additional trials.
        highlights = [[] for _ in range(size * size)]
        frames = []
        for step in range(last + 1):
            active_edges = graph.edges[edge_starts <= step]
            active_sites = occupied[starts[occupied] <= step]
            matrix = csr_matrix(
                (np.ones(len(active_edges)), (active_edges[:, 0], active_edges[:, 1])),
                shape=(size * size, size * size),
            )
            _, labels = connected_components(matrix, directed=True, connection="strong")
            counts = np.bincount(labels[active_sites])
            largest = int(counts.max(initial=0))
            if largest:
                component = int(counts.argmax())
                for node in active_sites[labels[active_sites] == component]:
                    highlights[node].append(step)
            frames.append(
                {
                    "caption": f"Step {step}/{last} · {len(active_edges)} arcs · "
                    f"{len(active_sites)} occupied sites · largest SCC: {largest}"
                }
            )
        if largest != measurement["largest"]:
            raise ValueError("Animated connectivity does not converge to the recorded graph")
        geometry = []
        for i, ((u, v), (dx, dy)) in enumerate(zip(graph.edges, graph.steps, strict=True)):
            start = int(max(starts[u], starts[v])) if mode == "site" else int(edge_starts[i])
            x, y = int(u % size), int(u // size)
            tx, ty = x + int(dx), y + int(dy)
            if 0 <= tx < size and 0 <= ty < size:
                geometry.append(line(x, y, tx, ty, color, start, arrow=True))
            else:
                # Periodic arcs exit and enter the seam, never cross the entire panel.
                geometry.append(line(x, y, x + dx / 2, y + dy / 2, color, start, arrow=True))
                vx, vy = int(v % size), int(v // size)
                geometry.append(line(vx - dx / 2, vy - dy / 2, vx, vy, color, start, arrow=True))
        geometry.extend(
            {
                **circle(int(u % size), int(u // size), 0.08, color, int(starts[u]), filled=True),
                "highlight": highlights[u],
            }
            for u in occupied
        )
        worlds[key] = {
            "label": "Original · local control" if arm == "control" else "Proposed · follow-up",
            "description": f"{model} / {mode}; L={size}; p={recipe['p']}; seed={row['seed']}. "
            f"Final horizontal SCC wrapping: {measurement['wrap_x']}; "
            f"largest SCC: {measurement['largest']} sites.",
            "geometry": geometry,
            "frames": frames,
        }
    return {
        "title": "Percolation · formation of the sampled directed lattices",
        "description": "Arrows show activated connections; seam arrows wrap around the periodic "
        "lattice. Orange nodes highlight a largest strongly connected component (SCC), "
        "recomputed at every construction step. Compare how connectivity emerges.",
        "x_label": "Lattice x (sites)",
        "y_label": "Lattice y (sites)",
        "timeline_label": "Construction step",
        "times": list(range(last + 1)),
        "bounds": [-0.6, size - 0.4, -0.6, size - 0.4],
        "selection": "First recorded trial in each arm at the smallest measured size, from "
        "this checkpoint's batch (sequential control from baseline). No outcome-based selection.",
        "limitations": "Seed replay of two recorded configurations, not new statistical evidence. "
        "The seeded reveal order illustrates lattice construction at fixed p; it is not physical "
        "time or a sweep in p. Site steps add occupied sites and their incident arcs. "
        "Wrapping is the archived SCC winding measurement, not a visual border-touch test. "
        "Aggregate rates and uncertainty remain in the numerical comparison.",
        "replayed_trials": 2,
        "inputs": inputs,
        **worlds,
    }


def astrosat_process(bundle, read):
    recipe = bundle["recipe"]
    raw_path = bundle["recipe_artifact"].rsplit("/", 1)[0] + "/trials.csv"
    row = next(rows(read, raw_path))
    # These are the parameters actually used by the existing transit kernel.
    if recipe["altitude_km"] != 335.0 or recipe["cross_track_sigma_km"] != 0.5:
        raise ValueError("No verified geometry adapter for the recorded parameters")
    g = transit_geometry(recipe["altitude_km"], recipe["cross_track_sigma_km"])
    radius = recipe["field_diameter_deg"] / 2
    guard = radius + recipe["margin_sigma"] * g["cross_track_deg"]
    speed = g["angular_speed_deg_s"]
    ny, nt, ty, tt = (
        float(row[k]) for k in ("nominal_y_deg", "nominal_time_s", "true_y_deg", "true_time_s")
    )
    half_chord = math.sqrt(max(0, radius**2 - ty**2)) / speed
    truth = (
        abs(ty) <= radius and tt + half_chord >= 0 and tt - half_chord <= recipe["exposure_seconds"]
    )
    timing = (
        -recipe["timing_window_seconds"]
        <= nt
        <= (recipe["exposure_seconds"] + recipe["timing_window_seconds"])
    )
    if truth != boolean(row["truth"]):
        raise ValueError("Recorded transit truth disagrees with the geometry")
    extent = max(guard, abs(ny), abs(ty)) * 1.2
    times = np.linspace(min(nt, tt) - extent / speed, max(nt, tt) + extent / speed, 61).tolist()
    x_extent = abs(nt - tt) * speed + extent
    worlds = {}
    for key, threshold, color, field in (
        ("original", radius, "control", "control_alert"),
        ("proposed", guard, "proposed", "treatment_alert"),
    ):
        alert = timing and abs(ny) <= threshold
        if alert != boolean(row[field]):
            raise ValueError("Recorded alert disagrees with the archived parameters")
        worlds[key] = {
            "label": "Original · nominal alert"
            if key == "original"
            else "Proposed · guarded alert",
            "description": f"Cross-track alert boundary ±{threshold:.3f}°. "
            f"Candidate alert: {alert}; true transit during exposure: {truth}. "
            f"Same ±{recipe['timing_window_seconds']:g} s timing window in both worlds.",
            "geometry": [
                circle(0, 0, radius, "field"),
                line(-x_extent, threshold, x_extent, threshold, color),
                line(-x_extent, -threshold, x_extent, -threshold, color),
                line(-x_extent, ny, x_extent, ny, "control"),
                line(-x_extent, ty, x_extent, ty, "truth"),
            ],
            "frames": [
                {
                    "caption": f"t={t:.3f} s · "
                    + (
                        "during exposure"
                        if 0 <= t <= recipe["exposure_seconds"]
                        else "outside exposure"
                    ),
                    "glyphs": [
                        circle(speed * (t - nt), ny, extent * 0.04, "control", filled=True),
                        circle(speed * (t - tt), ty, extent * 0.04, "truth", filled=True),
                    ],
                }
                for t in times
            ],
        }
    return {
        "title": "Orbit prediction comparison · local sky transit",
        "description": "Blue: nominal predicted track. Orange: simulated true track. "
        "Circle: observed field. Horizontal boundaries: candidate alert region. "
        "The proposal widens the alert region; it does not change the orbit prediction.",
        "x_label": "Along-track angle (deg)",
        "y_label": "Cross-track angle (deg)",
        "timeline_label": "Time relative to exposure start (s)",
        "times": times,
        "bounds": [-x_extent, x_extent, -extent, extent],
        "selection": "First recorded candidate of the checkpoint batch, regardless of outcome: "
        f"{row['scenario']} scenario, trial {row['trial']}, seed {row['seed']}.",
        "limitations": "Synthetic straight-line local transit under archived circular-orbit "
        "speed and Gaussian error assumptions. Not an SGP4 trajectory, measured satellite orbit, "
        "improved orbit estimator, or observational validation. This single candidate illustrates "
        "the mechanism; aggregate missed transits, false alerts and uncertainty "
        "are reported separately.",
        "replayed_trials": 0,
        "inputs": [{"artifact": raw_path, "record": row}],
        **worlds,
    }


# Register a reviewed scientific adapter here. No UI, export, or gate changes are
# needed for another paper/scenario: return the same ProcessComparison contract.
PROCESS_ADAPTERS = {"percolation": percolation_process, "astrosat": astrosat_process}


def build_legacy_process(bundle, read, *, run_id):
    from hacknation_databricks.research.process_visualization import build_process

    return build_process(bundle, read, run_id=run_id, adapters=PROCESS_ADAPTERS)
