from pathlib import Path

from streamlit.testing.v1 import AppTest


def test_demo_renders_notice_and_revision(monkeypatch):
    monkeypatch.setenv("APP_REVISION", "abc123")
    ui = Path(__file__).resolve().parents[1] / "src/hacknation_databricks/ui.py"
    result = AppTest.from_file(str(ui)).run()
    assert not result.exception
    assert result.title[0].value == "Rental Housing Law Navigator"
    assert result.caption[0].value == "Not legal advice."
    assert result.caption[1].value == "Deployed revision: abc123"
