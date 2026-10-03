# Measured reference results

These are real, seeded numerical outputs from the scripted full-paper run on
October 3, 2026. They contain 1,536 baseline trials (three models, two sizes,
256 repetitions) and 512 randomized-Manhattan follow-up trials. Eight additional
seed replays passed. This compact copy omits the copyrighted full paper and the
machine-specific run journal; complete local artifacts are under
`output/research/final-validation/`.

Run from the repo root:

```bash
uv run --locked research fetch
uv run --locked research run --paper data/papers/2607.24975v1.pdf \
  --config examples/percolation/validation.json --output output/research/reproduced
cmp examples/percolation/reference-results/baseline/trials.csv output/research/reproduced/baseline/trials.csv
cmp examples/percolation/reference-results/rounds/01/trials.csv output/research/reproduced/rounds/01/trials.csv
```

The seed paper's Table I provides the baseline probabilities, and Table II
provides the wrapping reference. All six baseline checks passed the declared
small-lattice tolerance. The effect criterion passed at L=32 but not L=16.
The combined gate did not pass; additional literature review is also required.
These are not official hackathon scores or a scientific novelty claim.
