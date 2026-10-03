# HackNation Databricks

Reproducible research and validation workspace with a Streamlit decision tracker,
seeded experiments, saved evidence and a health endpoint at `/_stcore/health`.
The current research scope follows `docs/overall-design.md` and `AGENTS.md`.
`hackthon-instruction.pdf` is the corrected Agentic Scientific Discovery challenge
brief. Omnigent must orchestrate the live discovery workflow; the earlier housing
challenge requirements are superseded.

The default frontend is now the **Omnigent scientific discovery lab**, following
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

The current **adaptive Omnigent workflow (v4)** runs source and citation researchers
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

Every completed analysis now exports `comparison/simulation.svg` (original versus
proposed simulated results), `comparison/summary.txt` (one numerical sentence),
and `comparison/comparison.json` (measurements, uncertainty, saved inputs and source
references). `comparisons/NNN/` retains the same outputs for each completed
checkpoint. Runs without measurements export an explicit unavailable result.
The **Discovery overview** and **Final synthesis** pages display and download
these outputs; older sealed runs derive the view without rewriting their archives.
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

## Optional API-key and Databricks routes

Omnigent 0.16.0 is pinned. For future API usage, set `OPENAI_API_KEY` in your
private environment or `.env`, then configure the SDK harness:

```bash
.venv/bin/research configure-agent --auth api-key --model YOUR_MODEL_ID
# Restart the server and host with the key available in their environment.
```

The generated `agents/local/config.yaml` contains model/profile names, never keys,
and is ignored by Git. The subscription harness excludes `OPENAI_API_KEY` from its
Codex child; switching to API usage is explicit. API-key inference was not exercised.

For an existing Databricks workspace:

```bash
uv sync --locked --extra databricks
.venv/bin/research configure-agent --model YOUR_SERVING_MODEL_ID \
  --databricks-profile YOUR_EXISTING_PROFILE
```

For a remote Omnigent server, set `OMNIGENT_SERVER_URL`, `OMNIGENT_HOST_ID`, and
`OMNIGENT_API_TOKEN` if required. Non-loopback servers must use HTTPS. Each role
gets a new host runner; incomplete requests are interrupted and runner cleanup is
requested on exit. The SDK can also bind an explicitly pre-existing compatible
runner when no host ID is set. `research doctor --spec agents/local` checks the
bundle only; completed streaming responses establish live execution.

Optional MLflow export verifies artifact hashes before logging parameters,
metrics and the run directory. Local export has been exercised; cloud export
requires an authorized workspace and tracking configuration.

```bash
uv sync --locked --extra tracking
mkdir -p .runtime
.venv/bin/research log-mlflow output/research/my-validation \
  --tracking-uri sqlite:///.runtime/research-mlflow.db \
  --experiment research-validation
# For an existing Databricks tracking setup, use --tracking-uri databricks.
```

## Development

Prerequisites: Git, Python 3.12 (uv can install it), uv, Node.js 22 or newer,
and GitHub CLI authenticated with access to this repository.

```bash
uv sync --locked
npm ci
cp .env.example .env
npm run dev
```

Development serves http://127.0.0.1:8000 with reload. The PM2 deployment uses
http://127.0.0.1:8010. Edit `.env` for application settings; credentials, local
datasets, environments, runtime state, and logs are ignored by Git.

```bash
uv add <package>        # Updates pyproject.toml and uv.lock together
uv add --dev <package>
npm run check          # Lint, formatting, tests, and PM2 config syntax
uv run ruff format .
```

Commit `uv.lock` and `package-lock.json`. Use feature branches and pull requests
after the initial bootstrap. CI checks all PRs and pushes to `main`.

## Processes and continuous deployment

```bash
npm start              # Start/restart the app under PM2
npm run status
npm run logs
npm run stop
npm run cd:start       # Start the deployment worker
npm run cd:logs
npm run cd:stop        # Pause automatic deployment; keep app running
npm run deploy         # Check for and deploy the latest main commit once
npm run save           # Save this project's PM2 process list
npm run startup        # Install macOS login service after saving
```

The worker checks `origin/main` every 60 seconds and automatically promotes its
latest commit without waiting for GitHub CI, per the temporary project policy.
CI still runs for visibility. To restore the gate, run
`DEPLOY_REQUIRE_CI=1 npm run cd:start` (and set it for one-off deploys).
The worker exports that commit into a new
`.runtime/releases/` directory, installs its locked production dependencies,
and restarts the app. PM2 must report the expected revision online and Streamlit's
HTTP health check must pass before recording
the release. A failed health check restores the previous release. The deployment
lock prevents overlapping runs. Working files and the development `.venv` are
never reset or reused by deployment.

PM2 runs in `.runtime/pm2`, isolated from other projects. Use the npm commands
above; plain global `pm2 status` addresses a different daemon. Python runs in
fork mode with one worker; restarts can cause a brief interruption.

See [deployment operations](docs/deployment.md) for login startup, configuration,
rollback, and moving to an always-on host.

## Project layout

- `src/hacknation_databricks/`: Python package and thin Streamlit interface
- `tests/`: UI and deployment safety checks
- `scripts/`: process and deployment operations
- `.github/`: CI, issue template, and PR template
- `hackthon-instruction.pdf`: supplied challenge brief

The housing-law starter dataset is not part of this research implementation.
Research source intake and all simulations can run independently of cloud setup.

## Source intake and agent visibility

**Source intake** accepts saved papers, uploads and versioned arXiv inputs. The UI
fixes the researcher to **Codex + Omnigent** and the decision agent to **AnyJev +
Omnigent**. Standard exploration is the default budget profile; finite budget
controls remain available. Starting a run immediately opens **Agents & execution
loops**, follows that exact run, refreshes generated files and execution steps,
and distinguishes starting, running, stopped and completed outcomes.

AnyJev is a local bounded scoring tool following a Codex assessment session in
Omnigent, not a native hosted Omnigent harness. Both the assessment and final
selection are archived; ambiguity stops the run for review. The existing CLI
retains Codex decisions unless its adaptive config sets `decision_backend` to
`anyjev`. UI users cannot change agent backends. Existing archives keep their
original runtime identities.

**Discovery overview** owns “What changed our next move?”: the cited original
paper result beside the proposed simulation, with its recorded recipe, measurements,
local controls, uncertainty, raw data and next action. The separate comparison page
has been removed. New runs save `comparisons/NNN/highlights.json` and
`comparison/highlights.json` alongside existing comparison artifacts; older sealed
runs render the comparison without rewriting their archives.

**Final synthesis** expands that same scientific comparison into detailed results,
validation, retained branch outcomes, bottleneck measurements and the next experiment.
It no longer includes Paper exploration. **Generated artifacts** retains the full
input, response, simulation and workflow audit. Inspection makes no new model or
simulation calls.

See [source intake and execution visibility](docs/source-intake.md) for limits,
commands and verification. The older numerical viewer remains directly runnable
at `src/hacknation_databricks/research_ui.py` for developer inspection.
