# Adaptive Omnigent research

The default Omnigent CLI launch and discovery profiles now use a parallel,
result-driven research portfolio. The original sequential workflow is retained
for older configuration files (`workflow: sequential`) and the auxiliary AnyJev
backend. Historical run directories remain immutable.

## Execution and decisions

1. Retrieve bounded explicit arXiv citations from the selected seed. Record
   versions, original PDFs, hashes, download failures and context exclusions.
2. Run one Omnigent researcher session per included seed/citation input in
   parallel. Each reads the full supplied source and proposes at most three
   catalog-supported directions, labels paper suggestions versus new hypotheses,
   and cites exact page-local evidence. One recorded correction attempt is allowed
   for invalid evidence; unresolved failures stop the run.
3. A consolidating critic reviews every candidate, rejects unsupported proposals
   and selects up to three distinct experimental directions. Related papers
   inform this decision even when they do not support another executable branch.
4. Validate the domain baseline. For every invested branch, a research planner
   compares screening and precision tests. Python dispatches its validated choice
   to an allowlisted simulation tool. The next batch includes fresh control and
   treatment samples; earlier samples remain in the cumulative analysis.
5. As each batch finishes, pass its real tool result, all available branch
   summaries, pending branches and remaining budgets to a separate Omnigent
   decision session. Completed results are processed in arrival order. The
   decision changes the investment order, pauses/resumes a branch, asks for more
   precision, requests final validation or stops. A prose suggestion outside the
   implemented catalog is a future recommendation, not executed code.
6. Continue until a declared numerical goal and independent validator agree, or
   stop honestly at a finite limit, rejection or runtime failure. Already
   authorized batches finish and receive decision reviews; no new work is
   launched after a terminal decision.

Researchers, consolidator, branch planners, decision maker and validator use
separate sessions through the pinned Omnigent 0.16.0 Sessions API. Call IDs and
stage contexts are thread-safe. Each host-launched session gets its own working
directory. Structured plans and tool-result handoffs are stored alongside actual
session IDs. Omnigent roles do not execute generated Python or shell commands;
the host supervisor executes the allowlisted computational tools.

## Budgets and completion

The frontend's checkpoint story reconstructs the prior plan and measurements from
each archived decision input, never the final portfolio state. A downstream planner
is attributed to a decision only through its recorded parent handoff; a simulation
launch also requires a `tool_dispatched` event. Late results and prose suggestions
cannot stand in for a new execution. The evidence tabs expose raw inputs/responses,
transition records, the selected test's budget check and deterministic replay.
Session IDs, registered agent IDs and archived common request constraints document
the shared Omnigent runtime. Request constraints are instructions; the scientific
and budget gates are enforced by Python. These historical archives do not capture
native Omnigent policy configuration or establish sandbox attestation.

Standard exploration permits eight batches per direction, six concurrent workers,
96 requests, 100,000 simulation units including replays, and one hour. Extended
exploration permits 16 batches, 12 workers, 192 requests and two hours. UI controls
allow up to 32 batches, 16 workers and finite call/compute/time limits. A seed is
chosen for each UI run unless pinned explicitly. Every branch, batch and arm has
its own reproducible derived seed stream.

The numerical goal requires at least two independent batches, a resolved effect
(or equivalence within the declared threshold) in every configured group,
interval width at most the configured limit, and independent validation. It is
not a scientific-novelty goal. Missing global-priority evidence cannot turn a
numerical result into a discovery claim, and does not prohibit useful additional
simulations. A bounded stop never changes `goal.achieved` to true.

Conservative Wilson endpoint intervals use a Bonferroni allowance across all
three possible invested branches, configured batch looks, groups and endpoints.
The implementation preserves unfavorable seeds and cumulative results instead of
selecting the best batch. Percolation arms are independent; Astrosat compares
control and guard policy on the same synthetic candidate within each batch.
The conservative interval calculation does not exploit paired covariance.
Wilson coverage is approximate: multiplicity adjustment does not create an exact
finite-sample familywise guarantee.

Simulation reservations include a complete seed replay of each batch. A global
request semaphore bounds simultaneous agent calls. Runtime failures may receive
one new recorded session attempt, within the same request/time limits; there is
no alternate backend fallback. Evidence repairs and request retries have separate
finite limits. The original project hard stop, October 4 at 00:07 PDT, remains
enforced for adaptive runs.

## Two scientific examples

**Percolation:** [Strongly-connected percolation on directed lattices,
arXiv:2607.24975v1](https://arxiv.org/abs/2607.24975v1). The existing Manhattan,
L-lattice and random-diode baseline checks are retained. Competing branches test
randomized Manhattan directions, site instead of bond occupation, and a 25%
bidirectional-diode fraction. These are fixed-probability, small-lattice wrapping
checks, not high-precision reproduction, critical-point estimates or universality
claims. Fresh control samples prevent later precision batches being limited by
an unchanged small baseline sample.

**Astrosat:** the supplied Silverchair link identifies
[Osborn et al., Astrosat, DOI 10.1093/mnras/stab3003](https://doi.org/10.1093/mnras/stab3003).
The run uses the immutable [arXiv:2111.11268v1 preprint](https://arxiv.org/abs/2111.11268v1),
which has seven pages and differs in pagination from the published article. The
signed expiring URL is not persisted. Section 2.1, page 2, provides orbital-error
examples and motivates probabilistic field expansion. Equation 1 checks the
conversion of 2/25 km in-track errors to timing offsets and a 500 m cross-track
error to an angular offset at 335 km altitude.

The follow-up is a Monte Carlo sensitivity study of 1-, 2- and 3-sigma spatial
guards, retaining the paper's ±5 second search window. It measures missed true
crossings and false alerts separately for fresh/stale error scenarios, with a
nominal-field control on the same candidates. Gaussian errors, interpreting the
quoted error magnitudes as standard deviations, uniform candidate locations,
a 0.5-degree circular field, a 30-second exposure and straight-line zenith
geometry are explicit modeling assumptions. This does not run SGP4, reproduce
historical TLE populations or forecast actual satellites. Real-world use requires
calibrated error distributions, orbit propagation, brightness modeling and
comparison against timestamped observational ground truth.

## Reproduce and inspect

```bash
bash scripts/research-runtime.sh status
.venv/bin/research fetch --arxiv-id 2607.24975v1
.venv/bin/research run --config examples/percolation/discovery.json \
  --output output/research/percolation-new-run
.venv/bin/research fetch --arxiv-id 2111.11268v1
.venv/bin/research run --paper data/papers/2111.11268v1.pdf \
  --config examples/astrosat/discovery.json \
  --output output/research/astrosat-new-run
.venv/bin/research verify output/research/astrosat-new-run
```

The saved UI needs no new model calls. The discovery view shows branch hypotheses,
source passages, cumulative intervals, pending work and investment decisions.
The execution graph draws the recorded handoff DAG, including parallel sessions
and retries. It does not invent serial arrows between independent workers.

Key artifacts are `research_briefs.json`, `candidates.json`, `consolidation.json`,
`goal.json`, `branches/<id>/batches/<n>/`, `checkpoints/<n>/input.json`,
`decision.json`, `transition.json`, `events.jsonl` and the sealed manifest. Every
batch retains its specification, raw trials, replay check and cumulative summary.
The viewer rechecks source quotations, raw-result summaries, goal gates,
dependencies and hashes. Failed and incomplete runs remain distinct from accepted
results.

The measured bottleneck is time from an available partial result to the next
investment decision. Request duration and, in newer runs, result-to-decision
latency including queueing are saved separately. A comparable human/manual
baseline has not been measured, so no acceleration multiplier is claimed.

## Verified live examples, October 3, 2026

Both final archives passed raw-result, handoff-contract and manifest verification.
The independent validator received the executed recipe, implementation, exact
counts, seed/replay checks and comparison summaries. Its support is an agent
review of supplied evidence, not independently executed scientific validation.

| Example | Requests / completed responses | Decisions | Simulation units, including replays | Elapsed | Median result-to-decision |
| --- | --- | --- | --- | --- | --- |
| Percolation | 22 / 21 | 8 | 33,542 | 269.6 s | 46.0 s |
| Astrosat | 25 / 23 | 9 | 36,864 | 301.6 s | 46.1 s |

Each used three source researchers and three experimental branches, peaking at
three concurrent requests under the six-worker limit. Runtime retries explain
the difference between request and completed-response counts. Stop requests
were recorded for every created runner; no cleanup request was unconfirmed.
Provider token/cost usage remained unavailable. Earlier unsuccessful runs are
preserved in the verification report, not counted as successful discoveries.

Percolation accepted the diode branch after two batches: independently adding
reverse edges with probability 0.25 at p=1 increased horizontal strongly connected
wrapping by 0.215 at L=8 and 0.248 at L=16. Accepted difference intervals were
[0.127, 0.292] and [0.160, 0.324]. The agent changed from precision sampling to
final review, then proposed varying probability or reverse-edge fraction as
future work. Those additional interventions have not been executed.

Astrosat accepted the three-sigma spatial guard after three batches. Fresh missed
crossings fell from 137/897 to 0/897 and stale misses from 112/880 to 2/880.
False alerts among nontransits increased from 15.1% to 55.7% and 14.7% to 58.2%.
This does not establish an acceptable operational tradeoff or a matched two-
versus three-sigma comparison: branches used different candidate samples.

See `docs/adaptive-validation.json` for all attempts and fingerprints,
`docs/adaptive-demo.md` for the two-minute walkthrough, and
`examples/{percolation,astrosat}/adaptive-results/` for compact snapshots.
