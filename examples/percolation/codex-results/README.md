# Measured Codex/Omnigent result

This snapshot comes from the real `output/research/codex-full-paper` run on
October 3, 2026. It is not a fixture or scripted role run. See
`docs/codex-live-run.md` for setup, measured results and limits.

`session-audit.json` records six completed live role sessions. Provider token usage
was unavailable. `source-index.json` identifies the original seed and two reviewed
references by URL, version and SHA-256. `reference_retrieval.json` also records the
downloaded reference excluded by the context limit.

This is a compact result snapshot, not the complete run archive. Raw trials,
prompts, full source pages, code, dependencies and audit events remain in the run
directory. `sha256.json` protects the copied result files against accidental drift.

The automated verdict is **incremental extension**. The combined numerical effect
criterion did not pass; no verified global novelty or high-precision reproduction
is claimed.
