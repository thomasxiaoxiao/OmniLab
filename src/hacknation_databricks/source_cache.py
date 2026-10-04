"""Cache extracted source text until library files or configured inputs change."""

import os
from pathlib import Path

import streamlit as st

from hacknation_databricks.research.intake import library_sources


@st.cache_data(max_entries=8, ttl=60, show_spinner=False)
def _load(root: str, signature: tuple):
    return library_sources(Path(root))


def source_library(root: Path):
    files = list(root.glob("*/source.*"))
    configured = os.environ.get("RESEARCH_PAPER_PATH")
    if configured:
        files.extend([Path(configured), Path(configured + ".json")])
    signature = tuple(
        (str(p.resolve()), p.stat().st_mtime_ns, p.stat().st_size)
        for p in sorted(set(files))
        if p.is_file()
    )
    return _load(str(root.resolve()), (configured, signature))
