import pytest

from hacknation_databricks.research.cli import fixture_source
from hacknation_databricks.research.intake import register_upload


@pytest.fixture
def launch_source(monkeypatch, tmp_path):
    """Supply launch tests with evidence independent of ignored local papers."""
    root = tmp_path / "sources"
    monkeypatch.setenv("RESEARCH_SOURCES_DIR", str(root))
    return register_upload(
        "seed.md",
        fixture_source().read_bytes() + b"\nCode: https://github.com/example/science\n",
        root,
    )


@pytest.fixture(autouse=True)
def isolate_seed_examples(monkeypatch):
    # UI tests must not depend on ignored papers on the developer's machine.
    monkeypatch.setattr("hacknation_databricks.tracking_ui.seed_examples", lambda: {})
