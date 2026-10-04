# Paper and repository execution

New Source intake runs and Omnigent CLI runs without an explicit old configuration
use workflow v5 (`workflow: repository`). The Discovery overview combines the
former overview and final synthesis: simulation first, then result, what changed,
and the next experiment. Evidence and audit details are expandable.

## Inputs and specialist handoffs

Supply a PDF/Markdown paper. The UI's seed menu is fixed to Percolation and AstroSat;
other uploads/imports remain in the separate Uploaded paper selector. A validated
paper enables Start bounded run even with no repository URL.

A public `https://github.com/owner/repository` URL is optional in the UI. Without one,
`allow_paper_implementation: true` explicitly authorizes the same Omnigent reader,
literature researcher, critic, planner, experimenter and evaluator loop to implement a scoped
numerical test from the paper's equations or algorithm. Unsupported evidence,
missing data, invalid contracts and failed experiments still stop honestly. No
preset kernel or alternate decision backend replaces that process.

Paper-based runs record `code_origin: paper_implementation`, an empty repository
identity/inventory, original paper evidence, generated code, all sandbox trials,
and evaluator handoffs. They retain identical sandbox, sanity, replay, budget and
process checks, but do not require a call to author code that was never supplied.
The UI labels that distinction. Repository-based runs still require observed use
of pinned source; download failures never trigger paper-only execution.

The UI prefills a unique paper repository link; clearing it selects a paper-based
implementation. CLI configuration defaults retain repository-only behavior; the
explicit flag permits paper-based implementation when no URL is configured.

A unique GitHub link found in the extracted paper can fill the repository field.
Otherwise the user supplies it. That distinction and the paper content hash are
recorded; a supplied URL is not presented as an author endorsement. The selected
project seed remains arXiv:2607.24975v1. No GitHub URL was found in its extracted
text, so the UI uses a paper-based implementation unless a code source is supplied.

GitHub intake resolves the requested branch/tag/ref to a commit, saves the original
archive, and hashes every file. It rejects traversal, symbolic links, duplicate
paths, archives over 12 MB compressed or 30 MB expanded, and more than 2,000 entries.
It does not install the repository or run its setup/build scripts. Original papers
and repository licenses, when present, remain in the archive.

The reader and literature researcher receive immutable source inputs and run
concurrently (up to two workers, or serially when max_workers is one). The literature
researcher assesses known results and missing evidence independently of proposal
selection. Both validated outputs must complete before the critic starts. These
are separate recorded Omnigent sessions; the global request and time budgets still
apply, including repairs. Failure joins both workers before sealing partial results.

The reader receives the complete bounded paper plus repository inventory and
selects at most three directions and twelve files. Reading is limited to 80,000
bytes, with an explicit error instead of silent truncation. The critic reads those
files, checks feasibility and the independent literature assessment, and selects an accepted
direction. The planner preserves the hypothesis, compares screen and precision
tests, and defines controls, a metric, bounds, a sanity expectation, tolerance and
paired replicates before results exist. The experimenter generates code from the
files actually read. The evaluator receives measurements and can change the next
treatment or stop. No predefined percolation or Astrosat kernel is dispatched.
Reader/critic quotations must match the cited source page exactly; one recorded
correction attempt is allowed within the same call/time budget. Repeated invalid
evidence stops the run and remains available for inspection.

The Agents page shows observed request concurrency (including runtime waits), a
dependency graph, and a Routes & decisions tab. Every proposed direction remains
visible with its critique, accepted/rejected/unselected status, exact supporting
passages, both candidate tests, and the complete continuation/stop rationale at
every experiment. v4 archives additionally retain every allocation checkpoint and
its in-flight branches. A paused route or suggested next test is never labeled as
executed. Discovery shows full interpretation, experimental scope and limitations.

The player uses shared axes and a consistent cyan control / violet treatment /
amber highlight palette, dark high-contrast cards, a grid, scrubbing and reduced-motion
support. These are presentation changes to recorded data. v5 saves scalar samples,
so it cannot honestly reconstruct spatial lattice frames. The earlier v4 lattice
animations remain accessible in the run selector; previous runs are shown by default.
No archived result or original playable export is rewritten.
Malformed structured responses also get at most one correction per stage, with
the schema errors saved and the additional session counted against the call
budget. Failed experiments and numerical checks are never silently retried or
accepted by relaxing their thresholds.
Control, treatment and sanity-check objects must share the same explicit parameter
keys; prose such as “inherit the baseline” is rejected. The sandbox receives those
objects verbatim. Explanatory text belongs in the plan's rationale and controls.

All model stages use the existing Omnigent Sessions API and saved authentication.
The generated-code tool is dispatched by the Python supervisor after a structured
Omnigent handoff. The model session itself has no unrestricted shell. Its returned
program is executed using Omnigent 0.16.0's `resolve_sandbox` and backend
`wrap_launcher_argv`, verified against the installed implementation and
[Omnigent's OS sandbox documentation](https://omnigent.ai/docs/reference/configuration/os-sandbox).
This is an integration of Omnigent's sandbox primitive, not a claim that a new
native server policy or hosted custom tool has been provisioned.

## Executable code and limits

- Python 3.12: standard library, NumPy, SciPy, PyEphem 4.2.1 and the pinned repository's source.
  Other packages and automatic package installation are unsupported.
- C17: selected, read repository `.c` files and optional generated bridge source
  compile with `cc -std=c17 -O2 -fPIC -shared ... -lm`; Python calls the resulting
  library through `ctypes`. The dispatch contract accepts no compiler flags or shell
  commands. Generated code still has standard-library system calls within the OS
  boundary; numerical-purpose instructions are not a separate language-level sandbox.
- `simulate(parameters, seed, library)` returns a finite metric plus 2–120 recorded
  `times` and `values`. Both arms share an increasing axis. Every supplied uint32
  seed must be accepted, including sanity and replay jobs. Follow-up numerical
  parameters must not be restricted to the initial two configurations.
- Isolating an unchanged numerical method with Python `ast` is allowed when
  importing an entire upstream application requires unavailable dependencies.
  Compile it with its original source filename, disclose omitted physics/data,
  and preserve the method body. This is a scoped code check, not full application
  reproduction. Repository call paths or compiled/loaded C sources are recorded.
- macOS uses Omnigent Seatbelt; Linux uses Omnigent bubblewrap. Unsupported platforms
  or failed sandbox activation stop before executing the program. There is no
  unsandboxed fallback.
- Experiment processes have no network and receive a small explicit environment
  without authentication. Isolated paper/repository inputs and numerical libraries
  are read-only. Only disposable scratch is writable; the archive and host project
  are not write grants.
- Per invocation: default 60-second wall and CPU limits (configurable up to 180),
  combined stdout/stderr limit of 4 MB, file size limit of 8 MB per file, no core
  dumps, and 128 open descriptors. Each tool invocation is sequential. The
  supervisor kills its process group at exit/timeout and removes scratch.
- Linux additionally sets 2 GiB address-space and 256-process rlimits. These are
  not aggregate container/cgroup quotas. macOS has no enforced resident-memory or
  per-job process-count limit. Process-group cleanup is not a general guarantee
  against deliberately detached descendants. This prototype is for bounded local
  numerical experiments, not a hostile multi-tenant code service.

The sandbox controls filesystem/network access; it does not prove that an
agent-written scientific model is correct. Source-call tracing, exact replay and
sanity checks are useful evidence, not a defense against falsified scientific
results. Review the generated program and independently replicate it before
relying on its conclusions.

## Measurements and artifacts

The supervisor supplies paired seeds derived from the master seed, round and
replicate. It reserves `2 * replicates + 2` jobs per round, including a sanity
check and a repeated first control. Failed reservations remain counted as
requested work. Every raw trial is retained. Identical seeded baseline output
must replay exactly; metrics must stay within the planner's recorded bounds.
The planner may choose 4–32 paired replicates, capped by the run's `trials` limit.
The UI exposes this as maximum paired replicates. The code timeout covers the
entire experiment invocation, including both arms, sanity and replay jobs.

Differences use a paired-seed Student t interval at 95%. These are exploratory
intervals without correction for sequential selection or multiple hypotheses.
Deterministic algebraic checks can have zero paired uncertainty; that does not
measure model error or observational uncertainty. No numerical threshold alone
establishes novelty or real-world validity.

The viewer builds a trusted playable comparison from the first recorded trajectory
in each arm, on shared axes. It executes no archived HTML or generated code.
This generic view shows recorded scalar trajectories, not an invented spatial
reconstruction. It is separate from the all-seed numerical summary. Missing or
invalid trajectories prevent acceptance of that experimental result.
New runs also reject a pair of constant trajectories as a process visualization.
The raw outputs remain saved as diagnostics. This check does not prove a scientific
model correct: reviewers must still inspect inputs, physics and uncertainty.
Only the latest attempt per paper appears by default, even when it failed. History
is opt-in. A sealed, evaluated terminal run highlights exactly its final experiment;
earlier rounds appear in an audit table rather than repeated result panels.

Artifacts include `sources.json`, original sources, `repository/source.zip`,
`repository/manifest.json`, file reading scope, role requests/responses and session
IDs, reader/critic/planner outputs, generated implementation, `code/provenance.json`,
per-round specifications, execution stdout/stderr/exit status, trials, summaries,
process JSON/HTML and decisions. The outer manifest includes nested repository
manifests. Early v5 implementation responses can also be recovered from their
archived experimenter transcript without changing the archive.

Result-to-decision time is measured. No comparable manual baseline has been
measured, so no acceleration multiplier is claimed. Missing repository code,
dependencies, rejected proposals, code failures and inconclusive results remain
explicit outcomes and never trigger a switch to a preset experiment.

## Run and inspect

Use the existing configured Omnigent server/host; see README for startup.

```bash
uv sync --locked
.venv/bin/research run --paper /absolute/path/paper.pdf \
  --repository https://github.com/OWNER/REPO --repository-ref COMMIT \
  --output output/research/new-run
.venv/bin/research verify output/research/new-run
.venv/bin/research replay-code output/research/new-run --round 1 \
  --output output/replays/new-run-round-1
```

Verification and the UI need no model calls. `replay-code` runs the exact archived
program again in the current pinned sandbox environment and compares its raw trials;
it makes no model calls and writes a separate archive. Use a new output directory
for every run/replay. Explicit v3/v4 config files retain their original engines;
they do not become repository-driven results retroactively.

Real sandbox tests (on a host that permits Omnigent sandbox activation):

```bash
RUN_SANDBOX_TESTS=1 .venv/bin/pytest \
  tests/test_repository_execution.py::test_real_omnigent_sandbox -q
```

## AstroSat reset and reference-orbit experiment

The [fresh orbital validation](astrosat-orbital-validation.md) completed two live
experiments with exact replays. Its final recorded model-difference span is
0.20061 mag; scientific and observational limitations remain explicit.

At the user's request, six earlier `omnigent-repository-astrosat-*` attempts were
withdrawn from the active run list. Their sealed artifacts are retained under
`output/research-archive/20261004T0312Z-astrosat-withdrawn/`; `archive-index.json`
records the move and reason. The [historical validation record](repository-execution-validation.json)
preserves the earlier checks and labels them withdrawn. The former accepted result
was a prescribed-input brightness identity with constant trajectories, not a useful
orbital experiment. It must not be presented as the current scientific result.

The fresh configuration is `experiments/astrosat-orbital-fresh.json`. It asks Omnigent
to design a phase-function sensitivity experiment using unchanged AstroSat methods
and actual PyEphem propagation. The supporting reference orbit, input provenance
and geometry-only availability probe are in `examples/astrosat/reference-orbit/`.
The full retrieved PyEphem reference HTML remains in `data/references/pyephem/`.
The input is a historical IRIDIUM 80 pass near its 2009 TLE epoch, not the paper's
2021 Starlink dataset or independent observed photometry. All optical and timing
perturbations are explicitly assumed sensitivity inputs.

```bash
.venv/bin/research run --paper data/papers/2111.11268v1.pdf \
  --literature examples/astrosat/reference-orbit/orbital-inputs.md \
  --config experiments/astrosat-orbital-fresh.json --no-auto-literature \
  --output output/research/astrosat-new-unique-run
```

The configuration permits at most two rounds, ten agent calls, forty requested
simulation jobs and fifteen minutes. No automatic network retrieval or package
installation occurs inside the generated experiment. Supporting inputs are passed
to all planning and implementation roles; reader evidence must still cite the seed
paper, while the critic can also cite supporting sources. No observational accuracy,
novelty or acceleration multiplier is established by a successful computational run.

Two-minute walkthrough after a run completes:

1. **0:00–0:35:** Open Discovery overview. The latest paper run appears by default.
   Show its single final visualization, result and next experiment.
2. **0:35–1:10:** Open Agents & execution loops and inspect the actual specialist
   sessions, code handoff, sandbox tool output and evaluator decision.
3. **1:10–1:35:** Expand paper evidence and code. Show the pinned repository,
   reference orbital inputs, two candidate tests and declared scientific limitations.
4. **1:35–2:00:** Show artifact verification, exact code replay and earlier rounds
   in the audit history. State whether the hypothesis survived, not just whether
   the program ran. A failed run has no final highlight.


## Uploaded-paper launch validation

The [October 3 intake validation](paper-intake-validation.json) uploaded the pinned
Percolation PDF through the running HTTP upload API, submitted Start bounded run
without a repository, and verified redirection to the new agent workflow. All five
Omnigent specialist stages completed in 222.636 seconds, executing 18 sandbox jobs
(eight paired controls/treatments, sanity and replay). Archive verification passed;
an independent code replay matched with zero model calls.

The exploratory Manhattan-minus-L-lattice contrast was 0.04260 with a 95% paired
interval of [-0.08166, 0.16686]. The evaluator stopped because this was inconclusive
and recommended additional independent seed pairs. A completed workflow does not
imply a supported hypothesis or force a second experiment.

```bash
# Start a new bounded live run (new model calls; use a fresh output directory).
.venv/bin/research run --paper data/papers/2607.24975v1.pdf \
  --config experiments/paper-intake-validation.json \
  --output output/research/my-paper-intake-run
# Inspect/replay the saved validation without new model calls.
.venv/bin/research verify output/research/20261004T044804-332ed05f
.venv/bin/research replay-code output/research/20261004T044804-332ed05f \
  --output output/replays/my-paper-intake-replay
```

All valid uploads can initiate the workflow. Scientific feasibility remains an
agent decision: unsupported data/dependencies, weak proposals, invalid evidence,
failed measurements or finite budgets can stop a run with a recorded reason.

## Parallel specialist and route visibility validation

The bounded uploaded-paper run `20261004T051223-523d4336` completed two experiments
with seven Omnigent sessions and 36 sandbox jobs in 181.558 seconds. Reader and
literature requests overlapped for 30.875 seconds; this includes runtime waits,
not a measured acceleration multiplier. Both outputs preceded critique.

The first result changed the next treatment from L=16 to L=32 against the fixed
L=8 baseline. The evaluator then stopped at the two-experiment limit and proposed
independent confirmation. Both candidate directions and both test options remain
in the route ledger, including the accepted direction that was not executed.
Final artifacts verify, and independent replay matched without model calls. See
[the complete validation record](parallel-routes-validation.json).

```sh
uv run --locked python -m hacknation_databricks.research.cli verify output/research/20261004T051223-523d4336
uv run --locked python -m hacknation_databricks.research.cli replay-code output/research/20261004T051223-523d4336 --output output/replays/my-parallel-replay
```

Choose `20261003T232809Z-percolation` in the run selector for the earlier spatial
lattice demonstration. Its reconstructed frames use recorded seeds and the
archived recipe; the view is not new statistical evidence. The v5 run above
records scalar Monte Carlo running means, not lattice geometry.
