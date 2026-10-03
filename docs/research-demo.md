# Three-minute demonstration

## Verified Codex subscription showcase

1. Open the local app and select `codex-full-paper`. No live call is needed to
   view this saved result.
2. In **Agents & loops**, show six real Omnigent sessions, including the separate
   novelty evaluator. Inspect the critic rejecting the unsupported site-threshold
   rationale while accepting the bounded randomized-Manhattan comparison.
3. Open **Original vs follow-up**. Show the two wrapping comparisons, their
   conservative lower bounds and the `incremental_extension` verdict.
4. Expand a comparison's evidence to show exact source quotes and paper links.
   Open the reference audit to show which whole papers were reviewed or excluded.
5. Explain that all baseline checks and seed replays passed, while the combined
   five-point effect criterion did not. The workflow completed automatically;
   it did not manufacture novelty or wait for human approval.
6. In **Artifacts**, download the ledger and inspect the saved trials and hashes.
   Use the commands in `codex-live-run.md` to launch another subscription-backed run.

## Local AnyJev alternative

1. Start `npm run dev` and open the decision control room. Select a saved AnyJev
   run or launch one after `research prepare-model` and `research fetch`.
2. Open the reader entry: show the candidate source passages, selected exact
   quotation, full option scores and retrieval scope.
3. Open the critic entry: compare accept/reject/defer judgments, then the separate
   decision selecting the most realistic accepted direction. No first-item fallback.
4. Show the baseline gate, locked experiment plan and actual implementation result.
   In **Research results**, inspect the raw wrapping measurements and intervals.
5. Open validation and the novelty gate. Read the actual stop reason, including
   inconclusive effects or missing literature. L0 option weights are uncalibrated.
6. Download the ledger. Show the model revision, input hashes, zero generated
   tokens and artifact hashes. Numerical results are reproducible from saved seeds;
   a closed model decision is evidence about a choice, not proof of scientific truth.

For a technical recording, trace `decision_roles.py` → `decision_worker.py` →
`workflow.py` → `simulation.py`. Explain bounded candidate retrieval, AnyJev option
rotations, MLX inference, typed decisions, independent numerical gates, finite
budgets and the audit trail. Do not describe local tests as an organizer score.
