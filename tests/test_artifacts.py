"""Run metadata remains available without the optional Apple Silicon runtime."""

from importlib.metadata import PackageNotFoundError

from hacknation_databricks.research import artifacts


def test_environment_records_absent_optional_mlx_without_blocking_runs(monkeypatch):
    installed_version = artifacts.version

    def without_mlx(name):
        if name == "mlx-lm":
            raise PackageNotFoundError(name)
        return installed_version(name)

    monkeypatch.setattr(artifacts, "version", without_mlx)
    metadata = artifacts.environment()
    assert metadata["packages"]["mlx-lm"] is None
    assert metadata["packages"]["omnigent"] == installed_version("omnigent")
    assert len(metadata["code_sha256"]) == 64
