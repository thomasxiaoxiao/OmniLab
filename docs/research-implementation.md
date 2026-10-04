# Research workflow implementation

## Paper-first automatic context

The UI reads each paper into a domain-independent `PaperBrief` before capability
selection. No preset catalog or metric is present in this reader's payload/schema.
Only a later mapper sees available implementations, and it cannot change a proposed
hypothesis to fit a tool. Unmatched research is retained without simulation.
The source-bound `implementation.json` identifies the kernel/dependencies supplied
to the validator; the full framework snapshot lives separately in
`framework/source.zip`. Historical archives remain immutable. This isolates
existing tools; it does not implement arbitrary generated scientific programs.

## Current adaptive execution

The UI now fixes Codex + Omnigent for research and AnyJev + Omnigent for decisions.
`HybridOmnigentRoles` keeps the existing Omnigent Sessions API for scientific
assessments, then hands each investment checkpoint to the pinned local AnyJev
scorer. Its finite option catalog permits investing in an existing branch,
requesting independent validation of an eligible branch, or stopping for review.
AnyJev runs as a local supervisor tool, not a native Omnigent harness. The request,
weights, ambiguity check, original assessment and applied action are retained;
the auditor checks the selected action against the saved options. No fallback
occurs on runtime failure or ambiguous scores. The UI requires the Codex harness;
old CLI configurations retain their existing decision route.

`Start bounded run` navigates immediately to the live execution page. A preallocated
run ID prevents another run from stealing progress. The page refreshes every five
seconds and displays an explicit terminal outcome plus current artifact downloads.
Discovery overview and Final synthesis share the cited-paper/proposed-simulation
comparison and checkpoint-scoped file inspector. Highlight JSON files are sealed
for future runs; existing sealed runs are projected without mutation.


The default Omnigent launcher and `examples/percolation/discovery.json` now use
workflow v4. Parallel source/citation researchers feed a consolidator; multiple
research branches run simulations and the decision agent evaluates every partial
batch before allocating more work. Baseline controls and treatment samples are
refreshed, earlier batches are retained, and completion requires a declared
numerical goal plus independent validation. Configurable limits extend to 32
batches per direction and 16 workers, with finite request/time/compute budgets.
The second implemented example uses Astrosat's positional-error analysis.

See [adaptive-discovery.md](adaptive-discovery.md) for contracts, scientific
assumptions, policies, artifacts and commands. The sections below describe the
retained sequential workflow used by earlier configurations and AnyJev.

The current implementation follows `overall-design.md`. That design requests a
multiagent research system for [arXiv:2607.24975v1](https://arxiv.org/abs/2607.24975v1),
**Strongly-connected percolation on directed lattices**. The corrected
`hackthon-instruction.pdf` requires Omnigent orchestration for scientific discovery;
`AGENTS.md` now reflects that brief.

## Execution contract

The Python supervisor enforces this sequence:

1. Read the supplied seed; extract at most three distinct directions with exact,
   page-local supporting quotations.
2. Critique every direction exactly once and select an accepted direction explicitly.
   Rejected directions cannot run.
3. Run and validate the numerical baseline before proceeding.
4. Review supplied literature, choose the reviewed experiment, run it, replay
   seeds and check invariants, then independently review the measurements.
5. Compare screening and precision tests by expected learning, feasibility and
   simulation cost. The planner selects the sampling budget before execution.
6. Interpret the result in a separate next-decision session. Record repeat,
   literature review or stop and the proposed next experiment. Repeat only while
   scientific gates and finite budgets permit it. A missing literature review
   cannot be repaired by more simulations.

New adaptive handoffs include explicit measurement definitions for every specialist.
For Astrosat, missed-transit rates use true crossings as their denominator, while
false-alert rates use nontransits. False alerts divided by all alerts is a different
quantity. The contract also states that guard branches have independent candidate
samples and that the numerical goal tests each guard against its own control.
Checkpoint scoring distinguishes sampling uncertainty that additional batches can
resolve from source or implementation defects that require stopping for review.
Stop, review and ambiguity abstention remain available; scientific thresholds stay
fixed. Historical handoffs without these contracts retain their original semantics.

The optional `anyjev` backend uses local Qwen3 4B logits via MLX. AnyJev scores
closed options across cyclic order rotations, with no generated text or executable
instructions. Evidence selection, proposal critique, direction ranking, literature
assessment, execution authorization and validation are model decisions. The
supervisor's gates and experiment implementations remain deterministic. All
options, scores, state, input hashes and usage are saved. Ambiguous scores or an
explicit stop/defer choice halt the workflow. See [decision runtime](decision-runtime.md).

The default input is the complete seed PDF; exact candidate passages are retrieved
from every page and the model reviews that bounded subset. Retrieval scope is
explicit. Original PDF bytes and hashes are saved with the run. Scripted decisions
exist only as test doubles, with no production CLI or UI entry point.

The default `omnigent` backend creates separate reader, critic, literature-reviewer,
planner, validator, novelty-evaluator and next-decision sessions through the **Omnigent 0.16.0 Sessions API**.
It resolves a registered agent, launches a session runner on the configured online
host (or binds an existing runner), consumes typed streaming events, interrupts
incomplete requests and requests cleanup of host-launched runners. Sessions have role/run labels, and IDs and reported token usage are
saved. A live failure never switches to the scripted backend. Roles receive only
public source text, structured context and an output schema. The local launcher
disables web search and requests native-tool suppression; role instructions forbid
code execution. The roles completed without tool calls in the verified run.
Python controls execution order and invokes scientific implementations from a
fixed allowlist; agents cannot execute generated Python or shell commands.

## Reproducible science

`simulation.py` implements periodic, even-sized square lattices:

- Baselines: Manhattan, L-lattice, and random diode bond percolation.
- Extensions: independently randomized Manhattan row/column directions,
  Manhattan site occupation, and random diodes with a 25% bidirectional fraction.
- SCCs: SciPy's strong-connectivity routine, tested against an independent
  reachability oracle on small graphs.
- Wrapping: integer displacement consistency inside SCCs. Merely touching a
  boundary or connecting across a seam does not count as winding around a torus.

The baseline evaluates one-axis wrapping at the paper's published critical bond
probabilities (Table I), comparing results to approximately 0.75001 (Table II).
A 95% Wilson interval plus a predeclared finite-size allowance is a **small-lattice
consistency check**, not reproduction of the paper's high-precision estimates.
Square-ice sampling, critical exponent fits, hull dimensions and million-sample
finite-size extrapolations are not implemented.

Each follow-up changes one model mechanism at a fixed occupation probability.
Its primary endpoint is the difference in horizontal wrapping rates. Conservative
Wilson intervals use a Bonferroni correction over all configured sizes and rounds.
The lower bound on the absolute difference must exceed `minimum_effect` at every
configured size. This protocol does not estimate a new critical probability or
establish a universality class. A failed comparison remains inconclusive.

The novelty gate requires baseline consistency, numerical validation, a detectable
effect, a supporting live validator, a literature candidate-gap assessment, and
citations to at least two distinct supplied sources. Duplicate source bytes are
rejected. Omnigent adds a separate reference evaluator, whose candidate-contribution
verdict is a seventh gate criterion. Every supplied source must have a traceable
quotation in its comparison. Passing advances an **automated candidate**; no human
approval is required. `scientific_novelty` remains `unverified` for global priority.

Omnigent CLI and UI runs automatically retrieve up to three explicit arXiv citations
from the seed. They resolve immutable versions, preserve full PDFs and include only
whole sources within the 180,000-character budget. Every unavailable, duplicate or
budget-excluded source is recorded in `reference_retrieval.json`. Non-arXiv and
uncited sources are not searched. Add more with `--literature`; use
`--no-auto-literature` to disable automatic downloads. A completed scoped review
returns `review_complete`; more simulations cannot repair missing literature.

## Budgets and artifacts

`RunConfig` bounds lattice sizes, trials, model calls, workers (maximum four),
rounds and elapsed time. Workers check a shared simulation budget before each
trial. Generated Omnigent bundles request 2,048 output tokens, one iteration,
a 300-second executor timeout and zero retries. Token limits are harness-dependent;
Codex enforcement is the parent call deadline and 32,000-character response cap.
The verified configuration budgets 12 role calls and 1,800 seconds. Cancellation failure is recorded explicitly.

Each new output directory contains:

| Artifact | Purpose |
| --- | --- |
| `inputs/`, `sources.json` | Unmodified inputs, normalized pages, hashes and retrieval metadata |
| `config.json`, `environment.json`, `code/`, `uv.lock` | Parameters, dependency versions and source snapshot |
| `proposals.json`, `critiques.json` | Grounded directions and feasibility decisions |
| `baseline/` | Raw trial CSV, summaries, checks and seed replays |
| `rounds/NN/` | Literature, plan, recipe, trials, reviews, effect intervals and gate |
| `roles/` | Validated role outputs or optional Omnigent prompts/responses |
| `decisions/`, `decision-model.json` | Closed questions, model scores, inference usage and pinned weights |
| `rounds/NN/test_options.json`, `next_decision.json`, `transition.json` | Compared tests, specialist recommendation and enforced supervisor action (v3) |
| `events.jsonl` | Real stage start, completion, failure and session events |
| `report.json`, `manifest.json` | Honest acceptance status and artifact checksums |
| `comparison/simulation.svg`, `comparison/summary.txt`, `comparison/comparison.json` | Required final original/proposed visualization, numerical sentence and provenance |
| `comparisons/NNN/` | The same comparison outputs for every completed result checkpoint |

Both sequential and adaptive workflows produce these comparison artifacts before
sealing. They derive numbers from the saved effect measurements and read the actual
saved experiment recipe, never a newer catalog definition. The accepted branch's
snapshot is bounded by the finalization decision; late results cannot replace it.
Intervals, denominators and Astrosat false-alert tradeoffs stay explicit. Failed
or rejected runs without completed measurements retain an unavailable result,
without fabricated rates. Older sealed runs expose read-only derived downloads.

The agent trace displays instructions from each archived `roles/*-request.json`,
not today's prompt catalog. Source IDs and branch/batch assignments distinguish
sessions sharing a role. Exact prompt downloads include the recorded input data,
constraints and output schema. Response fields and actual dependency handoffs show
how the supervisor uses those outputs; failed attempts do not inherit the later
successful retry's simulation handoff.

Trial seeds derive from scientific parameters and a master seed, independent of
worker scheduling. Cached jobs are keyed by parameters and the implementation
hash; checksums and seed replays guard reuse. CSV column order is stable across
fresh and cached runs. Existing run directories are never overwritten. Failed
runs retain partial reports and manifests; successfully cached simulation jobs
can be reused in a fresh run. Live model responses are audit records, not silently
reused responses. Whole-session live resume is not implemented.

## Databricks guidance applied

The implementation follows the principles in Databricks'
[agent design patterns](https://docs.databricks.com/aws/en/agents/agent-system-design-patterns)
and [observability concepts](https://docs.databricks.com/aws/en/mlflow3/genai/concepts/core-concepts):
explicit supervisor control, narrow role contexts/tools, bounded failure handling,
recorded steps, versioned inputs and separate quality checks. The optional
`log-mlflow` command exports verified artifacts, configuration, acceptance checks
and effect metrics to a local or Databricks MLflow experiment. It does not fabricate
model traces or judge scores from scripted runs. Omnigent session IDs and usage
remain in the original audit files.

The integration was checked against the installed 0.16.0 Python SDK and native
spec parser. The upstream [repository](https://github.com/omnigent-ai/omnigent),
[agent specification](https://github.com/omnigent-ai/omnigent/blob/main/docs/AGENT_YAML_SPEC.md)
and [Databricks integration guide](https://github.com/omnigent-ai/omnigent/blob/main/docs/databricks.md)
were inspected on October 3, 2026; repository HEAD at inspection was
`f37a484a9238d21dac71b62dd79b87e016947c19`. Dependencies use the published release,
not that moving development branch.
