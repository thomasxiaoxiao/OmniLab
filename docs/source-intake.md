# Paper-specific setup and isolation

Source intake has one **Paper** selector, initially containing only the pinned
Percolation and AstroSat examples. A visible drop zone accepts PDF/Markdown papers;
arXiv imports and uploads join the same selector. Content-identical copies of a
seed remain one entry. Related literature is retrieved from the selected paper's
citations; the CLI also accepts explicit `--literature` inputs.

Changing the paper filters runs by its content hash. Originals and provenance remain
in each run's evidence vault. The repository workflow uses live Omnigent reader,
literature, critic, planner, experimenter and evaluator sessions. Agents generate
the simulation and scene code from the paper or an optional pinned repository;
no preset scientific kernel executes. See [execution details](repository-execution.md).
Historical workflow descriptions are retained in [historical-workflows.md](historical-workflows.md).

# Source intake and execution visibility

Open the lab with `npm run dev`. The dedicated **Source intake** page accepts
saved local papers, PDF and Markdown uploads, and arXiv abstract/PDF links.
Choose the seed on this page. The seed selection
survives navigation. The sidebar contains the shared run selector, while local
simulation budgets and the launch action live beside source selection.

The default launch profile is **Standard exploration**, with up to 32 paired
replicates per experiment, eight experiments and a one-hour wall-clock bound.
Budgets remain editable. Reader and literature requests can run concurrently, with
at most two simultaneous specialist requests in this workflow. All decision-making
and experimental roles use Codex through Omnigent.

**Start bounded run** immediately opens **Agents & execution loops**. It follows
the preallocated run ID, including preparation before the first artifact exists,
then refreshes execution steps and downloadable artifacts every five seconds.
A running banner changes to an explicit finished or stopped outcome. A failed
preflight cannot display another run's results as the new experiment.

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

**Agents & execution loops** projects saved event logs into a Step Functions style state
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

**Discovery overview** owns the research highlights. It compares the cited
original-paper result with the agent-selected proposed simulation, then shows the
local control, uncertainty, decision change, recipe and data for that checkpoint.
Published asymptotic estimates remain distinct from finite-size measurements.
The separate Original → follow-up page has been removed. Cumulative checkpoints
are never summed as independent data.

**Final synthesis** pins the accepted checkpoint when the supervisor accepted a
goal. Other runs show their latest completed result as provisional or incomplete.
A finalized label requires a sealed, verified run. The UI preserves the evaluator's
reasoning and limitations even when the supervisor marks the goal achieved.
Charts use recorded simulation measurements; opening a page performs no new
simulation or inference. Raw dataset links, seeds and verification commands remain
available.

Final synthesis expands the highlight into measurements, validation, retained
branch outcomes, elapsed-time measurements and the next experiment. Paper
exploration is removed from this page; exact supporting passages remain in the
comparison assumptions and original source artifacts.

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

## Inspecting live work and connection failures

The source page shows live exploration progress after launch. The execution timeline
opens by default; turn off **Follow newest worker step** to inspect an earlier call.
Worker instructions come from the archived request. Session IDs, usage, schema
checks and lifecycle events are under **Technical details**. Simulation steps show
archived Python modules, specifications and actual saved datasets. **Download as
Parquet** converts the complete selected CSV for export; it does not modify the run.

A saved upload and a working agent runtime are separate checks. Launch checks the
Omnigent connection before fetching references and retains an actionable error if
the server or host is unavailable. Start the server and host with
`bash scripts/research-runtime.sh server` and `bash scripts/research-runtime.sh host`,
then run `bash scripts/research-runtime.sh status` to record the host. Restarting a
failed exploration creates a new run; the failed archive remains intact.

The October 3 Covasim upload passed extraction (32 pages). After restoring the
runtime, its live context worker returned `unsupported_source`: the existing
percolation and transit tools cannot test epidemiological interventions. General
paper intake does not imply a general-purpose experiment execution engine.
