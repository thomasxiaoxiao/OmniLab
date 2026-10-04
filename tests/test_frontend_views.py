"""Guard the scientific meaning of the new read-only frontend projections."""

from pathlib import Path

import pytest
from view_test import ViewTest

from hacknation_databricks.research.activity import Activity
from hacknation_databricks.research_views import (
    dataset_artifacts,
    latest_datasets,
    measurement_rows,
    paper_dot,
    paper_evidence,
    synthesis_dataset,
    workflow_dot,
)
from hacknation_databricks.tracking import Journal

UI = Path(__file__).resolve().parents[1] / "src/hacknation_databricks/ui.py"


def test_state_graph_preserves_parallel_handoffs_and_role_reuse():
    nodes = [
        Activity("a", "researcher", 0, "omnigent", "", parents=[]),
        Activity("b", "researcher", 0, "omnigent", "", parents=[]),
        Activity("c", "critic", 0, "omnigent", "", parents=["a", "b"]),
        Activity("d", "experiment", 1, "simulation", "", parents=["c"]),
        Activity("e", "critic", 1, "omnigent", "", parents=["d"]),
    ]
    graph = workflow_dot(nodes)
    assert 'r0 -> r0 [label="used 2 times"' in graph
    assert 'r1 -> r1 [label="used 2 times"' in graph
    assert 'r0 -> r1 [label="2 handoffs"' in graph
    assert 'r1 -> r2 [label="1 handoff"' in graph
    assert 'r2 -> r1 [label="1 handoff"' in graph
    assert "r0 -> r2" not in graph


def test_final_dataset_pins_accepted_checkpoint_and_never_adds_cumulative_counts():
    rounds = [
        {"round": 1, "branch_id": "a", "batch": 1},
        {"round": 2, "branch_id": "a", "batch": 2},
        {"round": 3, "branch_id": "b", "batch": 1},
    ]
    report = {"rounds": rounds, "checkpoints": [{"checkpoint": 2, "goal_accepted": True}]}
    assert synthesis_dataset(report) == rounds[1]
    assert latest_datasets(report) == rounds[1:]
    journal = Journal(
        "test",
        Path("."),
        artifacts={
            "branches/a/batches/01/trials.csv": {},
            "branches/a/batches/02/trials.csv": {},
            "branches/a/batches/03/trials.csv": {},
            "branches/b/batches/01/trials.csv": {},
        },
    )
    assert dataset_artifacts(journal, rounds[1]) == [
        "branches/a/batches/01/trials.csv",
        "branches/a/batches/02/trials.csv",
    ]


def test_legacy_intervals_are_derived_conservatively():
    dataset = {
        "trials_per_size": 10,
        "effect": {
            "checks": [
                {
                    "size": 8,
                    "control": 0.4,
                    "treatment": 0.7,
                    "difference": 0.3,
                    "control_interval": [0.2, 0.6],
                    "treatment_interval": [0.5, 0.9],
                }
            ]
        },
    }
    row = measurement_rows(dataset)[0]
    assert row["Lower"] == pytest.approx(-0.1)
    assert row["Upper"] == pytest.approx(0.7)
    assert row["Control samples"] == 10


def test_paper_map_does_not_invent_review_or_citation_edges(tmp_path):
    journal = Journal("test", tmp_path, sealed=True)
    journal.sources = [
        {"source_id": "seed", "title": 'Seed "paper"'},
        {"source_id": "unread", "title": "Retrieved only"},
    ]
    journal.proposals = [
        {
            "title": "A grounded concept",
            "evidence": {
                "source_id": "seed",
                "page": 2,
                "quote": "Quoted evidence",
            },
        }
    ]
    evidence = paper_evidence(journal)
    graph = paper_dot(journal, evidence)
    assert len(evidence) == 1
    assert "No recorded evidence passage" in graph
    assert "p0 -- p1" not in graph
    assert 'Seed \\"paper\\"' in graph


def test_navigation_preserves_run_and_seed_without_launching(tmp_path, monkeypatch):
    from hacknation_databricks.research.intake import register_upload

    monkeypatch.setenv("RESEARCH_RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.setenv("RESEARCH_SOURCES_DIR", str(tmp_path / "sources"))
    source = register_upload(
        "chosen.md", b"A source for a bounded experiment.", tmp_path / "sources"
    )
    app = ViewTest.from_file(str(UI)).run(timeout=15)
    assert not app.exception
    assert app.title[0].value == "Source intake"
    assert any(s.label == "Seed paper" for s in app.selectbox)
    app.switch_page("app_pages/sources.py").run()
    picker = next(s for s in app.selectbox if s.label == "Seed paper")
    picker.select(next(v for v in picker.options if "chosen.md" in v)).run()
    assert app.session_state["selected_seed_path"] == str(Path(source.path).resolve())
    for page in ["agents", "overview", "evidence", "sources"]:
        app.switch_page(f"app_pages/{page}.py").run()
        assert not app.exception
    assert "chosen.md" in next(s.value for s in app.selectbox if s.label == "Seed paper")
    assert not (tmp_path / "runs").exists()


def test_adaptive_summary_renders_finalized_snapshot_and_tradeoff(tmp_path, monkeypatch):
    from test_adaptive import make_run

    make_run(tmp_path)
    monkeypatch.setenv("RESEARCH_RUNS_DIR", str(tmp_path))
    app = ViewTest.from_file(str(UI)).run(timeout=15)
    app.switch_page("app_pages/overview.py").run()
    assert not app.exception
    assert any("scoped research goal was reached" in item.value for item in app.success)
    assert any("Control false alerts" in frame.value.columns for frame in app.dataframe)
    assert not any(h.value == "Paper exploration" for h in app.subheader)
    app.switch_page("app_pages/overview.py").run()
    assert not app.exception
    assert any(s.label == "Snapshot artifact" for s in app.selectbox)
    assert any("Original paper · cited result" in m.value for m in app.markdown)
    app.switch_page("app_pages/agents.py").run()
    assert not app.exception
    assert any("0" == m.value for m in app.metric if m.label == "Omnigent sessions")
