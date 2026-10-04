# OmniLab

OmniLab is a research workspace that helps turn a scientific paper into a
computational experiment a scientist can inspect. Agents read the paper, propose
and critique directions, write simulation code, run it, and use the measurements
to decide what to test next. [Omnigent, from Databricks](https://www.databricks.com/blog/introducing-omnigent-meta-harness-combine-control-and-share-your-agents),
coordinates the specialist sessions and provides the sandbox for their experiments.

## Why we built it

**Human scientists have limited time to validate results.** Checking a claim means
finding its source, understanding the assumptions, inspecting the implementation
and rerunning the experiment. AI can produce ideas faster than a person can do
that work. OmniLab aims to reduce the time spent assembling the evidence for review
by keeping the paper, code, parameters, measurements and decisions in one place.

**AI scientists need grounding and control.** An agent should be able to show which
passage supports its hypothesis, what would falsify it, and what the experiment
actually measured. It also needs limits on what it can execute and how long it can
keep trying. OmniLab combines Omnigent's sessions and OS sandbox with validated
handoffs, numerical checks and finite research budgets. The scientist sets the
question and judges whether the resulting evidence is useful.

## See it: connectivity on one-way streets

Starting with [*Strongly-connected percolation on directed lattices*](https://arxiv.org/abs/2607.24975v1)
and a user-requested comparison, the agents investigated how street directions
change connectivity as more bonds become available. They compared alternating
street directions with randomly directed whole streets, writing both the simulation
and its visualization from the source evidence.

[![Recorded percolation simulation: alternating streets and random whole streets across 21 bond occupation probabilities. Click to open the interactive player.](docs/assets/percolation-exploration.gif)](https://glum-radiant-engines.replit.app/overview)

**[Open the interactive simulation →](https://glum-radiant-engines.replit.app/overview)**
Play, pause or scrub the saved run and inspect the experiment behind it. The public
demo shows recorded results; starting new research runs is disabled there.
[Static image](docs/assets/percolation-exploration.png) ·
[Figure provenance](docs/assets/percolation-exploration.json)

The highlighted sites form the largest group in which every site can reach every
other by following directed bonds. The animation shows the final experiment's
first preregistered seed on a 16×16 lattice, sweeping bond occupation probability
from 0 to 1 in 21 computed steps. These are recorded simulation states, not physical
motion. Measurements also include 32×32 lattices and the other seeds.

The useful part was how the results changed the next experiment:

| Test | What happened next |
| --- | --- |
| Fair random streets, four paired seeds | The comparison was inconclusive, so the run added eight fresh pairs with the same parameters. |
| Fair random streets, eight fresh pairs | The meaningful-effect question remained unresolved, so it tested a directional bias of 0.75. |
| Biased random streets, eight pairs | The average difference fell within the declared practical-equivalence range. The run stopped and proposed comparing biased and fair streets directly. |

In the final test, the difference in mean largest-component fraction was
**+0.00375**, with an exploratory 95% interval of **[−0.00600, +0.01350]**, inside
the predeclared ±0.02 range. That applies to the average across sizes and
probabilities; it does not establish that the full curves are equivalent. The
proposed direct biased-versus-fair test has not been run.

The saved run completed in **377.8 seconds**: nine Omnigent specialist calls,
three AnyJev decisions and 50 simulation jobs, including four feasibility jobs.
These are small computational checks, with exploratory intervals and no established
scientific novelty or full-paper reproduction. Independent scientific validation
is still needed. We have not measured a comparable manual baseline, so we cannot
claim an acceleration multiplier. [Full validation record](docs/two-paper-validation.json).

## How the research loop works

**Paper → Evidence → Hypothesis → Experiment → Result → Next decision**

Omnigent runs separate specialist sessions with explicit inputs and outputs:

1. **Read and question.** A reader extracts up to three directions with supporting
   passages. A literature researcher checks related work; a critic challenges the
   assumptions and rejects weak proposals.
2. **Plan and implement.** A planner compares at least two tests and defines the
   controls, metric and budget. An experimenter writes the code and scene data.
   A paper alone is enough to start; a pinned public repository is optional.
3. **Execute and check.** The supervisor runs the generated code in Omnigent's OS
   sandbox, checks a baseline sanity case and deterministic replay, and saves raw
   results. Experiments have no network access or package installation.
4. **Learn and decide.** An Omnigent researcher interprets the measurements and
   proposes a follow-up. A separate AnyJev evaluator selects from bounded actions:
   more samples, an approved parameter change, or stop. Its option weights are
   uncalibrated; they are not scientific confidence scores.

Seeds supply papers, not preset experiments. Failed code, rejected directions and
inconclusive results stay in the record. The UI connects the final result to its
sources, agent sessions, generated code, parameters and seeds. Replay and provenance
help a scientist check the work; they do not establish that the scientific model
is correct. See [execution contracts and limits](docs/repository-execution.md).

## Run locally

Requires Python 3.12, [uv](https://docs.astral.sh/uv/), and Node.js 22 or newer.

```bash
npm ci
uv sync --locked
npm run dev
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000). Choose Percolation or AstroSat
under **Example papers**, or upload/import a paper under **Your papers**. Configure
the live runtime below before starting a new run. Viewing saved runs makes no model
calls. Full research archives are local and are not included in a fresh clone;
the animation and validation records above are included.

The UI uses React and TypeScript with a FastAPI research service. To serve the
built UI, run `npm run build`, then `uv run --locked python -m omnilab`.
The historical `hacknation_databricks` import namespace remains compatible with
existing research archives. [UI setup and architecture](docs/react-ui.md).

### Live Omnigent setup

<details>
<summary>Configure agents and start the local runtime</summary>

The current live workflow uses Omnigent 0.16.0 and existing Codex login
credentials. Its separate AnyJev evaluator requires Apple Silicon and a pinned
local Qwen3/MLX model. Missing runtime support stops the run with a recorded reason.

```bash
# One-time setup after installing the project dependencies:
.venv/bin/research prepare-model
.venv/bin/research configure-agent --auth subscription

# Run each service in a separate terminal:
bash scripts/research-runtime.sh server
bash scripts/research-runtime.sh host

# Check the connection, then start a bounded run from the UI:
bash scripts/research-runtime.sh status
```

Omnigent's experiment sandbox uses Seatbelt on macOS and bubblewrap on Linux;
missing sandbox support fails closed. macOS does not enforce a resident-memory
or per-job process-count cap. See the [execution limits](docs/repository-execution.md#executable-code-and-limits)
before running experiments.

Verify or replay your own saved run without new model calls:

```bash
.venv/bin/research verify output/research/YOUR_RUN_ID
.venv/bin/research replay-code output/research/YOUR_RUN_ID \
  --output output/replays/YOUR_REPLAY_ID
```

</details>

## Development and documentation

Run `npm run check` for frontend checks, the production build, Python linting,
formatting and tests. Keep `uv.lock` and `package-lock.json` committed; use feature
branches and pull requests for changes.

- [Research design](docs/overall-design.md)
- [Execution, reproducibility and sandbox limits](docs/repository-execution.md)
- [Two-minute saved-run walkthrough](docs/two-paper-demo.md)
- [Deployment operations](docs/deployment.md)
- [Project status and validation history](STATUS.md)

Built for Hack-Nation × Databricks **Challenge 03: Agentic Scientific Discovery**.
The [challenge brief](hackthon-instruction.pdf) and [agent instructions](AGENTS.md)
define the project scope.
