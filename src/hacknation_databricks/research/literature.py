"""Bounded reference retrieval from citations, with explicit omissions and provenance."""

import re
from pathlib import Path

from .sources import Source, fetch_arxiv, read_source


def cited_arxiv(source: Source) -> list[dict]:
    found = []
    seen = set()
    for page, text in enumerate(source.pages, 1):
        for match in re.finditer(r"arxiv\s*:\s*(\d{4}\.\d{4,5}(?:v[1-9]\d*)?)", text, re.I):
            identifier = match.group(1)
            if identifier.split("v")[0] in source.url or identifier in seen:
                continue
            seen.add(identifier)
            found.append({"arxiv_id": identifier, "page": page, "quote": match.group(0)})
    return found


def retrieve_references(
    source: Source, destination: Path, *, existing: list[Source] = (), limit: int = 3
) -> tuple[list[Source], dict]:
    if not 1 <= limit <= 4:
        raise ValueError("Reference retrieval is limited to 1–4 papers")
    records = cited_arxiv(source)
    sources = []
    digests = {s.sha256 for s in [source, *existing]}
    characters = sum(sum(map(len, s.pages)) for s in [source, *existing])
    for index, record in enumerate(records):
        if index >= limit:
            record["status"] = "not_requested_budget"
            continue
        try:
            path = fetch_arxiv(record["arxiv_id"], destination)
            reference = read_source(path, source_id=f"ref_{record['arxiv_id'].replace('.', '_')}")
            record.update(
                url=reference.url,
                sha256=reference.sha256,
                path=str(path),
                pages=len(reference.pages),
            )
            if reference.sha256 in digests:
                record["status"] = "duplicate"
            elif characters + sum(map(len, reference.pages)) > 180_000:
                record["status"] = "not_reviewed_context_budget"
            else:
                record["status"] = "retrieved_for_review"
                sources.append(reference)
                digests.add(reference.sha256)
                characters += sum(map(len, reference.pages))
        except Exception as exc:
            record.update(status="unavailable", error_type=type(exc).__name__)
    return sources, {
        "method": "Explicit arXiv citations in seed text; "
        "immutable version resolution and full PDF retrieval",
        "scope": "Bounded cited-reference review; non-arXiv references and uncited "
        "literature are not searched. Omitted sources are not evidence of novelty.",
        "max_downloads": limit,
        "records": records,
    }
