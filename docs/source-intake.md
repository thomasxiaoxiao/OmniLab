## Paper-first setup (October 3 update)

Source intake is the first and default navigation page. Its library and seed/literature
pickers share one content-deduplicated list: the two supplied papers
(2607.24975v1 and 2111.11268v1), explicitly imported documents, and an explicitly
configured project source. Arbitrary cached PDFs and generic “Full paper” aliases
are no longer included.

There is no Research example selector. New Omnigent UI runs request automatic
context: a specialist reads the full seed, returns its research question, summary,
exact supporting passages and a supported tool family. The supervisor validates
those passages before passing the context to downstream researchers. The original
request is saved in `requested_config.json`; resolved settings remain in
`config.json`, with `research_context.json` and the source-stage handoff as evidence.
Unsupported papers stop before simulation and retain their context and reason.
This does not add general-purpose experiment generation: executable tools remain
bounded to the existing percolation and synthetic transit experiments. The auxiliary
AnyJev path remains explicitly percolation-only; existing CLI configurations remain
reproducible. Automatic citation retrieval still follows references in the selected
paper and is separate from the built-in source choices.

# Source intake and execution visibility

Open the lab with `npm run dev`. The dedicated **Source intake** page accepts
saved local papers, PDF and Markdown uploads, and arXiv abstract/PDF links.
Choose the seed and up to three related documents on this page. The seed selection
survives navigation. The sidebar contains the shared run selector, while local
simulation budgets and the launch action live beside source selection.

The default launch profile is **Quick verification**: 32 trials per group,
four workers, four batches per direction, 20,000 simulation units and a 20-minute
wall-clock bound. Advanced budgets remain editable. Omnigent uses the configured
model and remains the default backend; the simulations execute locally.

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

**Agents & loops** projects saved event logs into a Step Functions style state
machine. Nodes group repeated specialist roles; decision roles use diamonds.
Solid arrows count recorded handoffs, including backward transitions. Dashed
self-loops mean the role was invoked multiple times, possibly in distinct sessions
or parallel tasks. They do not assert reuse of the same session. The separate
execution timeline retains individual instances and parallel dependencies.

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
**Export execution trace** downloads the complete projected JSON. The state machine
exports DOT; the execution timeline exports SVG. Active overview and agent views
refresh saved progress. Omnigent launches use the existing background worker;
intake and analysis do not launch research automatically.

Sealed runs continue to use the existing manifest/evidence checks. Damaged runs
remain quarantined. Older runs without the new lifecycle events can show their
recorded stages and artifacts, but missing session IDs remain unavailable.

## Compare and synthesize

**Original → follow-up** separates the published reference, the local baseline,
and implemented treatments. Compare each branch's latest cumulative snapshot,
its sample counts and uncertainty, then inspect the original and follow-up files.
Cumulative checkpoints are never summed as independent data.

**Final synthesis** pins the accepted checkpoint when the supervisor accepted a
goal. Other runs show their latest completed result as provisional or incomplete.
A finalized label requires a sealed, verified run. The UI preserves the evaluator's
reasoning and limitations even when the supervisor marks the goal achieved.
Charts use recorded simulation measurements; opening a page performs no new
simulation or inference. Raw dataset links, seeds and verification commands remain
available.

The paper map uses source titles and concepts from evidence-bearing proposals and
reviews. Edges distinguish recorded seed citations from shared evidence contexts.
Sources without evidence passages are labeled accordingly; missing or excluded
references remain visible in the retrieval audit. Select a paper for exact quotes,
page numbers, artifact provenance, search scope and missing evidence.

**Generated artifacts** distinguishes agent inputs/responses, original sources,
simulation CSVs, workflow records and reproduction files, with producing steps and
hashes. The separate session inventory shows actual agent IDs and session IDs.

## Verification

```bash
.venv/bin/pytest tests/test_intake.py tests/test_activity.py tests/test_intake_ui.py tests/test_frontend_views.py -q
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
