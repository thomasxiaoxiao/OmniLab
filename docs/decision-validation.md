# Decision-runtime validation

A real local AnyJev/Qwen run completed on October 3, 2026. No fixture backend,
remote model service, generated response text or scripted research decision was used.

- Run: `output/research/anyjev-final-validation-20261003`; prompt version `bounded-decisions-v4`.
- Selected experiment: **site percolation**, with the exact future-work evidence
  on PDF page 13. The model rejected random-Manhattan and resistor-diode proposals
  at the additional source-grounding check. These are model judgments, not expert labels.
- Executed: six baseline batches and two follow-up batches, **256 trials plus
  eight independent seed replays**. Baseline consistency and numerical checks passed.
- Inference: **11 closed decisions, 43 prefills,
  37,673 input tokens, zero generated tokens**;
  64.9 seconds end to end on this Mac.
- Outcome: `needs_literature_review`. The effect test failed and the validator
  selected inconclusive. The model's candidate-gap label could not bypass the
  requirement for multiple sources. No additional round spent resources on that gap.
- All artifact hashes and seven ordered journal stages verified. UI model answers
  are cross-checked against source choices, critiques and the selected plan.
- Targeted decision/tracking/UI checks: **35 passed**, including ambiguity stops,
  missing-model failures, explicit rejection, source-grounding rejection, fixed
  choice sets, context limits, budgets, tamper detection and artifact persistence.

Full details and distributions: [decision-validation.json](decision-validation.json).
This is a local engineering validation, not a benchmark of model accuracy or a
scientific discovery. In particular, a high L0 option weight is not calibrated
confidence. A human source spot-check was used to verify the accepted direction;
no saved model answer was altered.

## Development evidence retained

Earlier run directories remain intact. The first prompt selected a topic paragraph
instead of explicit future work. The reader question was corrected to distinguish
future suggestions from existing-model descriptions. A later grounding question
was too strict about evidence proving an experiment's outcome; it rejected all
proposals and correctly ran zero simulations. The final contract explicitly checks
whether an experiment operationalizes a suggested direction, separately from
whether measurements support its outcome. No rejected run was relabeled successful.

## Reproduce

```bash
uv sync --locked
uv run --locked research prepare-model
uv run --locked research fetch
uv run --locked research run --config examples/percolation/decisions.json \
  --output output/research/my-fresh-decision-run
uv run --locked research verify output/research/my-fresh-decision-run
uv run --locked pytest tests/test_decisions.py tests/test_tracking.py \
  tests/test_tracking_ui.py tests/test_ui.py
```

The run records its own code snapshot and lockfile. Other chats are concurrently
extending Omnigent; the last full-suite attempt had 117 passes and one unrelated
Omnigent timeout expectation failure (120 versus the newly configured 300 seconds).
Full-project lint also encountered those in-progress files. The targeted checks
above and the recorded local-model run are the verified scope of this report.
