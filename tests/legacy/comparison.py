"""Legacy presentation fixtures never installed with the application."""

from hacknation_databricks.research.comparison import save_comparisons as save

from .process_adapters import build_legacy_process


def save_comparisons(store, report, config, sources):
    return save(store, report, config, sources, process_builder=build_legacy_process)
