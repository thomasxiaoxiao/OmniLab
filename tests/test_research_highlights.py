"""Scientific meaning must survive negative, uncertain and missing measurements."""

import json
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from hacknation_databricks.research.comparison import comparison_bundle
from hacknation_databricks.research.highlights import research_highlights


def bundle_for(domain, index=0):
    root = Path(f"examples/{domain}/adaptive-results")
    report = json.loads((root / "report.json").read_text())
    return comparison_bundle(
        report,
        json.loads((root / "config.json").read_text()),
        json.loads((root / "source-index.json").read_text()),
        lambda name: json.loads((root / name).read_text()),
        report["rounds"][index],
    )


def test_percolation_explains_metric_without_claiming_improvement_or_universality():
    result = research_highlights(bundle_for("percolation"))
    assert "75.001%" in result["reference"]["finding"]
    assert "not that the model is better" in result["meaning"]
    assert "critical threshold" in result["implication"]
    assert all("not yet resolved" in row["Uncertainty"] for row in result["rows"])
    assert "2.0 more wrapping lattices" in result["rows"][0]["What changed"]


def test_astrosat_retains_false_alert_cost_and_zero_miss_uncertainty():
    result = research_highlights(bundle_for("astrosat"))
    assert "does not report" in result["reference"]["finding"]
    row = result["rows"][0]
    assert row["Follow-up"] == "0.0%"
    assert "11.4 fewer misses" in row["What changed"]
    assert "14.2% → 51.6%" in row["False-alert tradeoff"]
    assert "not yet resolved" in row["Uncertainty"]
    assert "does not prove zero risk" in result["implication"]


def test_unknown_source_and_missing_interval_cannot_inherit_paper_claims():
    bundle = bundle_for("percolation")
    bundle["sources"] = [{"url": "https://arxiv.org/abs/unrelated"}]
    bundle["checks"][0]["difference_interval"] = None
    result = research_highlights(bundle)
    assert result["reference"] is None
    assert "Uncertainty unavailable" in result["rows"][0]["Uncertainty"]
    bundle["checks"] = []
    assert not research_highlights(bundle)["rows"]


def test_resolved_negligible_effect_is_not_presented_as_failed_resolution():
    bundle = bundle_for("percolation")
    check = bundle["checks"][0]
    check.update(
        treatment=check["control"],
        difference_interval=[-0.01, 0.01],
        conclusion="equivalent_within_threshold",
    )
    row = research_highlights(bundle)["rows"][0]
    assert "negligible-effect range" in row["Uncertainty"]
    assert "identical behavior" in row["Uncertainty"]
    assert row["What changed"].startswith("No observed change")


@pytest.mark.parametrize("domain", ["percolation", "astrosat"])
def test_highlights_render_saved_scientific_comparisons(domain):
    bundle = bundle_for(domain)
    app = AppTest.from_string(
        "from hacknation_databricks.highlights_ui import render_highlights\n"
        f"render_highlights({bundle!r})"
    ).run()
    assert not app.exception
    assert any("Scientific insight" in item.value for item in app.markdown)
    assert len(app.metric) == len(bundle["checks"]) + (domain == "percolation")
    assert any("Original paper · cited result" in m.value for m in app.markdown)
    assert any("Proposed simulation · agent-selected change" in m.value for m in app.markdown)
