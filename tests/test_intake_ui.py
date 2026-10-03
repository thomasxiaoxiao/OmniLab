import json
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

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
    app = AppTest.from_function(intake_page).run()
    next(t for t in app.text_input if t.label == "arXiv link or identifier").set_value(
        "https://arxiv.org/abs/2607.24975v1"
    )
    next(b for b in app.button if b.label == "Import arXiv paper").click().run()
    assert not app.exception
    assert links == ["https://arxiv.org/abs/2607.24975v1"]
    assert any("Ready:" in s.value for s in app.success)
    assert app.session_state["intake_selected"] == str(Path(imported.path).resolve())
    assert any(s.label == "Inspect source" for s in app.selectbox)


def test_import_error_is_actionable_and_does_not_create_source(tmp_path, monkeypatch):
    monkeypatch.setenv("RESEARCH_SOURCES_DIR", str(tmp_path))
    app = AppTest.from_function(intake_page).run()
    next(t for t in app.text_input if t.label == "arXiv link or identifier").set_value(
        "https://example.com/arbitrary.pdf"
    )
    next(b for b in app.button if b.label == "Import arXiv paper").click().run()
    assert not app.exception
    assert any("arxiv.org" in e.value for e in app.error)
    assert not list(tmp_path.iterdir())


def test_uploaded_sources_launch_with_original_identity_and_literature(tmp_path, monkeypatch):
    from fixture_roles import DecisionWorkerFixture

    from hacknation_databricks.research import decision_roles, decision_runtime

    monkeypatch.setattr(decision_roles, "DecisionProcess", DecisionWorkerFixture)
    monkeypatch.setattr(decision_runtime, "runtime_status", lambda: {"ready": True})
    monkeypatch.setenv("RESEARCH_SOURCES_DIR", str(tmp_path / "sources"))
    monkeypatch.setenv("RESEARCH_RUNS_DIR", str(tmp_path / "runs"))
    seed = register_upload("seed.md", fixture_source().read_bytes(), tmp_path / "sources")
    related = register_upload(
        "related.md", b"Independent notes on a percolation experiment.", tmp_path / "sources"
    )
    app = AppTest.from_file(str(TRACKING)).run()
    app.switch_page("app_pages/sources.py").run()
    backend = next(s for s in app.selectbox if s.label == "Decision backend")
    backend.select(next(s for s in backend.options if "AnyJev" in s)).run()
    picker = next(s for s in app.selectbox if s.label == "Registered source")
    picker.select(next(s for s in picker.options if "seed.md" in s)).run()
    related_picker = next(s for s in app.multiselect if s.label == "Related literature")
    related_picker.select(next(s for s in related_picker.options if "related.md" in s)).run()
    next(s for s in app.selectbox if s.label == "Decision backend").select(
        "AnyJev · local Qwen · decision only"
    ).run()
    next(b for b in app.button if b.label == "Start bounded run").click().run(timeout=30)
    assert not app.exception
    directory = next((tmp_path / "runs").glob("*/sources.json")).parent
    source_data = json.loads((directory / "sources.json").read_text())
    assert [s["sha256"] for s in source_data] == [seed.sha256, related.sha256]
    assert all(not s["url"] for s in source_data)  # No unrelated seed-paper URL injected.
    assert (directory / "inputs/seed.md").read_bytes() == fixture_source().read_bytes()
    assert (directory / "inputs/seed.md.json").exists()
    app.switch_page("app_pages/agents.py").run()
    assert next(m for m in app.metric if m.label == "Omnigent sessions").value == "0"
    next(s for s in app.selectbox if s.label == "Inspect execution step").select_index(2).run()
    assert not app.exception
    assert any(
        "baseline/trials.csv" in s.options for s in app.selectbox if s.label == "Step artifact"
    )


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

    assert not AppTest.from_function(page).run().exception


def test_library_only_includes_two_builtins_and_explicit_imports(tmp_path, monkeypatch):
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
    assert [Path(s.path).name for s in sources] == [
        "source.md",
        "2607.24975v1.pdf",
        "2111.11268v1.pdf",
    ]
    monkeypatch.setenv("RESEARCH_PAPER_PATH", str(papers / "2607.24975v1.pdf"))
    assert len(library_sources(tmp_path / "sources")[0]) == 3
