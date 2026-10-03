"""Directed square-lattice percolation; no model-generated code is executed.

Definitions: Newman, Grassberger & Ziff (2026), sections II and III.D.
SCCs use SciPy's compiled graph algorithm; winding is checked using lifted
integer coordinates inside each SCC, not by touching opposite plot borders.
"""

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from math import sqrt

import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import connected_components

MODELS = {"manhattan", "l_lattice", "random_diode", "random_manhattan", "resistor_diode"}
BENCHMARKS = {"manhattan": 0.697160, "l_lattice": 0.740193, "random_diode": 1.0}
WRAPPING_TARGET = 0.75001  # Table II, one specified axis; infinite-size estimate.


@dataclass(frozen=True)
class Graph:
    size: int
    edges: np.ndarray
    steps: np.ndarray
    occupied: np.ndarray


def lattice(
    size: int,
    model: str,
    probability: float,
    seed: int,
    mode: str = "bond",
    resistor_fraction: float = 0.25,
) -> Graph:
    if size < 4 or size % 2 or model not in MODELS:
        raise ValueError("Expected an even size >= 4 and a supported lattice")
    if not 0 <= probability <= 1 or not 0 <= resistor_fraction <= 1:
        raise ValueError("Probabilities must be between zero and one")
    if mode not in {"bond", "site"}:
        raise ValueError("Unknown percolation mode")
    rng = np.random.default_rng(seed)
    ids = np.arange(size * size).reshape(size, size)
    y, x = np.indices((size, size))
    starts = np.concatenate([ids.ravel(), ids.ravel()])
    ends = np.concatenate([np.roll(ids, -1, axis=1).ravel(), np.roll(ids, -1, axis=0).ravel()])
    steps = np.repeat([[1, 0], [0, 1]], size * size, axis=0)
    if model == "manhattan":
        forward = np.concatenate([(y % 2 == 0).ravel(), (x % 2 == 0).ravel()])
    elif model == "l_lattice":
        forward = np.concatenate([((x + y) % 2 == 0).ravel(), ((x + y) % 2 == 1).ravel()])
    elif model == "random_manhattan":
        rows = rng.integers(0, 2, size).astype(bool)
        columns = rng.integers(0, 2, size).astype(bool)
        forward = np.concatenate([rows[y].ravel(), columns[x].ravel()])
    else:
        forward = rng.random(2 * size * size) < 0.5
    edges = np.column_stack([np.where(forward, starts, ends), np.where(forward, ends, starts)])
    steps = steps * np.where(forward, 1, -1)[:, None]
    occupied = np.ones(size * size, dtype=bool)
    if mode == "site":
        occupied = rng.random(size * size) < probability
        keep = occupied[edges[:, 0]] & occupied[edges[:, 1]]
    else:
        keep = rng.random(len(edges)) < probability
    edges, steps = edges[keep], steps[keep]
    if model == "resistor_diode":
        resistors = rng.random(len(edges)) < resistor_fraction
        steps = np.concatenate([steps, -steps[resistors]])
        edges = np.concatenate([edges, edges[resistors, ::-1]])
    return Graph(size, edges, steps, occupied)


def measure(graph: Graph) -> dict:
    n = graph.size**2
    edges, steps = graph.edges, graph.steps
    matrix = csr_matrix((np.ones(len(edges)), (edges[:, 0], edges[:, 1])), shape=(n, n))
    _, labels = connected_components(matrix, directed=True, connection="strong")
    sizes = np.bincount(labels[graph.occupied])
    largest = int(sizes.max(initial=0))
    occupied_count = int(graph.occupied.sum())
    mean_size = float(np.dot(sizes, sizes) / occupied_count) if occupied_count else 0.0
    # Ignore all arcs between SCCs. A path crossing a seam alone is not wrapping.
    internal = labels[edges[:, 0]] == labels[edges[:, 1]]
    adjacency: list[list[tuple[int, int, int]]] = [[] for _ in range(n)]
    for (u, v), (dx, dy) in zip(edges[internal], steps[internal], strict=True):
        adjacency[int(u)].append((int(v), int(dx), int(dy)))
    positions: dict[int, tuple[int, int]] = {}
    wrap_x, wrap_y = False, False
    for root in range(n):
        if root in positions or not adjacency[root]:
            continue
        positions[root] = (0, 0)
        stack = [root]
        while stack:
            u = stack.pop()
            ux, uy = positions[u]
            for v, dx, dy in adjacency[u]:
                point = (ux + dx, uy + dy)
                if v in positions:
                    delta_x, delta_y = point[0] - positions[v][0], point[1] - positions[v][1]
                    if delta_x % graph.size or delta_y % graph.size:
                        raise ValueError("Inconsistent lattice displacement")
                    wrap_x |= delta_x != 0
                    wrap_y |= delta_y != 0
                else:
                    positions[v] = point
                    stack.append(v)
    return {
        "largest": largest,
        "largest_fraction": largest / n,
        "mean_cluster_size": mean_size,
        "occupied_sites": occupied_count,
        "wrap_x": bool(wrap_x),
        "wrap_y": bool(wrap_y),
        "wrap_any": bool(wrap_x or wrap_y),
        "wrap_both": bool(wrap_x and wrap_y),
    }


def trial_seed(seed: int, model: str, mode: str, size: int, p: float, trial: int) -> int:
    key = json.dumps([seed, model, mode, size, p, trial], separators=(",", ":"))
    return int.from_bytes(hashlib.sha256(key.encode()).digest()[:8], "big")


def simulate(
    model: str,
    mode: str,
    size: int,
    p: float,
    trials: int,
    seed: int,
    check_budget: Callable[[], None] | None = None,
) -> list[dict]:
    rows = []
    for trial in range(trials):
        if check_budget:
            check_budget()
        actual_seed = trial_seed(seed, model, mode, size, p, trial)
        rows.append(
            {
                "model": model,
                "mode": mode,
                "size": size,
                "p": p,
                "trial": trial,
                "seed": actual_seed,
                **measure(lattice(size, model, p, actual_seed, mode)),
            }
        )
    return rows


def wilson(successes: int, n: int, z: float = 1.96) -> list[float]:
    if n <= 0:
        raise ValueError("Need observations for a confidence interval")
    p = successes / n
    denominator = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denominator
    radius = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denominator
    return [max(0.0, center - radius), min(1.0, center + radius)]


def summarize(rows: list[dict]) -> list[dict]:
    grouped: dict[tuple, list[dict]] = {}
    for row in rows:
        key = (row["model"], row["mode"], row["size"], row["p"])
        grouped.setdefault(key, []).append(row)
    summaries = []
    for (model, mode, size, p), observations in sorted(grouped.items()):
        n = len(observations)
        count = sum(row["wrap_x"] for row in observations)
        summaries.append(
            {
                "model": model,
                "mode": mode,
                "size": size,
                "p": p,
                "trials": n,
                "wrap_x": count / n,
                "wrap_x_ci95": wilson(count, n),
                "wrap_y": sum(row["wrap_y"] for row in observations) / n,
                "largest_fraction": float(np.mean([r["largest_fraction"] for r in observations])),
            }
        )
    return summaries
