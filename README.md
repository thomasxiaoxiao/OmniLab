# OmniLab

[GitHub repository](https://github.com/thomasxiaoxiao/OmniLab).
The installed package is `omnilab`; launch its built UI with `python -m omnilab`.
The historical `hacknation_databricks` Python import namespace and local checkout
directory remain compatible with saved research archives and existing absolute paths.
Omnigent is the orchestration platform used by OmniLab.

Reproducible research and validation workspace with a React + TypeScript UI,
a FastAPI research service, seed papers and saved evidence. Run `npm ci`,
`uv sync --locked`, then `npm run dev` to open http://127.0.0.1:8000.
See [React UI setup and architecture](docs/react-ui.md). The existing
`/_stcore/health` deployment probe remains compatible; `/health` reports the revision.
The current research scope follows `docs/overall-design.md` and `AGENTS.md`.
`hackthon-instruction.pdf` is the corrected Agentic Scientific Discovery challenge
brief. Omnigent must orchestrate the live discovery workflow; the earlier housing
challenge requirements are superseded.

New UI runs and unconfigured Omnigent CLI runs use the **repository workflow**.
The built-in **Seed paper** menu contains only Percolation and AstroSat. Uploads
and arXiv imports are selected separately under **Uploaded paper** and never expand
that menu. In the UI, a validated paper is sufficient to enable **Start bounded run**;
a public GitHub repository is optional. A unique paper link is prefilled. Omnigent
specialists read the source, critique up to three directions,
compare two tests, and generate Python/C from the paper or supplied pinned repository.
Without a repository, the run explicitly records a new paper-based implementation;
it never claims to have executed author code. A supplied repository that fails to
load stops the run, without switching modes.
The supervisor executes it in Omnigent's OS sandbox, validates a baseline sanity
check and deterministic replay, and passes measured results to an evaluator that
can change the next experiment's parameters. No preset scientific kernel is selected
for this path. Historical configurations are readable for audit but cannot launch preset experiments.

**Discovery overview** combines the former overview and final synthesis. It opens
with the simulation, then gives the result, what changed, and the next experiment.
Plans, citations, uncertainty and execution details are expandable below.
Only the newest run for each paper appears by default; **Show previous runs** opens
the history. A finished repository run highlights its final evaluated experiment
once. Intermediate rounds remain in the audit history. Failed or incomplete runs
do not promote partial measurements to final results.

Supported code: offline Python 3.12 using the standard library, NumPy, SciPy, PyEphem 4.2.1 and
repository functions; optional C17 sources compiled as a shared library and called
from Python. Network access and package installation are unavailable inside the
experiment. Source/code directories are read-only; only disposable scratch is
writable. macOS uses Seatbelt and Linux uses bubblewrap, through pinned Omnigent
0.16.0. Missing sandbox support fails closed. macOS has no enforced resident-memory
or per-job process-count cap. See [execution and reproduction details](docs/repository-execution.md)
and the [live validation record](docs/repository-execution-validation.json).

```bash
.venv/bin/research run --paper /path/to/paper.pdf \
  --repository https://github.com/OWNER/REPO --repository-ref COMMIT \
  --output output/research/my-repository-run
.venv/bin/research verify output/research/my-repository-run
.venv/bin/research replay-code output/research/my-repository-run \
  --output output/replays/my-repository-run
```

The configured seed paper remains arXiv:2607.24975v1. Its extracted text has no
GitHub URL. Both the UI and the unconfigured CLI permit a paper-based implementation.
An explicit configuration can require a repository by disabling
`allow_paper_implementation`.
New papers are never silently mapped onto percolation or AstroSat demonstrations.

## Agent-owned simulations and scenes

Seeds supply only the pinned source papers. The reader explores up to three
source-grounded directions; the critic records accepted, rejected and unselected
routes. The planner compares at least two tests and two visualization options,
then explains its choice, state variables, units, what to watch and limitations.
The prompts favor intuitive physical or mechanistic views when the evidence
supports them. They never require invented motion or an attractive outcome.

The experimenter writes both simulation and scene-generation code. Each sandbox
trial can return a `scene` containing actual computed coordinates, geometry and
frames alongside its numerical results. A trusted generic player draws those
recorded states from the first preregistered paired seed. It contains no domain
simulation or paper-specific reconstruction. Raw output, generated code and
all other trials remain auditable. The evaluator sees both measurements and
visualization availability and chooses a parameter follow-up or explains a stop.

Flat and negative results are valid. Missing or invalid scenes remain explicitly
unavailable while valid numerical results proceed to evaluation. No fallback
animation is manufactured. Scene validation and exact replay establish provenance
and consistency, not correctness of the scientific model.

See the [measured live validation](docs/agent-owned-scenes-validation.json) and
[two-minute demo](docs/agent-owned-scenes-demo.md).

Old preset kernels, recipes and domain adapters have moved to `tests/legacy/` and
are excluded from the wheel. Old workflow configurations are rejected by the live
gateway. Historical archives remain inspectable without rerunning their built-in
visual reconstruction. See [historical descriptions](docs/historical-workflows.md).

## Live Omnigent setup

```bash
uv sync --locked
.venv/bin/research configure-agent --auth subscription
# In separate terminals:
bash scripts/research-runtime.sh server
bash scripts/research-runtime.sh host
# Once connected:
bash scripts/research-runtime.sh status
.venv/bin/research run --paper data/papers/2607.24975v1.pdf \
  --config examples/percolation/discovery.json \
  --output output/research/my-agent-run
.venv/bin/research verify output/research/my-agent-run
.venv/bin/research replay-code output/research/my-agent-run \
  --output output/replays/my-agent-run
npm run dev
```

This uses existing `codex login` authentication. Configuration uses the configured
Codex model unless `--model` or `RESEARCH_MODEL` is supplied. The runtime helper
prefers the bundled CLI on macOS; `OMNIGENT_CODEX_PATH` overrides it. Services bind
to loopback and `status` saves connection identifiers in ignored runtime state.
The CLI and UI use Omnigent, with no alternate decision backend or silent fallback.

**Agents & execution loops** shows separate sessions, real handoffs, route choices,
and continuation or stop reasons. It refreshes while work is running, preserving
inspection and form drafts. **Discovery overview** shows the final evaluated
experiment, a guide to what to watch, full interpretation, limitations and next
experiment. Intermediate rounds and unsuccessful routes remain available.

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
and restarts the app. PM2 must report the expected revision online and the app's
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

- `src/hacknation_databricks/`: Python research package, view projections and FastAPI service
- `tests/`: UI and deployment safety checks
- `scripts/`: process and deployment operations
- `.github/`: CI, issue template, and PR template
- `hackthon-instruction.pdf`: supplied challenge brief

The housing-law starter dataset is not part of this research implementation.
Research source intake and all simulations can run independently of cloud setup.

## Source intake and agent visibility

**Source intake** offers exactly two pinned seed examples (Percolation and AstroSat).
Uploaded and versioned arXiv papers live in a separate selector. The UI accepts an
optional public GitHub repository and revision; a validated upload can start without one. New runs use separate Omnigent reader,
critic/literature, planner, experimenter and evaluator sessions. Starting a run
opens **Agents & execution loops** and follows that exact run.

**Discovery overview** explains what to watch before the recorded simulation,
followed by the measured result, what changed, and the next action. The former **Final synthesis** entry has been removed.
**Generated artifacts** retains the paper, pinned source archive, generated code,
parameters, seeds, measurements, prompts and handoffs. Inspecting a saved run makes
no model or experiment calls. Older sealed runs retain their original provenance
and scientific limitations; the app does not rerun preset visual reconstruction.
