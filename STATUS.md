# Repository consolidation

Last update: October 3, 2026, 13:26 PDT. Approximately 10 hours 41 minutes
remain before the original hard stop; this task is consolidation and deployment.

- Consolidated the existing research implementation, tests, examples and documentation.
- Validation: lint, formatting, 132 tests, PM2 syntax and saved Codex run hashes pass.
- Remote feature branches were already deleted; stale tracking refs were pruned.
- One primary checkout exists; no secondary worktrees require removal.
- Stable source, model, output and Omnigent paths are configured in ignored `.env`.
- Current task: commit to main, push, verify CI, and deploy the resulting revision.
- Local endpoint: `http://127.0.0.1:8010` (deployment verification pending).
- Private runtime data stays local; portable results are in `examples/percolation/`.

---

# Live Codex research milestone

Last update: October 3, 2026, 13:18 PDT. Hard stop: October 4, 00:07 PDT;
approximately 10 hours 49 minutes remain. Core requested live implementation is complete;
all checks pass and handoff is complete. No need to consume the remaining window.

- Completed: Codex subscription configuration, current desktop CLI discovery,
  local Omnigent server and online host, one runner per role, future API-key route.
- Measured live run: `output/research/codex-full-paper`, status `review_complete`;
  six completed model sessions; 4,096 trials and eight successful seed replays.
- Completed: automatic bounded cited-arXiv retrieval, grounded novelty evaluator,
  source quote checks, comparison chart and original/follow-up evidence cards.
- Result: incremental extension. Combined effect threshold not met; no global
  novelty or high-precision reproduction claim. Two references reviewed; one
  downloaded reference excluded by context budget; direct 2018 reference not fetched.
- Verification: `npm run check` passes lint, format, 132 tests and PM2 syntax.
  Full run hashes and decision ledger verified; actual UI inspected in browser
  on `http://127.0.0.1:8503`. Comparison screenshot saved under `docs/images/`.
- Current task: complete. Demo, Omnigent server and host remain available locally.
  Completed role runners have been stopped; no background research loop is active.
- Remaining limits: provider usage is null; API-key inference and cloud deployment
  not live-tested. Human review is optional, never a required execution gate.
- Commands: see `docs/codex-live-run.md`; result snapshot under
  `examples/percolation/codex-results/`.

---

# Research workflow implementation

Last update: October 3, 2026, 12:44 PDT. Hard stop remains October 4 at 00:07 PDT.

- Scope: latest user request follows `docs/overall-design.md`: Omnigent research
  workflow and directed-percolation paper, superseding housing implementation.
- Complete: strict research workflow, source/evidence validation, three baseline
  models, three allowlisted extensions, bounded Omnigent Sessions API adapter,
  native configuration/onboarding, CLI, research UI and optional MLflow export.
- Verified: exact `npm run check` passes all 84 tests, lint/format and PM2 syntax;
  fresh noneditable production installation runs without credentials; source
  download, artifact hashes, cache replay and local MLflow export pass.
- Measured: full-paper scripted run has 2,048 trials plus 8 seed replays, six
  baseline batches passing the declared tolerance, randomized-Manhattan follow-up
  executed. Combined effect/novelty gate remains unmet; status is
  `needs_literature_review`. Artifacts: `output/research/final-validation/`;
  compact reference results: `examples/percolation/reference-results/`.
- Current task: base implementation complete; reproducible handoff in README,
  `docs/research-implementation.md`, `docs/local-validation.md` and demo walkthrough.
- Next external step: configure a real Omnigent provider/runner and supplied
  literature, then run live mode. See `docs/research-todos.md`.
- External gaps: no model/Databricks credentials configured in project `.env`;
  no scientific novelty or full-scale paper reproduction claimed.
- Remaining deadline time: about 11 hours 23 minutes; base finished early.

## Decision tracking frontend checkpoint

Updated October 3, 2026, 12:40 PDT; roughly 11 hours 27 minutes to hard stop.

- Completed: default decision control room, retained research results page,
  closed launch profiles, seven-step journal, Jev-style typed choice inspector,
  implementation tracking, evidence downloads, environment view and JSON ledger.
- Boundaries: engine-controlled transitions; independent trace, quote, plan,
  budget, novelty-gate and artifact checks; invalid histories are quarantined.
- Verified: real local scripted run saved at `output/research/ui-verification`,
  seven documented steps, three proposals, 32 hashed artifacts. Novelty gate held.
  Final checks: 84 tests passed; lint, formatting and PM2 config syntax passed.
- Current task: frontend implementation complete; local preview at port 8502.
  Browser verified the journal, typed decision inspector and implementation path.
  The `uv` wrapper hit a macOS sandbox panic; equivalent checks passed through
  the installed `.venv` executables without modifying the environment.
- Limitation: Jev-style decision pattern only; no Jev API integration or calibrated
  probabilities. Live Omnigent execution depends on the backend's external setup.
- Reproduce: `npm run dev`; see `docs/decision-tracking.md` for verification commands.

## Open-source decision-only runtime checkpoint

Updated October 3, 2026, 13:13 PDT; about 10 hours 54 minutes to hard stop.

- Completed: AnyJev + pinned local MLX Qwen3 4B inference, default backend,
  explicit options and scores, source-grounding check, model-ranked direction,
  strict state/quote/plan/ambiguity/budget gates, model process cleanup and setup CLI.
  Scripted research responses now exist only as test doubles.
- Real run: `output/research/anyjev-final-validation-20261003/`; 11 decisions,
  43 prefills, 37,673 input tokens, zero generated tokens. The model selected and
  executed site percolation; six baseline and two follow-up batches plus eight
  seed replays completed. All saved hashes and seven journal stages verified.
- Outcome: `needs_literature_review`; finite-size effect inconclusive and the
  multi-source requirement unmet. Model candidate-gap labels cannot bypass gates.
- Verified: 35 targeted decision/tracking/UI tests passed. Full-suite attempt
  had 117 passes and one unrelated concurrent Omnigent timeout assertion failure;
  other chats are still extending that backend. Preserved their work.
- Current task: completed. Browser verified the final model run, scored critic
  decisions and source evidence. Local preview runs on port 8502.
- Reproduce: `research prepare-model`, `research fetch`, then
  `research run --config examples/percolation/decisions.json`.
- Limits: Apple Silicon MLX adapter; uncalibrated L0 scores; three executable
  recipes; retrieved source passages; no established novelty. See
  `docs/decision-runtime.md` and `docs/decision-validation.md`.

## Source intake and agent visibility checkpoint

Updated October 3, 2026, 13:20 PDT; about 10 hours 47 minutes to the hard stop.

- Complete: PDF/Markdown uploads, modern/legacy arXiv links and version resolution,
  immutable source library, provenance/checksums, bounded downloads and extraction,
  seed/related selection, and original/provenance snapshots in each run.
- Complete: recorded agent/session lifecycle, failure/partial-response evidence,
  per-worker graph grouped by actual rounds, multiple sessions within a stage,
  step artifact inspection, JSON trace and SVG graph downloads. Local inference
  and Python simulations are distinct from Omnigent sessions.
- Verified: 132 full-project tests passed; repository lint, formatting and PM2
  configuration checks passed. The intake/activity subset has 33 passing tests.
  Browser exercised a real versioned arXiv import plus PDF and Markdown uploads.
- Measured: cached paper has 16 pages and 73,812 extracted characters. Verified
  `codex-full-paper` artifacts project to 6 Omnigent sessions and 2 simulations.
  No future/unexecuted round is displayed. Scientific novelty remains unverified.
- Current task: final visual verification complete; local preview at port 8504.
  Saved screenshot, SVG and JSON trace are in `output/intake-verification/`.
- Reproduce: `npm run dev`; see `docs/source-intake.md` for CLI and test commands.
- Limits: scanned PDFs require OCR before upload; no text truncation; launch is
  synchronous, and ongoing saved runs update through Refresh artifacts. Remote
  arXiv service availability is required for uncached downloads/version resolution.
