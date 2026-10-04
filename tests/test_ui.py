from pathlib import Path

from view_test import ViewTest


def test_legacy_entry_uses_current_interface_and_revision(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_REVISION", "abc123")
    monkeypatch.setenv("RESEARCH_RUNS_DIR", str(tmp_path))
    ui = Path(__file__).resolve().parents[1] / "src/hacknation_databricks/research_ui.py"
    result = ViewTest.from_file(str(ui)).run(timeout=15)
    assert not result.exception
    assert result.title[0].value == "Source intake"
    assert any(
        "scientific conclusions require further validation" in c.value for c in result.caption
    )
    assert any("abc123" in c.value for c in result.caption)
    assert not any(s.label in {"Agent runner", "Simulation size"} for s in result.selectbox)
    assert not list(tmp_path.glob("*/report.json"))
