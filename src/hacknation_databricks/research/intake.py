"""Validated, content-addressed source library shared by the CLI and frontend."""

import argparse
import fcntl
import hashlib
import json
import os
import re
import tempfile
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from .sources import MAX_SOURCE_BYTES, Source, fetch_arxiv, read_source


def source_root() -> Path:
    return Path(os.environ.get("RESEARCH_SOURCES_DIR", "data/sources"))


def register_upload(
    filename: str, body: bytes, root: Path, *, provenance: dict | None = None
) -> Source:
    """Commit only after text extraction succeeds; retain the original bytes unchanged."""
    suffix = Path(filename).suffix.lower()
    if suffix not in {".pdf", ".md"}:
        raise ValueError("Upload a .pdf or .md file")
    if not body or len(body) > MAX_SOURCE_BYTES:
        raise ValueError("Source must be nonempty and at most 10 MiB")
    if suffix == ".pdf" and not body.startswith(b"%PDF"):
        raise ValueError("The uploaded file does not contain a PDF")
    if suffix == ".md" and b"\x00" in body:
        raise ValueError("Markdown must contain UTF-8 text, not binary data")
    digest = hashlib.sha256(body).hexdigest()
    directory = root / digest
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=root, prefix=".intake-") as staging:
        staged = Path(staging) / digest
        staged.mkdir()
        path = staged / f"source{suffix}"
        path.write_bytes(body)
        read_source(path)
        metadata = {
            "title": Path(filename.replace("\\", "/")).name[:240],
            "original_filename": Path(filename.replace("\\", "/")).name[:240],
            "kind": "full_text",
            "origin": "upload",
            "retrieved_at": datetime.now(UTC).isoformat(),
            **(provenance or {}),
            "sha256": digest,
            "bytes": len(body),
            "format": suffix.removeprefix("."),
            "intake_version": "source-intake-v1",
        }
        path.with_suffix(suffix + ".json").write_text(json.dumps(metadata, indent=2) + "\n")
        # Serializes the brief commit only; extraction and download hold no library lock.
        with (root / ".intake.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if not directory.exists():
                staged.rename(directory)
            return load_registered(root, digest)


def register_arxiv(link: str, root: Path) -> Source:
    path = fetch_arxiv(link, root / ".arxiv-cache")
    metadata = json.loads(path.with_suffix(".pdf.json").read_text())
    return register_upload(
        path.name, path.read_bytes(), root, provenance={**metadata, "origin": "arxiv"}
    )


def load_registered(root: Path, digest: str, source_id: str = "seed") -> Source:
    if not re.fullmatch(r"[a-f0-9]{64}", digest):
        raise ValueError("Invalid registered source identifier")
    directory = root / digest
    paths = [p for p in directory.glob("source.*") if p.suffix in {".pdf", ".md"}]
    if len(paths) != 1:
        raise ValueError("Registered source is missing or ambiguous")
    path = paths[0]
    for item in [directory, path, path.with_suffix(path.suffix + ".json")]:
        if item.is_symlink() or not item.resolve().is_relative_to(root.resolve()):
            raise ValueError("Registered source leaves the library")
    if not path.with_suffix(path.suffix + ".json").is_file():
        raise ValueError("Source provenance is missing")
    source = read_source(path, source_id=source_id)
    if source.sha256 != digest:
        raise ValueError("Registered source checksum does not match")
    return source


def list_sources(root: Path) -> tuple[list[Source], list[str]]:
    sources, issues = [], []
    if root.is_dir():
        for directory in sorted(root.iterdir()):
            if re.fullmatch(r"[a-f0-9]{64}", directory.name):
                try:
                    sources.append(load_registered(root, directory.name))
                except Exception:
                    issues.append(
                        f"Source {directory.name[:12]} failed validation; excluded from runs."
                    )
    return sources, issues


def library_sources(root: Path) -> tuple[list[Source], list[str]]:
    """Only the two supplied papers are built in; other sources require explicit intake."""
    sources, issues = list_sources(root)
    configured = os.environ.get("RESEARCH_PAPER_PATH")
    paths = [Path(configured)] if configured else []
    titles = {
        "2607.24975v1": "Strongly-connected percolation on directed lattices",
        "2111.11268v1": (
            "Astrosat: Forecasting satellite transits for optical astronomical observations"
        ),
    }
    paths.extend(
        Path("data/papers") / f"{identifier}.pdf" for identifier in ("2607.24975v1", "2111.11268v1")
    )
    seen = {source.sha256 for source in sources}
    for path in paths:
        if not path.is_file():
            continue
        try:
            source = read_source(path)
            if path.stem in titles:
                source = replace(source, title=f"{titles[path.stem]} · {path.stem}")
            if path.stem in titles:
                sources = [
                    replace(item, title=source.title) if item.sha256 == source.sha256 else item
                    for item in sources
                ]
            if source.sha256 not in seen:
                sources.append(source)
                seen.add(source.sha256)
        except Exception:
            issues.append(f"Source {path.name} failed validation; excluded from runs.")
    return sources, issues


def main() -> int:
    parser = argparse.ArgumentParser(description="Import PDF, Markdown or arXiv sources")
    parser.add_argument("--file", type=Path, action="append", default=[])
    parser.add_argument("--arxiv", action="append", default=[])
    parser.add_argument("--destination", type=Path, default=source_root())
    args = parser.parse_args()
    results = []
    for path in args.file:
        # Check size before loading a local file into memory.
        if path.stat().st_size > MAX_SOURCE_BYTES:
            raise ValueError("Source exceeds 10 MiB intake limit")
        results.append(register_upload(path.name, path.read_bytes(), args.destination))
    for link in args.arxiv:
        results.append(register_arxiv(link, args.destination))
    if not args.file and not args.arxiv:
        results, issues = list_sources(args.destination)
        if issues:
            print(json.dumps({"issues": issues}))
            return 1
    print(
        json.dumps(
            [
                {
                    "title": s.title,
                    "path": s.path,
                    "sha256": s.sha256,
                    "url": s.url,
                    "pages": len(s.pages),
                }
                for s in results
            ],
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
