"""Archive test-only retired implementations for legacy regression fixtures."""

from pathlib import Path

from hacknation_databricks.research import scientific_statistics
from hacknation_databricks.research.code_archive import archive_framework as archive_framework


def archive_implementation(store, source, domain, *, sequential=False):
    modules = {
        "percolation": ["percolation_experiments.py", "simulation.py", "scientific_statistics.py"],
        "astrosat": ["astrosat_experiments.py", "scientific_statistics.py"],
    }
    if domain not in modules:
        raise ValueError("Cannot archive an implementation for an unsupported source")
    selected = modules[domain]
    if sequential:
        if domain != "percolation":
            raise ValueError("The explicit sequential workflow supports percolation only")
        selected = ["simulation.py", "scientific_statistics.py"]
    paths = []
    for name in selected:
        path = f"code/{name}"
        store.write_text(
            path,
            (
                Path(scientific_statistics.__file__)
                if name == "scientific_statistics.py"
                else Path(__file__).parent / name
            ).read_text(),
        )
        paths.append(path)
    store.write(
        "implementation.json",
        {
            "source_id": source.source_id,
            "source_sha256": source.sha256,
            "domain": domain,
            "files": paths,
            "origin": "Explicit legacy sequential configuration"
            if sequential
            else "Existing implementation selected for this run's scientific context",
            "framework_archive": "framework/source.zip",
        },
    )
    return paths
