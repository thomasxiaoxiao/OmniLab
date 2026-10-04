import json
from pathlib import Path

import pytest
from view_test import ViewTest

from hacknation_databricks.research.cli import fixture_source
from hacknation_databricks.research.intake import register_upload

TRACKING = Path(__file__).resolve().parents[1] / "src/hacknation_databricks/ui.py"


def intake_page():
    from hacknation_databricks.source_ui import render_sources

    render_sources()


def test_source_form_import_updates_library_and_selected_seed(tmp_path, monkeypatch):
    from hacknation_databricks import source_ui

    root = tmp_path / "sources"
    monkeypatch.setenv("RESEARCH_SOURCES_DIR", str(root))
    imported = register_upload("paper.md", b"# Source\n\nEvidence from imported paper.", root)
    links = []

    def fake_import(link, destination):
        links.append(link)
        assert destination == root
        return imported

    monkeypatch.setattr(source_ui, "register_arxiv", fake_import)
    app = ViewTest.from_file(str(TRACKING)).run(timeout=15)
    next(t for t in app.text_input if t.label == "arXiv link or identifier").set_value(
        "https://arxiv.org/abs/2607.24975v1"
    )
    next(b for b in app.button if b.label == "Import arXiv paper").click().run()
    assert not app.exception
    assert links == ["https://arxiv.org/abs/2607.24975v1"]
    assert any("Ready:" in s.value for s in app.success)
    assert app.session_state["selected_seed_path"] == str(Path(imported.path).resolve())
    assert sum(s.label == "Seed paper" for s in app.selectbox) == 1
    assert not any(e.label == "Extracted text & provenance" for e in app.expander)
    assert not any(s.label == "Related literature" for s in app.multiselect)
    assert not any(h.value == "Prepare a discovery run" for h in app.subheader)
    assert not any(s.label == "Inspect sources" for s in app.selectbox)


def test_import_error_is_actionable_and_does_not_create_source(tmp_path, monkeypatch):
    monkeypatch.setenv("RESEARCH_SOURCES_DIR", str(tmp_path))
    app = ViewTest.from_function(intake_page).run()
    next(t for t in app.text_input if t.label == "arXiv link or identifier").set_value(
        "https://example.com/arbitrary.pdf"
    )
    next(b for b in app.button if b.label == "Import arXiv paper").click().run()
    assert not app.exception
    assert any("arxiv.org" in e.value for e in app.error)
    assert not list(tmp_path.iterdir())


def test_uploaded_sources_launch_with_original_identity_and_literature(tmp_path, monkeypatch):
    from fixture_roles import DecisionWorkerFixture

    from hacknation_databricks import tracking_ui
    from hacknation_databricks.research import decision_roles

    monkeypatch.setattr(decision_roles, "DecisionProcess", DecisionWorkerFixture)
    monkeypatch.setenv("RESEARCH_SOURCES_DIR", str(tmp_path / "sources"))
    monkeypatch.setenv("RESEARCH_RUNS_DIR", str(tmp_path / "runs"))
    seed = register_upload("seed.md", fixture_source().read_bytes(), tmp_path / "sources")
    related = register_upload(
        "related.md", b"Independent notes on a percolation experiment.", tmp_path / "sources"
    )
    app = ViewTest.from_file(str(TRACKING)).run()
    app.switch_page("app_pages/sources.py").run()
    picker = next(s for s in app.selectbox if s.label == "Seed paper")
    picker.select(next(s for s in picker.options if "seed.md" in s)).run()
    assert not any(s.label == "Related literature" for s in app.multiselect)
    tracking_ui.launch_run(
        Path(seed.path), "Quick verification", "anyjev", lambda _: None, [Path(related.path)]
    )
    app.run(timeout=30)
    assert not app.exception
    directory = next((tmp_path / "runs").glob("*/sources.json")).parent
    source_data = json.loads((directory / "sources.json").read_text())
    assert [s["sha256"] for s in source_data] == [seed.sha256, related.sha256]
    assert all(not s["url"] for s in source_data)  # No unrelated seed-paper URL injected.
    assert (directory / "inputs/seed.md").read_bytes() == fixture_source().read_bytes()
    assert (directory / "inputs/seed.md.json").exists()
    app.switch_page("app_pages/agents.py").run()
    assert next(m for m in app.metric if m.label == "Omnigent sessions").value == "0"
    # ViewTest cannot click a custom SVG; seed the state emitted by its click callback.
    from hacknation_databricks.research.activity import load_activity
    from hacknation_databricks.tracking import load_journal

    nodes = load_activity(load_journal(directory))
    app.session_state[f"execution-selection:{directory.resolve()}"] = nodes[2].key
    app.run()
    assert not app.exception
    assert not any(s.label == "Inspect execution step" for s in app.selectbox)
    assert any("baseline/trials.csv" in s.options for s in app.pills if s.label == "Step artifact")


def test_launch_rejects_tampered_sources_and_excess_literature(tmp_path, monkeypatch):
    from hacknation_databricks.tracking_ui import launch_run

    monkeypatch.setenv("RESEARCH_SOURCES_DIR", str(tmp_path / "sources"))
    source = register_upload("seed.md", b"A test source document.", tmp_path / "sources")
    with pytest.raises(ValueError, match="three"):
        launch_run(
            Path(source.path),
            "Quick verification",
            "anyjev",
            lambda _: None,
            [Path(source.path)] * 4,
        )
    Path(source.path).write_text("changed")
    with pytest.raises(ValueError, match="registered"):
        launch_run(Path(source.path), "Quick verification", "anyjev", lambda _: None)


def test_running_validation_without_gate_does_not_crash():
    def page():
        from pathlib import Path

        from hacknation_databricks.tracking import Decision, Journal
        from hacknation_databricks.tracking_ui import render_gate

        journal = Journal("running", Path("."))
        journal.decisions = [
            Decision(
                "D-007",
                "rounds/01/validation",
                "validation",
                1,
                "running",
                "",
                "In progress",
                "",
                facts={"model_decisions": []},
            )
        ]
        render_gate(journal)

    assert not ViewTest.from_function(page).run().exception


def test_library_only_includes_explicit_imports_and_configured_source(tmp_path, monkeypatch):
    from hacknation_databricks.research.intake import library_sources
    from hacknation_databricks.research.sources import Source

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("RESEARCH_PAPER_PATH", raising=False)
    papers = tmp_path / "data/papers"
    papers.mkdir(parents=True)
    for name in ("2607.24975v1", "2111.11268v1", "ghost"):
        (papers / f"{name}.pdf").write_bytes(name.encode())
    imported = register_upload(
        "my-paper.md", b"My explicitly imported paper.", tmp_path / "sources"
    )

    def fake_read(path):
        return Source(
            source_id="seed",
            url="",
            title=path.stem,
            path=str(path),
            sha256=path.stem,
            pages=["Full text"],
            kind="full_text",
        )

    monkeypatch.setattr("hacknation_databricks.research.intake.read_source", fake_read)
    monkeypatch.setattr(
        "hacknation_databricks.research.intake.list_sources", lambda _: ([imported], [])
    )
    sources, issues = library_sources(tmp_path / "sources")
    assert not issues
    assert [Path(s.path).name for s in sources] == ["source.md"]
    monkeypatch.setenv("RESEARCH_PAPER_PATH", str(papers / "2607.24975v1.pdf"))
    assert len(library_sources(tmp_path / "sources")[0]) == 2


@pytest.mark.parametrize("same_source", [True, False])
def test_source_progress_matches_content_and_keeps_assessment_in_details(
    tmp_path, monkeypatch, same_source
):
    import hashlib

    from hacknation_databricks import activity_ui, source_ui
    from hacknation_databricks.tracking import Journal

    paper = tmp_path / "paper.md"
    paper.write_bytes(b"Original seed" if same_source else b"Different paper, same filename")
    reason = "Archived assessment: these tools cannot test this paper's hypothesis."
    journal = Journal(
        "stopped-run",
        tmp_path / "stopped-run",
        sources=[
            {
                "source_id": "seed",
                "title": "paper.md",
                "path": "/old/location/paper.md",
                "sha256": hashlib.sha256(b"Original seed").hexdigest(),
            }
        ],
        report={"status": "unsupported_source", "reason": reason},
        sealed=True,
    )
    monkeypatch.setattr(source_ui, "load_journal", lambda _: journal)
    rendered = []
    monkeypatch.setattr(activity_ui, "render_activity", lambda j: rendered.append(j.run_id))

    def page(path):
        from hacknation_databricks.source_ui import render_source_progress
        from hacknation_databricks.web import components as ui

        ui.session_state["run_selection"] = "stopped-run"
        ui.session_state["selected_seed_path"] = path
        render_source_progress()

    app = ViewTest.from_function(page, args=(str(paper),)).run()
    assert not app.exception
    assert not app.warning
    if same_source:
        assert any("stopped before simulation" in i.value for i in app.info)
        details = next(e for e in app.expander if "saved agent assessment" in e.label)
        assert not details.expanded
        assert details.text[0].value == reason
        assert any("stopped-run" in c.value for c in app.caption)
        assert rendered == ["stopped-run"]
    else:
        assert not app.info
        assert not app.expander
        assert any("belongs to paper.md" in c.value for c in app.caption)
        assert not rendered
    assert journal.report["reason"] == reason


def test_stopped_source_overview_does_not_wait_for_experiments():
    def page():
        from pathlib import Path

        from hacknation_databricks.discovery_ui import render_discovery
        from hacknation_databricks.run_feedback_ui import render_run_outcome
        from hacknation_databricks.tracking import Journal

        journal = Journal(
            "stopped", Path("."), report={"status": "unsupported_source", "workflow_version": "4"}
        )
        render_run_outcome(journal)
        render_discovery(journal)

    app = ViewTest.from_function(page).run()
    assert not app.exception
    assert not app.metric  # No "Goal: Open" on a concluded compatibility check.
    assert any("stopped before simulation" in i.value for i in app.info)
    assert any("No experiment" in c.value for c in app.caption)


def test_runtime_failure_is_distinct_from_unsupported_paper():
    def page():
        from pathlib import Path

        from hacknation_databricks.run_feedback_ui import render_run_outcome
        from hacknation_databricks.tracking import Journal

        render_run_outcome(
            Journal(
                "blocked",
                Path("."),
                report={"status": "blocked_live_backend", "reason": "ConnectError"},
            )
        )

    app = ViewTest.from_function(page).run()
    assert not app.exception
    assert len(app.warning) == 1
    assert "agent runtime" in app.warning[0].value
    assert app.expander[0].text[0].value == "ConnectError"
    assert not app.expander[0].expanded
