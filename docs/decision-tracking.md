# Exploration decision control room

Run `npm run dev` and open http://127.0.0.1:8000. The default page is the
**Decision control room**; **Research results** preserves the numerical results
viewer. Both use the existing research engine. No separate frontend build or
service is needed.

The control room follows the research workflow in `overall-design.md` and the
[Jev decision pattern](https://docs.typesafe.ai/introduction): inspect state,
ask a closed question, and let application code determine the permitted action.
New runs use the open-source AnyJev decision engine with local Qwen logits, not
the proprietary Jev API. The actual backend is shown on every run. Each model
choice includes its full L0 distribution, state, evidence and model revision.
Weights are uncalibrated; deterministic numerical gates have no model scores.
See [decision runtime](decision-runtime.md) for installation and the architecture choice.

## Inspect a run

1. Choose a saved run, or start a bounded run from a registered source and fixed
   environment profile. Run `research prepare-model` and `research fetch` first.
2. Follow the seven-stage path and the current novelty gate. A completed step
   means its execution was recorded, not that the research claim is established.
3. Expand a journal entry to inspect its state, typed choices, selected answer,
   rationale, evidence hashes, gate, and implementation reference. Filter by
   attention state or search decisions, explanations and artifact names.
4. Open **Implementations & path** to see which source-backed proposal received
   a plan. **Artifacts** previews and downloads the saved inputs and outputs.
   **Environment** records the seed, budgets, code identity and source provenance.
5. Export the decision ledger as JSON. It is deterministically derived from the
   original audit log and artifacts; exporting never changes a sealed run.

## Boundaries and documented decisions

| Decision | Enforcement | Visible evidence |
| --- | --- | --- |
| Limit exploration to the reviewed source | Registered source selection; existing source and quote contracts | Source hash, excerpt/full-text label, source-local citations |
| Propose at most three directions | `ProposalBatch` and allowlisted experiment types | Reader choices, proposals, quotes |
| Critique before execution | Ordered engine stages; exactly one critique per proposal | Accept/reject/defer record for each direction |
| Preserve baseline requirements | Deterministic numerical and replay checks | Validation report, raw trials and summaries |
| Lock an implementation | Model ranks accepted proposals; plan must match its selected direction | Competing directions, full scores, execution/stop choice |
| Bound execution | Fixed profiles; finite rounds, calls, workers, wall time and simulations | Original config and current round count |
| Stop unsupported novelty claims | Deterministic evidence gate with reference evaluator for Omnigent | Each criterion and the actual stop reason |
| Preserve audit provenance | Original append-only events plus artifact manifest | Hash verification, immutable downloads and derived ledger |
| Reject broken history | Viewer replays the allowlisted path and validates contracts | Quarantine banner for invalid evidence, stage skips or budget violations |

The Python engine controls execution; the viewer cannot approve a gate or invoke
an arbitrary next state. Explanations and paper text are data, never instructions.
The viewer independently rejects changed artifacts, fabricated quotes, unknown
stages, duplicate/overlapping stages, mismatched plans, invalid retry routes and
out-of-budget histories. This is local integrity checking, not cryptographic
attestation against a writer who can replace both artifacts and the manifest.

UI starts are serialized with a nonblocking filesystem lock. Each run gets a
fresh directory. The lock is scoped to this UI and output root; externally
launched CLI jobs retain their own per-run budgets. The legacy results page uses
the original launch controls and can also produce compatible saved runs.

## Files and configuration

- `src/hacknation_databricks/ui.py`: application navigation.
- `src/hacknation_databricks/tracking_ui.py`: UI and closed launch profiles.
- `src/hacknation_databricks/tracking.py`: evidence validation and decision projection.
- `output/research/<run>/`: original engine output, including `events.jsonl`.

Set `RESEARCH_RUNS_DIR` to change the control room's run root;
`RESEARCH_OUTPUT_DIR` remains a supported fallback. Only immediate child run
directories are listed; file paths are confined to the selected run. The viewer
limits individual artifacts to 20 MiB and histories/manifests to 1,024 entries.

The control room launches AnyJev only. Runtime readiness checks dependency and
manifest presence; a run verifies model hashes and actual inference. Missing or
failed inference stops with an audited status. `RESEARCH_DECISION_MODEL_DIR`
selects the local directory for the pinned model, not a different model identity.
Historical scripted artifacts remain labeled and viewable; they cannot launch
new scripted decisions. Omnigent is available in the UI and CLI with Codex subscription authentication;
see `codex-live-run.md`.

## Verification

```bash
uv run --locked pytest tests/test_tracking.py tests/test_tracking_ui.py tests/test_ui.py
uv run --locked ruff check src/hacknation_databricks/tracking.py \
  src/hacknation_databricks/tracking_ui.py src/hacknation_databricks/ui.py
```

Tests cover a real deterministic run, trace ordering, closed answer sets, quote
fabrication, mismatched plans, altered artifacts, manifest path escape, budget
violations, malformed input, launch restrictions, persistence, filters, empty
state and quarantine rendering. Deterministic test doubles live only under
`tests/`; they do not verify model quality. Real-model runs retain inference usage
and option scores in `decisions/`. Not legal advice.
