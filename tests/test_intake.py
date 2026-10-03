import io
import json

import httpx
import pytest
from pypdf import PdfWriter
from pypdf.errors import PdfReadError
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from hacknation_databricks.research import sources
from hacknation_databricks.research.intake import (
    list_sources,
    load_registered,
    register_arxiv,
    register_upload,
)


def text_pdf(text="A reproducible source with enough text to extract."):
    writer = PdfWriter()
    page = writer.add_blank_page(300, 400)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})}
    )
    stream = DecodedStreamObject()
    stream.set_data(f"BT /F1 12 Tf 20 100 Td ({text}) Tj ET".encode())
    page[NameObject("/Contents")] = writer._add_object(stream)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def test_markdown_preserved_deduplicated_and_tampering_detected(tmp_path):
    original = b"# Future work\n\nStudy **directed** percolation.\n"
    first = register_upload("../../paper.MD", original, tmp_path)
    second = register_upload("renamed.md", original, tmp_path)
    assert first.path == second.path
    assert first.title == "paper.MD"
    from pathlib import Path

    assert Path(first.path).read_bytes() == original
    assert first.retrieved_at and not first.url
    assert len(list_sources(tmp_path)[0]) == 1
    Path(first.path).write_text("modified")
    assert list_sources(tmp_path)[0] == []
    assert list_sources(tmp_path)[1]
    with pytest.raises(ValueError, match="checksum"):
        load_registered(tmp_path, first.sha256)


def test_pdf_extracts_and_records_provenance(tmp_path):
    source = register_upload("paper.pdf", text_pdf(), tmp_path)
    assert "reproducible source" in source.pages[0]
    assert source.kind == "full_text"
    assert list_sources(tmp_path) == ([source], [])


@pytest.mark.parametrize(
    "filename,body",
    [
        ("code.py", b"print(1)"),
        ("bad.md", b"\xff\xfe"),
        ("empty.md", b" \n"),
        ("scan.pdf", b"%PDF broken"),
        ("fake.pdf", b"html"),
        ("binary.md", b"a\x00b"),
    ],
)
def test_invalid_upload_never_enters_library(tmp_path, filename, body):
    with pytest.raises((ValueError, PdfReadError)):
        register_upload(filename, body, tmp_path)
    assert list_sources(tmp_path) == ([], [])
    assert not list(tmp_path.glob(".intake-*"))


def test_blank_scanned_and_large_sources_rejected(tmp_path):
    writer = PdfWriter()
    writer.add_blank_page(100, 100)
    buffer = io.BytesIO()
    writer.write(buffer)
    with pytest.raises(ValueError, match="OCR"):
        register_upload("scan.pdf", buffer.getvalue(), tmp_path)
    with pytest.raises(ValueError, match="10 MiB"):
        register_upload("big.md", b"x" * (sources.MAX_SOURCE_BYTES + 1), tmp_path)
    with pytest.raises(ValueError, match="context budget"):
        register_upload("long.md", b"x" * (sources.MAX_SOURCE_CHARACTERS + 1), tmp_path)


@pytest.mark.parametrize(
    "value,expected",
    [
        ("https://arxiv.org/abs/2607.24975", "2607.24975"),
        ("https://arxiv.org/pdf/2607.24975v2.pdf#page=2", "2607.24975v2"),
        ("arXiv:hep-th/9901001v1", "hep-th/9901001v1"),
        (" http://www.arxiv.org/abs/2607.24975v1 ", "2607.24975v1"),
    ],
)
def test_arxiv_link_normalization(value, expected):
    assert sources.arxiv_identifier(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "https://arxiv.org.evil/abs/2607.24975",
        "file:///etc/passwd",
        "https://user:secret@arxiv.org/abs/2607.24975",
        "../../paper",
        "https://arxiv.org:9000/abs/2607.24975",
        "2607.24975v0",
    ],
)
def test_arxiv_invalid_and_unsafe_links_rejected(value):
    with pytest.raises(ValueError):
        sources.arxiv_identifier(value)


def test_unversioned_arxiv_resolves_version_then_caches_exact_pdf(tmp_path, monkeypatch):
    calls = []
    pdf = text_pdf()

    def download(url, limit):
        calls.append(url)
        if "/api/" in url:
            return b"""<feed xmlns="http://www.w3.org/2005/Atom"><entry>
            <id>http://arxiv.org/abs/2607.24975v3</id><title>A paper</title>
            </entry></feed>"""
        return pdf

    monkeypatch.setattr(sources, "_arxiv_bytes", download)
    first = register_arxiv("https://arxiv.org/abs/2607.24975", tmp_path)
    assert first.url == "https://arxiv.org/abs/2607.24975v3"
    assert first.title == "A paper"
    assert len(calls) == 2 and calls[-1].endswith("/2607.24975v3")
    second = register_arxiv(first.url, tmp_path)
    assert second == first and len(calls) == 2
    from pathlib import Path

    assert Path(first.path).read_bytes() == pdf
    metadata = json.loads(Path(first.path + ".json").read_text())
    assert metadata["origin"] == "arxiv" and metadata["arxiv_id"] == "2607.24975v3"


def test_redirect_cannot_escape_arxiv(monkeypatch):
    from contextlib import contextmanager

    calls = []

    @contextmanager
    def redirect(*args, **kwargs):
        calls.append(args)
        yield httpx.Response(302, headers={"location": "http://127.0.0.1/secret"})

    monkeypatch.setattr(sources.httpx, "stream", redirect)
    with pytest.raises(ValueError, match="allowed"):
        sources._arxiv_bytes("https://arxiv.org/pdf/2607.24975v1", 1000)
    assert len(calls) == 1


def test_download_failure_leaves_no_accepted_source(tmp_path, monkeypatch):
    monkeypatch.setattr(sources, "_arxiv_bytes", lambda *args: b"%PDF malformed")
    with pytest.raises(PdfReadError):
        sources.fetch_arxiv("2607.24975v1", tmp_path)
    assert not list(tmp_path.iterdir())
