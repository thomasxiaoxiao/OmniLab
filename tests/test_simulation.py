import numpy as np
import pytest
from legacy.simulation import Graph, lattice, measure, simulate, wilson


@pytest.mark.parametrize("model", ["manhattan", "l_lattice"])
def test_empty_full_and_degree_invariants(model):
    empty = measure(lattice(8, model, 0, 1))
    full_graph = lattice(8, model, 1, 1)
    full = measure(full_graph)
    assert empty["largest"] == 1
    assert not empty["wrap_any"]
    assert full["largest"] == 64
    assert full["wrap_both"]
    assert np.all(np.bincount(full_graph.edges[:, 0], minlength=64) == 2)
    assert np.all(np.bincount(full_graph.edges[:, 1], minlength=64) == 2)


def test_seam_crossing_is_not_wrapping():
    graph = Graph(
        4, np.array([[0, 3], [3, 0]]), np.array([[-1, 0], [1, 0]]), np.ones(16, dtype=bool)
    )
    assert measure(graph)["largest"] == 2
    assert not measure(graph)["wrap_any"]


def test_horizontal_noncontractible_cycle_wraps_only_x():
    graph = Graph(
        4,
        np.array([[0, 1], [1, 2], [2, 3], [3, 0]]),
        np.array([[1, 0]] * 4),
        np.ones(16, dtype=bool),
    )
    result = measure(graph)
    assert result["wrap_x"] and not result["wrap_y"]


def test_diagonal_winding_detects_both_axes():
    nodes = [0, 1, 5, 6, 10, 11, 15, 12, 0]
    graph = Graph(
        4,
        np.array(list(zip(nodes[:-1], nodes[1:], strict=True))),
        np.array([[1, 0], [0, 1]] * 4),
        np.ones(16, dtype=bool),
    )
    assert measure(graph)["wrap_both"]


def test_opposite_sides_in_different_sccs_do_not_wrap():
    graph = Graph(
        4, np.array([[0, 1], [1, 2], [2, 3]]), np.array([[1, 0]] * 3), np.ones(16, dtype=bool)
    )
    assert measure(graph)["largest"] == 1
    assert not measure(graph)["wrap_any"]


@pytest.mark.parametrize("seed", [0, 1, 4, 9])
def test_scc_statistics_match_independent_reachability_oracle(seed):
    graph = lattice(4, "random_diode", 0.85, seed)
    reachable = []
    for root in range(16):
        seen, todo = {root}, [root]
        while todo:
            u = todo.pop()
            for a, b in graph.edges:
                if a == u and int(b) not in seen:
                    seen.add(int(b))
                    todo.append(int(b))
        reachable.append(seen)
    components = {
        frozenset(j for j in range(16) if j in reachable[i] and i in reachable[j])
        for i in range(16)
    }
    result = measure(graph)
    assert result["largest"] == max(map(len, components))
    assert result["mean_cluster_size"] == sum(len(c) ** 2 for c in components) / 16


def test_site_percolation_preserves_empty_sites():
    result = measure(lattice(4, "manhattan", 0, 123, mode="site"))
    assert result["largest"] == result["occupied_sites"] == result["mean_cluster_size"] == 0
    assert not result["wrap_any"]


def test_bond_addition_never_splits_sccs_or_removes_wrapping():
    observations = [measure(lattice(8, "manhattan", p, 71)) for p in [0, 0.4, 0.6, 0.8, 1]]
    for key in ["largest", "wrap_x", "wrap_y"]:
        assert [r[key] for r in observations] == sorted(r[key] for r in observations)


def test_trials_replay_exactly_and_seeds_change_results():
    a = simulate("manhattan", "bond", 8, 0.7, 8, 1)
    assert a == simulate("manhattan", "bond", 8, 0.7, 8, 1)
    assert a != simulate("manhattan", "bond", 8, 0.7, 8, 2)


def test_wilson_interval_not_zero_width_at_extremes():
    assert wilson(0, 32)[1] > 0
    assert wilson(32, 32)[0] < 1
    with pytest.raises(ValueError):
        wilson(0, 0)
