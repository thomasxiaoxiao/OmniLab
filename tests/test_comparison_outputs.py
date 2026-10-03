import json
from xml.etree import ElementTree

import pytest
from fixture_roles import run_fixture

from hacknation_databricks.research.activity import Activity
from hacknation_databricks.research.artifacts import verify_artifacts
from hacknation_databricks.research.cli import fixture_source
from hacknation_databricks.research.comparison import (
    comparison_bundle,
    comparison_svg,
    synthesis_dataset,
)
from hacknation_databricks.research.models import RunConfig
from hacknation_databricks.research.sources import read_source
from hacknation_databricks.research_views import downstream_steps, recorded_prompt
from hacknation_databricks.tracking import Journal


def test_final_selection_uses_accepted_branch_at_decision_time_not_late_results():
    rounds = [
        {"round": 1, "branch_id": "a", "batch": 1},
        {"round": 2, "branch_id": "b", "batch": 1},
        {"round": 3, "branch_id": "a", "batch": 2},
    ]
    report = {
        "rounds": rounds,
        "goal": {"branch_id": "a", "achieved": True},
        "checkpoints": [
            {"checkpoint": 2, "goal_accepted": True, "decision": {"goal_branch_id": "a"}}
        ],
    }
    assert synthesis_dataset(report) is rounds[0]


def test_comparison_preserves_zero_negative_effect_uncertainty_and_tradeoff():
    dataset = {
        "round": 4,
        "branch_id": "b1",
        "batch": 2,
        "effect": {
            "metric": "missed-transit rate",
            "checks": [
                {
                    "scenario": "fresh <test>",
                    "control": 0.2,
                    "treatment": 0,
                    "difference": -0.2,
                    "difference_interval": [-0.3, -0.1],
                    "control_samples": 500,
                    "treatment_samples": 500,
                    "control_false_alert_rate": 0.1,
                    "false_alert_rate": 0.3,
                    "negative_candidates": 600,
                    "conclusion": "difference_detected",
                }
            ],
        },
    }
    reads = []

    def read(name):
        reads.append(name)
        return {
            "recipe": {
                "margin_sigma": 2,
                "field_diameter_deg": 0.5,
                "timing_window_seconds": 5,
                "assumptions": "Archived assumptions",
            }
        }

    bundle = comparison_bundle({"rounds": [dataset], "domain": "astrosat"}, {}, [], read)
    assert reads == ["branches/b1/batches/02/specification.json"]
    assert bundle["recipe"]["assumptions"] == "Archived assumptions"
    assert "20.00% → 0.00% (-20.00 percentage points" in bundle["summary"]
    assert "false alerts 10.00% → 30.00% (+20.00 points)" in bundle["summary"]
    svg = comparison_svg(bundle)
    ElementTree.fromstring(svg)
    assert "fresh &lt;test&gt;" in svg and "fresh <test>" not in svg
    assert "n=500" in svg and "n=600" in svg
    assert "no historical satellite forecast" in svg
    assert svg == comparison_svg(bundle)


@pytest.mark.parametrize("adaptive", [False, True])
def test_terminal_run_seals_both_outputs_for_every_checkpoint(tmp_path, adaptive):
    if adaptive:
        from test_adaptive import make_run

        report = make_run(tmp_path)
    else:
        report = run_fixture(
            read_source(fixture_source()), tmp_path / "run", RunConfig(sizes=[8, 16], trials=32)
        )
    directory = tmp_path / "run"
    assert len(report["comparison_artifacts"]) == len(report["rounds"]) + 1
    for record in report["comparison_artifacts"].values():
        assert record["status"] == "measured"
        bundle = json.loads((directory / record["measurements"]).read_text())
        assert (directory / record["summary"]).read_text().strip() == bundle["summary"]
        ElementTree.parse(directory / record["visualization"])
        assert bundle["recipe"]
    assert not verify_artifacts(directory)


def test_missing_measurements_export_unavailable_without_invented_rates():
    bundle = comparison_bundle({"status": "failed", "rounds": []}, {}, [], lambda _: None)
    assert bundle["status"] == "unavailable" and bundle["checks"] == []
    assert "unavailable" in bundle["summary"]
    assert "n=" not in comparison_svg(bundle)


def test_prompts_come_from_each_archived_call_and_retries_do_not_claim_actions(tmp_path):
    (tmp_path / "roles").mkdir()
    nodes = [
        Activity(
            "source",
            "researcher",
            0,
            "omnigent",
            "",
            call_id="roles/01-researcher",
            status="failed",
            parents=[],
        ),
        Activity(
            "source",
            "researcher",
            0,
            "omnigent",
            "",
            call_id="roles/02-researcher",
            status="completed",
            parents=[],
        ),
        Activity("critique", "consolidator", 0, "omnigent", "", parents=["source"]),
    ]
    path = "roles/02-researcher-request.json"
    prompt = {
        "instructions": "The archived assignment, not the current catalog.",
        "data": {"source": {"source_id": "seed"}},
        "output_schema": {"title": "Brief"},
    }
    (tmp_path / path).write_text(json.dumps({"prompt": json.dumps(prompt), "prompt_version": "v0"}))
    journal = Journal("run", tmp_path, sealed=True, artifacts={path: {}})
    assert recorded_prompt(journal, nodes[0]) is None
    saved = recorded_prompt(journal, nodes[1])
    assert saved["instructions"] == prompt["instructions"]
    assert saved["input_scope"] == "Source: seed"
    assert saved["prompt_version"] == "v0"
    assert downstream_steps(nodes, nodes[0]) == []
    assert downstream_steps(nodes, nodes[1]) == [nodes[2]]
