# Fresh AstroSat experiment

The fresh live Omnigent run completed two experiments and passed artifact validation.
Both experiments replayed exactly in the OS sandbox without new model calls.
The final visualization belongs to experiment 2 only; experiment 1 remains in
the audit history. The [machine-readable record](astrosat-orbital-validation.json)
contains the measurements, handoffs, runtime versions and verification results.

Run: `output/research/omnigent-astrosat-orbital-20261004T0335Z`.
Six specialist sessions, 36 requested simulation jobs, 204.024 seconds.
Terminal status: `research_stopped`, an explicit evaluator stop after two rounds.
The CLI returns 2 because this does not claim completion of a novelty goal.

## What was tested

The reader derived a question from the submitted AstroSat paper,
[arXiv:2111.11268v1](https://arxiv.org/abs/2111.11268v1): does replacing its constant
phase approximation with the repository's diffuse-sphere option change the shape
of a predicted light curve, beyond a constant brightness offset?

The generated program calls the unchanged `AstroSat.process_satellite` method from
the paper's [repository](https://github.com/james-m-osborn/astrosat), pinned to
`e65cd9a22d57c146f390b758822f3e37d16be9ad`. It checks the source hash and extracts
the original method with AST, excluding unrelated catalogue and plotting paths.
Real PyEphem 4.2.1 observers, satellites and Sun objects compute each sample.
No satellite positions, solar geometry or measured trajectories were hardcoded.

The historical IRIDIUM 80 orbital inputs come from the
[official PyEphem reference](https://rhodesmill.org/pyephem/quick.html).
The paper's original Starlink dataset was unavailable. This is therefore a scoped
model sensitivity check, not reproduction of the paper's main result or validation
against observed brightness. Input strings, retrieval provenance and the pre-run
geometry probe are in `examples/astrosat/reference-orbit/`.

## Recorded results and changed decision

Each job evaluates 61 samples across a 90-second window around the reference pass
maximum over Boston. The nominal peak is 2009-05-01 00:26:32.950313 UTC.
The low elevation, optical cross-section and assumed timing perturbations limit
physical interpretation. Invalid, eclipsed or below-horizon samples fail the job;
they are not silently discarded.

| Experiment | Question | Measured result | Next decision |
| --- | --- | --- | --- |
| 1 | Does the model difference vary under eight paired synthetic timing shifts? | Mean bounded span 0.16747; exploratory 95% interval 0.16374–0.17121, above the preregistered 0.05 threshold. | Remove the timing perturbation and test the nominal window. |
| 2 — final | Does variation remain without the timing perturbation? | Model difference ranges from 1.95249 to 2.15310 mag: a **0.20061 mag span**. Bounded span 0.16709. | Stop and propose an independent vector-based phase-angle calculation. |

The bounded metric is `span / (1 mag + span)`. Both identical-model controls and
exact replay passed. The final treatment repeats one deterministic trajectory
eight times; its collapsed numerical interval does not estimate observational,
orbital or model uncertainty. The UI states this explicitly and leads with the
magnitude span. The independent phase-angle calculation remains unexecuted.

Result-to-decision times were 25.681 and 16.836 seconds. No comparable manual
baseline exists, so an acceleration multiplier is unverified. Scientific novelty,
observational accuracy and generalization to other passes remain unverified.

## Reset and verification

- Six earlier `omnigent-repository-astrosat-*` runs were withdrawn unchanged into
  `output/research-archive/20261004T0312Z-astrosat-withdrawn/`. All six still verify.
- Three stopped restart attempts remain under
  `output/research-archive/20261004T0338Z-astrosat-restart-attempts/`. They exposed
  a disconnected service, unclear citation instructions and a prose-length limit;
  none produced accepted experimental measurements.
- Source intake now preserves fixed-width text inputs. Plots can declare units
  separately from the summary metric. Two constant trajectories cannot be promoted
  as a process simulation. Scientific thresholds were not relaxed.
- Regression suite before the concurrent React migration: 247 passed, 3 skipped.
  Focused repository/intake suite after adapting to its view interface: 46 passed,
  3 skipped. Real macOS Python, C and access-denial probes separately passed all 3.
- The new view protocol renders exactly one final visualization and one result
  heading, with history collapsed. Browser verification of this result passed in the React preview at
  `http://127.0.0.1:8505/overview`: current AstroSat run selected, playback reached
  all 61 samples, final visualization above the summary, earlier rounds collapsed.
  The screenshot is `docs/images/astrosat-final-orbital.jpg`. General frontend
  migration verification remains with the separate React task.

```bash
.venv/bin/research verify output/research/omnigent-astrosat-orbital-20261004T0335Z
.venv/bin/research replay-code output/research/omnigent-astrosat-orbital-20261004T0335Z \
  --round 2 --output output/replays/choose-a-new-directory
```

Existing exact replay archives are
`output/replays/omnigent-astrosat-orbital-screen-20261004T0342Z` and
`output/replays/omnigent-astrosat-orbital-final-20261004T0340Z`.
The [execution guide](repository-execution.md) provides fresh-run commands and
the two-minute walkthrough. No publication or deployment was performed for this task.
