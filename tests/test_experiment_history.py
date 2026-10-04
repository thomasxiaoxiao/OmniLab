"""History isolation and full-range simulations survive planning, execution and display."""

import json
import shutil
from types import SimpleNamespace

import pytest
from test_repository_execution import RepositoryRoles, make_repository_run

from hacknation_databricks.research.experiment_history import (
    experiment_history,
    reject_repeated_direction,
)
from hacknation_databricks.research.repository_models import ExplorationRepositoryPlan
from hacknation_databricks.research.repository_workflow import validate_trials


def test_history_checks_hashes_isolates_papers_and_deduplicates_copies(tmp_path):
    output, _ = make_repository_run(tmp_path)
    source_hash = json.loads((output / "sources.json").read_text())[0]["sha256"]
    shutil.copytree(output, tmp_path / "copy")
    history = experiment_history(source_hash, [tmp_path])
    assert len(history["entries"]) == 1
    assert history["entries"][0]["completed_comparisons"] == 2
    assert not experiment_history("another-paper", [tmp_path])["entries"]
    with pytest.raises(ValueError, match="already analyzed"):
        reject_repeated_direction(SimpleNamespace(**history["entries"][0]["direction"]), history)
    for path in [output, tmp_path / "copy"]:
        (path / "report.json").write_text("{}")
    assert not experiment_history(source_hash, [tmp_path])["entries"]


def test_history_reaches_all_selection_roles(tmp_path):
    received = []

    class HistoryAware(RepositoryRoles):
        def ask(self, role, payload, contract):
            if role in {"repository_reader", "repository_critic", "repository_planner"}:
                assert payload["exploration_mode"] == "new_direction"
                assert payload["prior_experiments"]["entries"] == []
                received.append(role)
            return super().ask(role, payload, contract)

    _, report = make_repository_run(tmp_path, roles_factory=HistoryAware)
    assert report["status"] == "research_stopped"
    assert len(received) == 3


def sweep_plan():
    plan = RepositoryRoles([], None, None).ask("repository_planner", {}, ExplorationRepositoryPlan)
    raw = plan.model_dump()
    raw["sweep"] = {"parameter": "probabilities", "label": "p", "lower": 0.0, "upper": 1.0}
    for parameters in [
        raw["baseline"],
        raw["treatment"],
        raw["sanity"],
        raw["learning_design"]["followups"][0]["treatment"],
    ]:
        parameters["probabilities"] = [0.0, 0.5, 1.0]
    return raw


def test_cutoff_rejected_before_execution_and_partial_output_rejected():
    raw = sweep_plan()
    raw["treatment"]["probabilities"] = [0.6, 0.8]
    with pytest.raises(ValueError, match="endpoints"):
        ExplorationRepositoryPlan.model_validate(raw)
    plan = ExplorationRepositoryPlan.model_validate(sweep_plan())
    with pytest.raises(ValueError, match="complete baseline sweep"):
        plan.validate_sweep({**plan.treatment, "probabilities": [0.0, 0.75, 1.0]})
    trial = {
        "arm": "control",
        "parameters": plan.baseline,
        "output": {"metric": 1.0, "times": [0.5, 1.0]},
    }
    with pytest.raises(ValueError, match="every planned value"):
        validate_trials({"trials": [trial]}, plan)


def test_comparison_ui_exposes_current_parameters_and_actual_range(tmp_path):
    from hacknation_databricks.repository_ui import render_repository_result
    from hacknation_databricks.tracking import load_journal
    from hacknation_databricks.web.components import Session, render

    output, _ = make_repository_run(tmp_path)
    main = render(Session(), lambda: render_repository_result(load_journal(output)))["main"]
    values = [str(item.get("value", "")) for item in main]
    assert any("How the scenarios differ" in value for value in values)
    assert any("Step: 0 to 3" in value for value in values)
    html = (output / "comparison/process.html").read_text()
    assert "Fixed state" in html and "Baseline" in html
    assert "render();if(!reduced)start();" not in html
    # Current final treatment is .8, rather than the first experiment's .9.
    table = next(item for item in main if item["type"] == "dataframe")
    assert "0.8" in str(table) and "1.0" in str(table)


def test_paper_name_uses_pinned_hash_without_rewriting_saved_metadata():
    from hacknation_databricks.seed_catalog import SEED_PAPERS, source_display_name

    for label, _, digest in SEED_PAPERS:
        assert source_display_name({"title": "seed", "sha256": digest}) == label
    assert source_display_name({"title": "New paper", "sha256": "unknown"}) == "New paper"


def test_repeated_selection_stops_before_any_simulation_after_bounded_repair(tmp_path):
    prior = tmp_path / "prior"
    prior.mkdir()
    make_repository_run(prior)
    fresh = tmp_path / "fresh"
    fresh.mkdir()
    output, report = make_repository_run(fresh, history_roots=[prior])
    assert report["status"] == "failed"
    assert report["computed_simulations"] == 0
    assert report["role_calls"] == 4  # reader/literature, critic, one critic correction
    failure = json.loads((output / "critic_contract_failure.json").read_text())
    assert "already analyzed" in failure["errors"][0]["msg"]


def test_large_sealed_evidence_is_not_quarantined_by_preview_limit(tmp_path):
    import hashlib

    from hacknation_databricks.tracking import load_journal, read_artifact

    output, _ = make_repository_run(tmp_path)
    data = b"x" * (21 * 1024 * 1024)
    artifact = output / "large-diagnostic.bin"
    artifact.write_bytes(data)
    manifest_path = output / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["artifacts"][artifact.name] = {
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }
    manifest_path.write_text(json.dumps(manifest))
    assert load_journal(output).verified
    with pytest.raises(ValueError, match="20 MiB"):
        read_artifact(output, artifact.name)
    assert read_artifact(output, artifact.name, max_bytes=128 * 1024 * 1024) == data
    from view_test import ViewTest

    from hacknation_databricks.tracking_ui import render_artifacts

    app = ViewTest.from_function(render_artifacts, args=(load_journal(output),)).run()
    next(s for s in app.selectbox if s.label == "Inspect artifact").select(artifact.name).run()
    assert not app.exception and not app.error
    assert any("preview omitted" in item.value for item in app.info)
    assert any(blob[0] == data for blob in app.session.blobs.values())
    with artifact.open("r+b") as stream:
        stream.write(b"y")
    assert not load_journal(output).verified
