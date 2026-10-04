"""The completion gate cannot be satisfied by prose, bars, or fabricated states."""

import csv
import io
import json

import pytest
from fixture_roles import run_fixture

from hacknation_databricks.research.artifacts import verify_artifacts
from hacknation_databricks.research.astrosat_experiments import ASTROSAT_RECIPES, transit_batch
from hacknation_databricks.research.cli import fixture_source
from hacknation_databricks.research.comparison import comparison_bundle
from hacknation_databricks.research.models import RunConfig
from hacknation_databricks.research.process_adapters import PROCESS_ADAPTERS
from hacknation_databricks.research.process_player import process_html
from hacknation_databricks.research.process_visualization import build_process, checked_process
from hacknation_databricks.research.simulation import simulate
from hacknation_databricks.research.sources import read_source
from hacknation_databricks.tracking import load_journal


def csv_bytes(rows):
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=rows[0])
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode()


def build(domain, recipe, rows, scenario):
    dataset = {
        "round": 1,
        "branch_id": "b1",
        "batch": 1,
        "effect": {
            "checks": [{"scenario": scenario, "control": 0.5, "treatment": 0.5, "difference": 0}]
        },
    }
    report = {"domain": domain, "rounds": [dataset]}
    prefix = "branches/b1/batches/01/"
    files = {
        prefix + "specification.json": json.dumps({"recipe": recipe}).encode(),
        prefix + "trials.csv": csv_bytes(rows),
    }
    bundle = comparison_bundle(report, {}, [], lambda name: json.loads(files[name]))
    return build_process(bundle, files.__getitem__, run_id="test")


@pytest.mark.parametrize(
    "mode,model", [("bond", "random_manhattan"), ("site", "manhattan"), ("bond", "resistor_diode")]
)
def test_percolation_states_replay_actual_sample_and_periodic_edges(mode, model):
    recipe = {"model": model, "mode": mode, "control": "manhattan", "p": 0.69716}
    rows = [
        {**r, "arm": arm}
        for arm, m, kind in [("control", "manhattan", "bond"), ("treatment", model, mode)]
        for r in simulate(m, kind, 8, recipe["p"], 2, 42)
    ]
    result = build("percolation", recipe, rows, "8")
    assert result["status"] == "ready", result
    process = result["process"]
    assert process["replayed_trials"] == 2
    assert [i["record"]["trial"] for i in process["inputs"]] == ["0", "0"]
    assert len(process["times"]) == len(process["original"]["frames"]) == 25
    for world in (process["original"], process["proposed"]):
        edges = [g for g in world["geometry"] if g["kind"] == "arrow"]
        assert edges and any(g["start"] > 0 for g in edges)
        assert all(abs(g["x"] - g["x2"]) + abs(g["y"] - g["y2"]) <= 1 for g in edges)
    for arm, key in (("control", "original"), ("treatment", "proposed")):
        expected = next(r["largest"] for r in rows if r["arm"] == arm)
        assert sum(24 in g["highlight"] for g in process[key]["geometry"]) == expected
    assert result == build("percolation", recipe, rows, "8")
    rows[0]["wrap_x"] = not rows[0]["wrap_x"]
    assert build("percolation", recipe, rows, "8")["status"] == "invalid"


def astro_process():
    recipe = ASTROSAT_RECIPES["transit_margin_2"]
    return build("astrosat", recipe, transit_batch(recipe, 8, 71, lambda: None), "fresh")["process"]


def test_transit_animates_saved_prediction_and_truth_with_actual_changed_boundary():
    process = astro_process()
    original, proposed = process["original"], process["proposed"]
    assert original["frames"] == proposed["frames"]  # Guard does not improve the orbit.
    assert original["frames"][0]["glyphs"] != original["frames"][-1]["glyphs"]
    assert proposed["geometry"][1]["y"] > original["geometry"][1]["y"]
    assert "Not an SGP4" in process["limitations"]
    row = process["inputs"][0]["record"]
    for key, field in (("original", "control_alert"), ("proposed", "treatment_alert")):
        assert f"Candidate alert: {row[field]}" in process[key]["description"]


@pytest.mark.parametrize("defect", ["missing_arm", "unsynchronized", "nan", "static", "script"])
def test_invalid_process_cannot_satisfy_output_contract(defect):
    process = astro_process()
    if defect == "missing_arm":
        del process["proposed"]
    elif defect == "unsynchronized":
        process["original"]["frames"].pop()
    elif defect == "nan":
        process["times"][0] = float("nan")
    elif defect == "static":
        for key in ("original", "proposed"):
            process[key]["frames"] = [process[key]["frames"][0]] * len(process["times"])
    else:
        process["original"]["geometry"][0]["kind"] = "script"
    with pytest.raises(ValueError):
        checked_process(process)


def test_html_treats_source_strings_as_data_not_executable_content():
    process = astro_process()
    process["title"] = '</script><script>alert("unsafe")</script>'
    page = process_html(process)
    assert process["title"] not in page
    assert "\\u003c/script\\u003e" in page
    assert 'src="http' not in page


@pytest.mark.parametrize("adaptive", [False, True])
def test_missing_adapter_blocks_success_but_preserves_results_and_seal(
    tmp_path, monkeypatch, adaptive
):
    monkeypatch.delitem(PROCESS_ADAPTERS, "astrosat" if adaptive else "percolation")
    if adaptive:
        from test_adaptive import make_run

        report = make_run(tmp_path)
    else:
        report = run_fixture(
            read_source(fixture_source()), tmp_path / "run", RunConfig(sizes=[8, 16], trials=32)
        )
    assert report["rounds"]
    assert report["status"] == "visualization_incomplete"
    assert not report["output_contract"]["passed"]
    assert not report.get("goal", {}).get("achieved")
    assert not report["acceptance"]["simulated_world_comparison"]
    assert not verify_artifacts(tmp_path / "run")
    journal = load_journal(tmp_path / "run")
    assert journal.verified, journal.issues


def test_verifier_rejects_required_export_removed_even_from_manifest(tmp_path):
    from test_adaptive import make_run

    report = make_run(tmp_path)
    assert report["output_contract"]["passed"]
    directory = tmp_path / "run"
    manifest_path = directory / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    name = "comparison/process.html"
    (directory / name).unlink()
    del manifest["artifacts"][name]
    manifest_path.write_text(json.dumps(manifest))
    assert any("process output" in issue for issue in verify_artifacts(directory))


def test_new_scenario_uses_same_contract_player_and_provenance_gate(monkeypatch):
    # A third scientific implementation supplies only data, with no changes to the
    # harness, serializer, player, or frontend. This fixture is not live evidence.
    prefix = "branches/b1/batches/01/"

    def plant_adapter(bundle, read):
        read(prefix + "trials.csv")

        def world(label, heights):
            return {
                "label": label,
                "description": "Deterministic fixture heights in cm.",
                "frames": [
                    {
                        "caption": f"Height {height} cm",
                        "glyphs": [{"kind": "line", "x": 0, "y": 0, "x2": 0, "y2": height}],
                    }
                    for height in heights
                ],
            }

        return {
            "title": "Plant growth scenario",
            "description": "Synthetic growth fixture.",
            "x_label": "Width (cm)",
            "y_label": "Height (cm)",
            "timeline_label": "Day",
            "bounds": [-1, 1, 0, 4],
            "times": [0, 1, 2],
            "original": world("Original", [1, 2, 3]),
            "proposed": world("Proposed", [1, 2.5, 4]),
            "selection": "All deterministic fixture time steps.",
            "limitations": "Software fixture, not biological evidence.",
            "replayed_trials": 0,
            "inputs": [{"artifact": prefix + "trials.csv", "record": {"seed": 1}}],
        }

    monkeypatch.setitem(PROCESS_ADAPTERS, "plant_growth", plant_adapter)
    result = build("plant_growth", {"light": 1}, [{"height": 2}], "controlled light")
    assert result["status"] == "ready"
    assert "Plant growth scenario" in process_html(result["process"])
    assert len(result["process"]["provenance"]["artifacts"]) == 2


def test_renderer_failure_preserves_partial_report_and_artifact_seal(tmp_path, monkeypatch):
    def broken_adapter(*_):
        raise RuntimeError("Fixture renderer failure")

    monkeypatch.setitem(PROCESS_ADAPTERS, "percolation", broken_adapter)
    result = run_fixture(
        read_source(fixture_source()), tmp_path / "run", RunConfig(sizes=[8, 16], trials=32)
    )
    assert result["status"] == "visualization_incomplete"
    assert result["rounds"]
    output = json.loads((tmp_path / "run/comparison/process.json").read_text())
    assert output["status"] == "invalid"
    assert not verify_artifacts(tmp_path / "run")
