"""Paper-specific intent and implementations cannot silently become preset examples."""

import json
from pathlib import Path

import pytest

from hacknation_databricks.research.adaptive import run_adaptive
from hacknation_databricks.research.adaptive_experiments import execute_batch
from hacknation_databricks.research.agents import RoleBackend
from hacknation_databricks.research.artifacts import verify_artifacts
from hacknation_databricks.research.models import RunConfig
from hacknation_databricks.research.sources import read_source
from hacknation_databricks.tracking import load_journal


def test_unrelated_paper_is_read_without_presets_and_keeps_its_own_findings(tmp_path):
    seen = []

    class Reader(RoleBackend):
        def ask(self, role, payload, contract):
            self.calls += 1
            seen.append(role)
            evidence = [{"source_id": "seed", "page": 1, "quote": payload["source"]["pages"][0]}]
            if role == "paper_reader":
                context = json.dumps({"payload": payload, "schema": contract.model_json_schema()})
                assert all(word not in context for word in ("percolation", "astrosat", "wrapping"))
                return contract.model_validate(
                    {
                        "research_question": "Does illumination affect photosynthetic yield?",
                        "summary": "The paper studies light intensity and photosynthesis.",
                        "directions": [
                            {
                                "id": "illumination",
                                "title": "Vary illumination intensity",
                                "hypothesis": "Illumination affects measured photosynthetic yield.",
                                "origin": "agent_hypothesis",
                                "evidence": evidence,
                            }
                        ],
                        "search_scope": "Read the complete supplied source.",
                        "missing_evidence": [
                            "No validated plant-response implementation available."
                        ],
                    }
                )
            assert role == "research_context"
            return contract.model_validate(
                {
                    "research_question": payload["paper_brief"]["research_question"],
                    "summary": payload["paper_brief"]["summary"],
                    "domain": "unsupported",
                    "rationale": "No supplied implementation models photosynthetic yield.",
                    "evidence": evidence,
                }
            )

    source = tmp_path / "plant-study.md"
    source.write_text("Photosynthetic yield depends on illumination intensity.")
    output = tmp_path / "run"
    result = run_adaptive(
        read_source(source),
        output,
        RunConfig(workflow="adaptive", domain="auto"),
        backend="fixture",
        roles_factory=Reader,
    )
    assert seen == ["paper_reader", "research_context"]
    assert result["status"] == "unsupported_source"
    assert result["computed_simulations"] == 0
    assert not (output / "code").exists()
    assert not (output / "experiment_catalog.json").exists()
    assert "illumination" in (output / "paper_briefs.json").read_text()
    assert not verify_artifacts(output)
    assert load_journal(output).verified


def test_validator_and_archive_contain_only_selected_science(tmp_path):
    from test_adaptive import make_run

    make_run(tmp_path)
    directory = tmp_path / "run"
    manifest = json.loads((directory / "implementation.json").read_text())
    sources = json.loads((directory / "sources.json").read_text())
    assert manifest["source_sha256"] == sources[0]["sha256"]
    assert set(manifest["files"]) == {
        "code/astrosat_experiments.py",
        "code/scientific_statistics.py",
    }
    assert not (directory / "code/simulation.py").exists()
    assert not (directory / "code/adaptive_experiments.py").exists()
    code = "\n".join((directory / p).read_text() for p in manifest["files"])
    assert "percolation" not in code
    assert "lattice" not in code
    assert (directory / "framework/source.zip").is_file()


def test_unknown_domain_never_defaults_to_percolation():
    with pytest.raises(ValueError, match="No implementation"):
        execute_batch("unknown", {}, [], 8, 1, None)


def test_source_filter_matches_content_not_names(tmp_path):
    from hacknation_databricks.tracking_ui import runs_for_source

    runs = [tmp_path / "a", tmp_path / "b"]
    for path, digest in zip(runs, ["paper-one", "paper-two"], strict=True):
        path.mkdir()
        (path / "sources.json").write_text(
            json.dumps([{"source_id": "seed", "title": "Same filename", "sha256": digest}])
        )
    assert runs_for_source(runs, "paper-two") == [runs[1]]
    assert runs_for_source(runs, "new-paper") == []


def test_library_does_not_inject_preset_papers(tmp_path, monkeypatch):
    from hacknation_databricks.research.intake import library_sources

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("RESEARCH_PAPER_PATH", raising=False)
    papers = Path("data/papers")
    papers.mkdir(parents=True)
    (papers / "2607.24975v1.pdf").write_bytes(b"not read automatically")
    assert library_sources(tmp_path / "library") == ([], [])


def test_tool_mapper_cannot_rewrite_paper_hypothesis(tmp_path):
    from test_adaptive import AdaptiveFixture

    class Rewrite(AdaptiveFixture):
        def ask(self, role, payload, contract):
            if role == "research_context":
                self.calls += 1
                return contract.model_validate(
                    {
                        "research_question": payload["paper_brief"]["research_question"],
                        "summary": payload["paper_brief"]["summary"],
                        "domain": "astrosat",
                        "rationale": "Check the transit implementation fit.",
                        "evidence": payload["paper_brief"]["directions"][0]["evidence"],
                    }
                )
            response = super().ask(role, payload, contract)
            if role == "implementation_mapper":
                response.directions[
                    0
                ].hypothesis = "A different preset hypothesis replaces the paper."
            return response

    paper = tmp_path / "paper.md"
    paper.write_text("Expand the field of view to account for cross-track uncertainty.")
    output = tmp_path / "run"
    with pytest.raises(ValueError, match="changed a paper-first direction"):
        run_adaptive(
            read_source(paper),
            output,
            RunConfig(workflow="adaptive", domain="auto"),
            backend="fixture",
            roles_factory=Rewrite,
        )
    report = json.loads((output / "report.json").read_text())
    assert report["computed_simulations"] == 0
    assert not (output / "baseline").exists()
    assert not (output / "implementation.json").exists()
    assert (output / "paper_briefs.json").exists()
    assert not verify_artifacts(output)


def test_cli_uploaded_paper_defaults_to_paper_first_context(tmp_path, monkeypatch):
    from hacknation_databricks.research import cli

    paper = tmp_path / "unrelated.md"
    paper.write_text("A distinct source must not select a preset by default.")
    seen = {}

    def capture(source, output, config, **kwargs):
        seen.update(config=config, source=source)
        return {"status": "unsupported_source"}

    monkeypatch.setattr(cli, "run_research", capture)
    assert cli.main(["run", "--paper", str(paper), "--no-auto-literature"]) == 2
    assert seen["config"].domain == "auto"
    assert seen["config"].workflow == "adaptive"
    assert seen["source"].path == str(paper)
