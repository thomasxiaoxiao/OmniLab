# Two-minute demo: Percolation and AstroSat

This records the earlier two-paper validation. The completed runs in the exploration
list were pruned to `20261004T085900Z-demo-percolation`, as requested. New live runs
still appear normally. The older Percolation
run and AstroSat run were moved unchanged to
`output/archived-research/20261004T092925Z-percolation-only/`;
see [retention record](exploration-retention.json). The AstroSat steps below describe
the historical demo; that run is now available for offline artifact inspection
at its archived location, not in the current exploration selector.

Open http://127.0.0.1:8000/overview. Expand the sidebar and click **Refresh artifacts**
to inspect the retained Percolation run.
Inspection makes no model calls. These results came from live Omnigent specialist
sessions, executed agent-written code and AnyJev continuation decisions.

1. **0:00–0:35 — Percolation and the two scenarios.** Select
   `20261004T085900Z-demo-percolation`. Point to **How the scenarios differ** and
   the actual parameter table: adjacent whole streets alternate direction in the
   baseline; the proposed method randomly assigns each whole street a direction.
   Lattice sizes and occupation draws are matched. The player starts paused at
   **p = 0**. Scrub to **p = 1** and show all 21 computed frames. This is occupation
   probability, not physical time. Read the result and its exploratory interval.
2. **0:35–1:10 — A different AstroSat question.** Select
   `20261004T084900Z-demo-astrosat`. This tests screening under cross-track position
   uncertainty, rather than the old reflectivity-to-magnitude conversion. Both
   arms use identical physical trajectories; only the screening boundary changes.
   Show the three completed comparisons and their result-driven decisions.
3. **1:10–1:40 — What the results changed.** AstroSat first used global 0.25 km
   padding, then altitude-specific 0.25 km, then altitude-specific 0.5 km. Each
   experiment has four fresh paired seeds. The final full-bound treatment has no
   missed crossings under the assumed error bound, but adds 213.75 false alerts
   per seed on average. Recovery at that bound is expected containment; the alert
   burden is the measured trade-off. The next experiment is one concise sentence.
4. **1:40–2:00 — Traceable work and limits.** Open **Agents & execution loops**
   and **Generated artifacts** to show specialist sessions, the plan, actual code,
   raw trials, failures and decisions. Every accepted comparison is independently
   replayed, including scenes, without model calls. These are small synthetic
   computational experiments; full paper reproduction, scientific novelty and
   operational validity are not established.

## Percolation's executed experiments

| Treatment | Paired seeds | Baseline mean | Proposed mean | Difference interval |
|---|---:|---:|---:|---|
| Fair random streets | 4 | 0.31730 | 0.31322 | [-0.02546, +0.01730] |
| Fair random streets, fresh precision batch | 8 | 0.30395 | 0.31504 | [+0.00090, +0.02129] |
| Random streets, positive-direction probability 0.75 | 8 | 0.31030 | 0.31405 | [-0.00600, +0.01350] |

The scalar averages largest-SCC fractions over both sizes and all 21 occupation
probabilities. The final interval lies inside the preregistered ±0.02 practical
threshold, supporting only exploratory equivalence for that aggregate. It does
not establish curve equivalence or a direct bias-versus-fair effect. The first
inconclusive screen caused the eight-pair precision test; the unresolved fair
contrast then led to the planned bias scenario. At p=0 the displayed 16×16 system
has singleton components and no occupied bonds; at p=1 all 512 bonds are present
and all 256 vertices share one SCC.

## AstroSat's executed experiments

| Screening treatment | Baseline misses | Proposed misses | Extra false alerts per seed |
|---|---:|---:|---:|
| Global 0.25 km padding | 11.62% | 1.18% | 192.00 |
| Altitude-specific 0.25 km | 10.75% | 2.32% | 80.25 |
| Altitude-specific 0.5 km | 10.28% | 0.00% | 213.75 |

Miss rates divide missed crossings by all actual crossings. Extra alerts count
false alerts added to that round's matched baseline. Cross-round comparisons are
descriptive: seeds change, so they do not isolate a policy effect. The next proposed
study holds cases fixed while comparing global and altitude-specific padding.
No shutter, photometry, SGP4 or observed orbital-error distribution was validated.

## Root causes and corrections

- The earlier Percolation plan sampled only p = 0.60–0.80. Five-frame autoplay
  made that deliberate range look like a rendering cutoff. New sweep contracts
  require the requested endpoints and the same complete grid in every scientific
  comparison and follow-up. Output is checked against that grid. Playback starts
  paused and displays its real range; no artificial endpoint frames are added.
- AstroSat selection had no cross-run history. New reader, critic and planner
  calls receive bounded, source-hash matched history, including archived local
  attempts. Exact repeats are rejected in new-direction mode; the critic assesses
  substantive overlap. This supports local exploration, not a novelty claim.
- The first full-sweep Percolation attempt failed because its sanity parameter
  list omitted p = 0.55 while its implementation required all 21 samples. Two
  bounded code repairs incorrectly pursued numeric-grid validation. The failure
  lacked job attribution. Worker diagnostics now identify the failed arm and
  seed and retain completed partial trials. The corrected run explicitly uses
  the full grid for its sanity parameters too. The failed attempt is preserved
  in `output/demo-validation/failed-runs/`, with its original manifest hash.
- The viewer incorrectly quarantined valid Percolation trials because formatted
  JSON files exceeded its 20 MiB preview limit. Integrity checks now stream every
  artifact independently of preview size. Raw-trial downloads preserve exact sealed
  bytes under a separate 128 MiB limit; structured previews remain bounded.
- Comparisons now name both methods, state the changed mechanism and show actual
  final parameter differences. Plans are instructed to keep the visible baseline
  as a direct scientific control. Next-experiment responses remain bounded to
  one sentence, 20 words and 140 characters.

## Verification

[Recorded validation](two-paper-validation.json): 325 tests passed with real OS
sandbox probes; six comparisons independently replayed exactly. Both UI journals
verify, including the 50,071,039-byte raw-trials download. Independent raw-evidence
checks certified 1,680 Percolation graph partitions and 13,932 AstroSat case pairs.
The successful runs used 17 Omnigent specialist calls, six AnyJev evaluations and
84 simulation jobs. The preserved failed attempt used eight calls and 12 reserved
pilot jobs. Successful run times were 377.808 seconds (Percolation) and 363.877
seconds (AstroSat); the earlier failed attempt consumed 536.575 seconds.

## Recheck without model calls

```bash
.venv/bin/research verify output/research/20261004T085900Z-demo-percolation
.venv/bin/research verify output/archived-research/20261004T092925Z-percolation-only/20261004T084900Z-demo-astrosat
.venv/bin/research replay-code output/research/20261004T085900Z-demo-percolation \
  --round 1 --output output/replays/new-percolation-check
.venv/bin/research replay-code output/archived-research/20261004T092925Z-percolation-only/20261004T084900Z-demo-astrosat \
  --round 1 --output output/replays/new-astrosat-check
```

Use fresh replay output directories and repeat `--round` for each recorded round.
The full live inputs, configurations, prompts and source snapshots remain in each
run. Fresh runs require the existing Omnigent server/host and authentication; use
`output/demo-validation/percolation-corrected-config.json` or
`output/demo-validation/astrosat-config.json` with `research run`, the corresponding
saved seed/supporting PDFs, and a new output path. Per-run limits are 900 seconds,
18 specialist calls, three evaluations, three comparisons and 200 simulation jobs;
code pilots and complete batches have separate 15/60-second limits.

Astra extra-high applies only to the Codex work chat. Research-worker model settings
were not changed. No comparable manual discovery baseline exists, so an acceleration
multiplier is unverified. Independent domain and observed-data validation are needed
before real-world use. No public deployment or submission was performed.
