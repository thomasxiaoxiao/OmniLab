# Source intake and execution visibility

Open the **Decision control room** with `npm run dev`. **Source intake** accepts
PDF and Markdown uploads and arXiv abstract/PDF links. It is also displayed on the
empty workspace screen. Imported sources become available in the sidebar as a
seed or related literature (at most three manually selected related documents).

Intake makes no model calls. Accepted originals live unchanged in
`data/sources/<sha256>/source.pdf` or `source.md`, with a provenance sidecar.
Set `RESEARCH_SOURCES_DIR` to use a different library. Duplicate content reuses
the first validated source and its provenance. Invalid or tampered entries are
excluded from the launch selector and reported in the library.

- Maximum 10 MiB per source, 100 PDF pages, and 180,000 extracted characters.
- PDFs need a text layer; scanned or empty PDFs require OCR before intake.
- Markdown must be UTF-8. The original bytes remain unchanged; normalized text
  is used for evidence matching. Form feeds delimit text pages in Markdown.
- Modern and legacy arXiv identifiers are supported. Unversioned links resolve
  through the official Atom API to a versioned identifier. Downloads and redirects
  are restricted to official arXiv hosts, with finite time and response-size limits.
- Versioned cached PDFs can be reused without a network request. If the metadata
  service cannot resolve an unversioned link, use a versioned link or upload a PDF.
- Each run copies originals and available provenance sidecars into `inputs/` and
  records source hashes, URL, retrieval time, and extracted text in `sources.json`.

The arXiv adapter follows the [official API version semantics](https://info.arxiv.org/help/api/user-manual.html#51-details-of-query-construction).
Intake does not extend the simulator's supported scientific experiment catalog.

## Reproduce intake without the UI

```bash
.venv/bin/python -m hacknation_databricks.research.intake --file paper.md --file paper.pdf
.venv/bin/python -m hacknation_databricks.research.intake --arxiv https://arxiv.org/abs/2607.24975v1
.venv/bin/python -m hacknation_databricks.research.intake  # List validated library entries
```

Pass a returned source path to `research run --paper PATH`; related files use
the existing repeated `--literature PATH` option. The frontend passes selected
sources through the same source reader and workflow.

## Inspect what actually ran

**Agents & loops** projects the saved event log into an execution graph, grouped
by the initial stages and each entered round. Only started work is drawn. An
additional round receives a repeat edge only when it appears in the event log.

Omnigent sessions are shown individually, including multiple calls within one
stage (for example validator and novelty evaluator). The inspector includes
session/agent/runner identity, start/end times, elapsed time, schema status,
available provider usage, request/response files, and produced artifacts.
The lifecycle distinguishes a completed agent response from a later failed
workflow stage. Partial responses and cancellation requests are retained on error.

AnyJev local inference and deterministic Python simulation use separate labels;
neither increments the Omnigent session count. Fixture/legacy scripted runs remain
labeled. There are no invented agent traces or simulated live sessions.

Select an execution step and artifact to preview or download its evidence.
**Export execution trace** downloads the complete projected JSON, and **Download
execution graph** saves the SVG. **Refresh
artifacts** reads updated saved events for running work. UI launch remains
synchronous; this change does not introduce a background job scheduler.

Sealed runs continue to use the existing manifest/evidence checks. Damaged runs
remain quarantined. Older runs without the new lifecycle events can show their
recorded stages and artifacts, but missing session IDs remain unavailable.

## Verification

```bash
.venv/bin/pytest tests/test_intake.py tests/test_activity.py tests/test_intake_ui.py -q
```

These checks cover exact-byte preservation, duplicate intake, malformed/scanned
PDFs, invalid UTF-8, context limits, checksum failures, link normalization,
unversioned-to-versioned resolution, redirect restrictions, two loop iterations,
multiple sessions in one stage, failed responses, fixture labeling, source-to-run
identity, related-document selection, and running validation before a gate exists.
Provider behavior in automated tests uses explicit test doubles.

Browser verification on October 3, 2026 exercised versioned and unversioned arXiv
links and imported the real 16-page
`2607.24975v1` PDF (73,812 extracted characters), uploaded PDF/Markdown files,
and confirmed the persistent source selector. The temporary synthetic Markdown
was removed after verification; the public arXiv source remains cached.
