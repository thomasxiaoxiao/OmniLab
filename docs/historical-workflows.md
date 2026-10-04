# Historical workflow descriptions

These descriptions preserve the previous README's v3/v4 implementation history.
**Their launch commands are retired.** Preset engines and domain visualization
adapters now live only in `tests/legacy/` for archive regression coverage and are
excluded from the installed application. The current CLI accepts only Omnigent
and agent-generated experiments. Saved original outputs remain immutable evidence
of those older implementations, not evidence of new agent-authored experiments.
See [current execution](repository-execution.md) for supported commands.

The following sections also document retained v3/v4 workflows and historical runs.
Their fixed kernels and AnyJev decisions describe those explicit configurations.

The default frontend is now the **OmniLab scientific discovery lab**, following
the research workflow in `docs/overall-design.md`. It records bounded choices,
execution gates, evidence and implementations from saved research runs. See the
[decision tracking guide](docs/decision-tracking.md) for controls, enforcement,
Jev-style contracts and limitations. Run locally with `npm run dev`.

**Omnigent & policies** centralizes the selected run's session context, reported
usage, immutable resource limits and checkpoint enforcement evidence. The research
pages explain the framework's contribution at each step. **Next-run controls** saves
per-profile resource limits for this app session; select that profile in Source
intake to apply them to a new Omnigent run. These are supervisor limits around the
existing Omnigent runtime, not edits to native Omnigent policy configuration.
Archived instructions are shown as instructions, not proof of sandbox enforcement.

Discovery overview now leads with **What changed our next move?** Select a
checkpoint to compare the prior plan, incoming measurements, Omnigent decision,
and action actually executed. The shared-runtime evidence shows session identities,
archived common request constraints, responses and supervisor-enforced gates.
Explicit parent handoffs distinguish new work from batches already in flight.
Saved runs are labeled; native Omnigent policy attestation is not inferred from
a shared agent ID. See the [demo walkthrough](docs/adaptive-demo.md).

## Scientific discovery workflow

The retained **adaptive Omnigent workflow (v4)** runs source and citation researchers
in parallel, consolidates up to three experimental branches, and asks a decision
agent to reallocate work after every completed simulation batch. Standard runs
allow eight batches per direction and six workers; extended profiles and editable
finite budgets support longer exploration. Independent seed streams, cumulative
controls, goal gates and final validation replace a fixed two-round demo.

Both the percolation example and an **Astrosat transit-uncertainty** example are
implemented. See [adaptive workflow, science and reproduction commands](docs/adaptive-discovery.md).
Run Astrosat with `--paper data/papers/2111.11268v1.pdf --config examples/astrosat/discovery.json`.
The Astrosat experiment uses explicit synthetic error assumptions; it does not
reproduce historical satellite forecasts. Scientific novelty remains unverified.

Both examples completed live Omnigent runs with independent agent review and
verified artifacts. See the [measured validation record](docs/adaptive-validation.json)
and [two-minute walkthrough](docs/adaptive-demo.md). Compact results are saved in
each example's `adaptive-results/` directory; full archives remain in `output/research/`.

The following v3 description documents the retained sequential compatibility path.

Every completed analysis must export `comparison/process.html`, a self-contained
playable comparison of the original and proposed simulated worlds, and
`comparison/process.json`, its validated states, parameters and input hashes.
Percolation reconstructs the recorded directed lattices and animates their
construction; Astrosat animates the saved predicted/true local transit and compares
the nominal and expanded alert boundaries. These illustrate recorded samples;
they do not replace aggregate evidence or improve the orbit estimator.

The v3/v4 supervisor blocks completion as `visualization_incomplete` if an implemented
experiment cannot produce valid process outputs. Missing simulations remain
explicitly unavailable. A generic data contract and adapter registry support new
scientific implementations without rewriting the player or completion gate;
v3/v4 continue to use explicit domain adapters. Repository runs use generated code
and recorded scalar trajectories; malformed samples fail their experiment stage.

For v3/v4 archives, `comparison/simulation.svg` retains the numerical comparison chart,
`comparison/summary.txt` the numerical sentence, and `comparison/comparison.json`
the measurements, uncertainty, saved inputs and source references.
`comparisons/NNN/` retains these outputs for every completed checkpoint.
The consolidated **Discovery overview** displays and downloads
these outputs; older sealed runs reconstruct a labeled view without rewriting their archives.
**Agents & loops** opens each specialist's complete archived prompt, inputs and
constraints when its timeline box is clicked. Returned actions and downstream work
appear below; session identities, counts and exports are under Run details and
exports. Shared `research-worker` names do not imply identical tasks.

The primary **Discovery overview** page shows the hypothesis and source evidence,
competing screening/precision tests, selected trial budget, measured effect and
result-driven next action. **Agents & loops** retains the session and handoff audit.
Older runs remain inspectable and explicitly lack the new decision records.
See the [v3 refactor notes](docs/discovery-refactor.md) for contracts and verification.

Workflow v3 uses the critic's accepted selection, then asks the planner to compare
two bounded sampling tests. After validation and reference review, a separate
Omnigent specialist chooses repeat, literature review or stop. The supervisor
checks the chosen simulation budget and enforces scientific gates before another
round. Python executes the allowlisted simulations; agents never execute generated
code. Both tests study the same hypothesis at different sampling precision.
Elapsed workflow time and simulation counts are recorded. A speedup multiplier
remains unverified until a comparable baseline is measured.

```bash
.venv/bin/research run --config examples/percolation/discovery.json
```

## Live Codex subscription workflow

The earlier `codex-full-paper` run verified six Codex subscription role sessions.
Those sessions read the full seed paper, critique directions, review retrieved
references, plan and evaluate the experiment, then compare its contribution with
prior work. API-key support remains available; no credential is written to a bundle.

```bash
uv sync --locked
.venv/bin/research configure-agent --auth subscription
# In separate terminals:
bash scripts/research-runtime.sh server
bash scripts/research-runtime.sh host
# Once connected, in your working terminal:
bash scripts/research-runtime.sh status
.venv/bin/research run --backend omnigent \
  --config examples/percolation/codex-live.json \
  --output output/research/my-codex-run
.venv/bin/research verify output/research/my-codex-run
npm run dev
```

This uses saved `codex login` authentication. `configure-agent` uses your configured
Codex model unless `--model` or `RESEARCH_MODEL` is supplied. The helper prefers the
current CLI bundled with ChatGPT on macOS; `OMNIGENT_CODEX_PATH` overrides it.
Stop the two foreground services with Ctrl-C. Services bind to loopback only.
`status` saves the server URL and host ID in ignored `.runtime/research.env`.

In the UI select **codex-full-paper**, then **Discovery overview**. The saved run
needs no model call. It contains 4,096 trials plus eight seed replays and an
**incremental extension** verdict. Full results, boundaries and commands are in
[the live-run report](docs/codex-live-run.md). The evaluator completes automatically;
there is no mandatory human-review step. A scoped agent assessment is not a claim
of global scientific priority.

## Local decision-only alternative

The CLI and frontend default to **Omnigent**. The optional `--backend anyjev`
mode uses **AnyJev 0.2.0 with a local Qwen3 4B model**. The model scores
closed choices; it generates no prose, tool calls, or executable code. It chooses
source evidence, critiques proposals, selects the most realistic accepted direction,
authorizes the experiment, and judges the measurements. Python enforces the allowed
experiments, ordered stages, numerical checks and resource limits. There is no
scripted decision backend or automatic fallback.

The local inference adapter uses MLX on an Apple Silicon Mac (verified on a 24 GiB
machine). The pinned 4-bit model download is approximately 2.3 GB and needs no
model account. Other platforms can inspect artifacts and run tests; local inference
requires an appropriate adapter. See [decision runtime](docs/decision-runtime.md).

```bash
uv sync --locked
uv run --locked research prepare-model
uv run --locked research fetch --arxiv-id 2607.24975v1
uv run --locked research run --backend anyjev \
  --config examples/percolation/decisions.json \
  --output output/research/my-decision-run
uv run --locked research verify output/research/my-decision-run
npm run dev
```

Use a new output directory for each run. The default input is the full seed PDF.
Identical simulation parameters and seeds produce identical trial CSVs; model
choices and their complete option distributions are recorded separately. A missing
model, ambiguous choice or rejected plan stops execution and preserves the audit.
The reader reviews retrieved exact passages across all source pages, not every
word of the full PDF; the retrieval scope is recorded for each decision.

`preferred_experiment` restricts eligibility; the model must still approve it.
Add supplied literature with repeated `--literature /path/to/paper.pdf` flags.
The small-lattice baseline is a consistency check, not high-precision reproduction.
AnyJev L0 scores are **uncalibrated option weights**, not confidence in scientific
truth. The novelty gate still requires numerical evidence and multiple sources;
passing it advances a scoped automated candidate, never a global discovery claim. CLI exit
code 2 denotes a blocked, rejected, ambiguous, failed or interrupted run.

See the [implementation contract](docs/research-implementation.md),
[remaining TODOs](docs/research-todos.md), and [demo walkthrough](docs/research-demo.md).
Measured results and reproduction commands are in the
[local validation report](docs/local-validation.md).

