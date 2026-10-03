# Local validation, October 3, 2026

The base solution passes `npm run check`: **84 tests**, Ruff lint/format checks
and PM2 configuration syntax. The suite includes the existing deployment tests,
source/schema rejection, independent SCC checks, periodic winding fixtures,
seed replay, deterministic cached exports, role sequencing, rejection/budget
stops, mocked Omnigent session binding/cancellation, native spec validation and
Streamlit interaction checks. The concurrent decision-tracking tests are included.

A fresh production-style environment (`--no-dev --no-editable`) successfully ran
the packaged CLI using its bundled excerpt, without credentials or a model call.
The complete linked PDF was also fetched successfully with TLS verification.

The full-paper run saved **2,048 Monte Carlo trials and 8 seed replays**:

| Model | L=16 wrapping rate | L=32 wrapping rate |
| --- | ---: | ---: |
| Manhattan baseline | 0.7578125 | 0.74609375 |
| L-lattice baseline | 0.71484375 | 0.73046875 |
| Random diode baseline | 0.73046875 | 0.75390625 |
| Randomized Manhattan extension | 0.88671875 | 0.9453125 |

All six baseline batches pass the declared Wilson-interval plus finite-size
allowance check. The corrected effect criterion passes only at L=32; the combined
criterion remains unmet. The workflow stops honestly at `needs_literature_review`.
This is a reduced-scale consistency result, not a high-precision reproduction.

All final run artifact checksums passed. A verified run was also logged to local
SQLite-backed MLflow and read back with its metrics and artifacts intact. This
verifies the optional exporter, not a Databricks connection or a live model trace.

[Machine-readable evidence](local-validation.json) records the source/code hashes,
environment and limitations. [Reference outputs](../examples/percolation/reference-results/README.md)
include raw trials and reproduction commands. Full local audit files live in
`output/research/final-validation/`. Live Omnigent model execution, a Databricks
workspace run, full-scale paper reproduction and global novelty remain unverified.
