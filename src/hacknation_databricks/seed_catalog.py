"""The two pinned demonstration papers; uploads never extend this catalog."""

from pathlib import Path

from .research.intake import source_root
from .research.sources import read_source
from .source_cache import source_library

SEED_PAPERS = (
    (
        "Percolation · arXiv:2607.24975v1",
        "2607.24975v1.pdf",
        "ec1c1fbd4d1a05ed60875020ea2f103def25cc012bf100ebfe82991a147bd8bb",
    ),
    (
        "AstroSat · arXiv:2111.11268v1",
        "2111.11268v1.pdf",
        "e56bf525c71437be590c99f6cb4697cb41442f05c5836d7f555c34851eca0ebf",
    ),
)


def seed_examples():
    registered, _ = source_library(source_root())
    by_hash = {source.sha256: Path(source.path) for source in registered}
    examples = {}
    for label, filename, digest in SEED_PAPERS:
        if digest in by_hash:
            examples[label] = by_hash[digest]
            continue
        path = Path("data/papers") / filename
        if path.is_file():
            try:
                if read_source(path).sha256 == digest:
                    examples[label] = path
            except (ValueError, OSError):
                pass
    return examples
