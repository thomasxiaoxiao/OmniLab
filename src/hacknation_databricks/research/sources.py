"""Immutable source intake and mechanically checked, page-local evidence."""

import hashlib
import json
import re
import tempfile
import time
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlencode, urljoin, urlsplit

import httpx
from pypdf import PdfReader

from .models import Evidence

MAX_SOURCE_BYTES = 10 * 1024 * 1024
MAX_SOURCE_CHARACTERS = 180_000


def normalize(text: str) -> str:
    return " ".join(text.replace("\x00", "").split())


@dataclass(frozen=True)
class Source:
    source_id: str
    title: str
    url: str
    sha256: str
    pages: tuple[str, ...]
    kind: str
    path: str
    retrieved_at: str | None = None

    def payload(self) -> dict:
        return asdict(self)

    def supports(self, evidence: Evidence) -> bool:
        return (
            evidence.source_id == self.source_id
            and 1 <= evidence.page <= len(self.pages)
            and normalize(evidence.quote) in self.pages[evidence.page - 1]
        )


def read_source(path: Path, source_id: str = "seed", url: str = "") -> Source:
    if path.suffix.lower() not in {".pdf", ".md", ".txt"}:
        raise ValueError("Expected a PDF, Markdown, or plain-text source")
    if path.stat().st_size > MAX_SOURCE_BYTES:
        raise ValueError("Source exceeds 10 MiB intake limit")
    raw = path.read_bytes()
    if path.suffix.lower() == ".pdf":
        reader = PdfReader(path)
        if reader.is_encrypted or len(reader.pages) > 100:
            raise ValueError("Expected an unencrypted PDF with at most 100 pages")
        pages = tuple(normalize(p.extract_text() or "") for p in reader.pages)
    else:
        pages = tuple(normalize(p) for p in raw.decode("utf-8").split("\f"))
    if not any(pages):
        raise ValueError("No source text; scanned PDFs need an explicit OCR step")
    if sum(map(len, pages)) > MAX_SOURCE_CHARACTERS:
        raise ValueError("Source exceeds context budget; no text was silently truncated")
    metadata_path = path.with_suffix(path.suffix + ".json")
    metadata = json.loads(metadata_path.read_text()) if metadata_path.exists() else {}
    digest = hashlib.sha256(raw).hexdigest()
    if metadata.get("sha256", digest) != digest:
        raise ValueError("Source no longer matches its intake checksum")
    return Source(
        source_id,
        metadata.get("title", path.stem),
        url or metadata.get("url", ""),
        digest,
        pages,
        metadata.get("kind", "full_text"),
        str(path),
        metadata.get("retrieved_at"),
    )


def check_evidence(evidence: Evidence, sources: list[Source]) -> None:
    if not any(source.supports(evidence) for source in sources):
        raise ValueError(f"Untraceable evidence: {evidence.source_id}, page {evidence.page}")


ARXIV_ID = r"(?:\d{4}\.\d{4,5}|[a-z][a-z.-]*/\d{7})(?:v[1-9]\d*)?"
ARXIV_HOSTS = {"arxiv.org", "www.arxiv.org", "export.arxiv.org"}


def arxiv_identifier(value: str) -> str:
    """Accept official abstract/PDF links and modern or legacy identifiers only."""
    value = value.strip().removeprefix("arXiv:")
    if "://" in value:
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"https", "http"}
            or parsed.hostname not in ARXIV_HOSTS
            or parsed.username
            or parsed.password
            or parsed.port is not None
            or parsed.query
        ):
            raise ValueError("Use an arxiv.org abstract or PDF link")
        match = re.fullmatch(r"/(?:abs|pdf)/(.+)", parsed.path)
        value = match.group(1) if match else ""
    value = value.removesuffix(".pdf")
    if not re.fullmatch(ARXIV_ID, value):
        raise ValueError("Use an arXiv link or identifier, for example 2607.24975v1")
    return value


def _arxiv_bytes(url: str, limit: int) -> bytes:
    """Bounded public downloads; redirects cannot escape official arXiv hosts."""
    started = time.monotonic()
    for _ in range(4):
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https"
            or parsed.hostname not in ARXIV_HOSTS
            or parsed.username
            or parsed.password
            or parsed.port is not None
        ):
            raise ValueError("arXiv redirected outside the allowed download hosts")
        with httpx.stream(
            "GET",
            url,
            timeout=30,
            follow_redirects=False,
            headers={"User-Agent": "HackNationResearch/0.1 (public paper intake)"},
        ) as response:
            if response.is_redirect:
                url = urljoin(url, response.headers["location"])
                continue
            response.raise_for_status()
            chunks, length = [], 0
            for chunk in response.iter_bytes():
                length += len(chunk)
                if length > limit:
                    raise ValueError("arXiv response exceeds intake size limit")
                if time.monotonic() - started > 60:
                    raise TimeoutError("arXiv intake time limit exceeded")
                chunks.append(chunk)
            return b"".join(chunks)
    raise ValueError("Too many arXiv redirects")


def resolve_arxiv(value: str) -> tuple[str, str]:
    identifier = arxiv_identifier(value)
    if re.search(r"v[1-9]\d*$", identifier):
        return identifier, f"arXiv:{identifier}"
    body = _arxiv_bytes(
        "https://export.arxiv.org/api/query?" + urlencode({"id_list": identifier}), 1024 * 1024
    )
    if b"<!DOCTYPE" in body.upper() or b"<!ENTITY" in body.upper():
        raise ValueError("Unexpected arXiv metadata")
    root = ET.fromstring(body)
    ns = {"a": "http://www.w3.org/2005/Atom"}
    entry = root.find("a:entry", ns)
    if entry is None:
        raise ValueError("arXiv paper not found")
    pinned = arxiv_identifier(entry.findtext("a:id", "", ns))
    if re.sub(r"v\d+$", "", pinned) != identifier or not re.search(r"v\d+$", pinned):
        raise ValueError("arXiv did not resolve a matching immutable version; use a versioned link")
    return pinned, normalize(entry.findtext("a:title", f"arXiv:{pinned}", ns))


def fetch_arxiv(arxiv_id: str, destination: Path) -> Path:
    arxiv_id, title = resolve_arxiv(arxiv_id)
    destination.mkdir(parents=True, exist_ok=True)
    path = destination / f"{arxiv_id.replace('/', '_')}.pdf"
    if path.exists():
        # A successful prior download is immutable and can be used without network.
        read_source(path)
        return path
    url = f"https://arxiv.org/pdf/{arxiv_id}"
    body = _arxiv_bytes(url, MAX_SOURCE_BYTES)
    if len(body) > MAX_SOURCE_BYTES or not body.startswith(b"%PDF"):
        raise ValueError("arXiv did not return a PDF within the size limit")
    metadata = {
        "title": title,
        "arxiv_id": arxiv_id,
        "url": f"https://arxiv.org/abs/{arxiv_id}",
        "download_url": url,
        "retrieved_at": datetime.now(UTC).isoformat(),
        "sha256": hashlib.sha256(body).hexdigest(),
        "kind": "full_text",
    }
    with tempfile.TemporaryDirectory(dir=destination, prefix=".download-") as staging:
        temporary = Path(staging) / path.name
        temporary.write_bytes(body)
        read_source(temporary)  # Full text validation before a source enters the cache.
        sidecar = temporary.with_suffix(".pdf.json")
        sidecar.write_text(json.dumps(metadata, indent=2) + "\n")
        sidecar.replace(path.with_suffix(".pdf.json"))
        temporary.replace(path)
    return path
