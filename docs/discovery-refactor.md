# Omnigent discovery workflow v3

The corrected scientific-discovery brief is implemented in the primary CLI and
frontend path. `research run` now defaults to Omnigent; AnyJev requires explicit
selection and remains supported. Dependencies are unchanged.

## Execution

Reader → critic selection → deterministic baseline → literature → planner test
comparison → deterministic experiment → validator → reference evaluator →
next-decision specialist → enforced supervisor transition.

The critic selects an accepted proposal rather than the supervisor taking the
first accepted item. The planner compares two tests of the selected hypothesis:
a screening sample and a precision sample with twice as many treatment trials.
Both retain the existing fixed-p recipe and baseline control data. These are
sampling alternatives, not different physical models or freely generated code.
The planner receives previous rounds and available simulation/time budgets.

The next-decision specialist sees the actual effect, validation, literature and
remaining budget. Its repeat/literature/stop recommendation is saved separately
from the supervisor action. Validation rejection, a completed evidence gate,
missing independent literature or exhausted rounds can prevent a requested repeat.
A future experiment described in prose is a recommendation, not executable code.

New artifacts are `rounds/NN/test_options.json`, `next_decision.json` and
`transition.json`. Existing plan identity, source quotations, finite simulation
budgets, numerical checks and artifact hashes remain enforced. Older full run
archives are still readable. Compact example snapshots are not full run archives.

## Frontend

The main page is **Omnigent scientific discovery lab**. **Discovery loop** presents
the hypothesis, exact source passage, compared tests, measured result, recommended
action and enforced supervisor action. Test cards expose sampling cost and their
learning/feasibility rationale. **Agents & loops** shows actual specialist sessions
and Python execution steps. Source intake, audit downloads, comparison views and
the optional local decision backend are retained.

Elapsed workflow time and computed simulations are measured. No comparable manual
baseline is supplied, so acceleration remains explicitly unverified. The scientific
result remains a bounded simulation check, not a claim of global novelty.

## Reproduce

Use the existing authenticated Omnigent server and host described in README.md:

```bash
uv sync --locked
bash scripts/research-runtime.sh status
.venv/bin/research run --config examples/percolation/discovery.json \
  --output output/research/my-discovery-run
.venv/bin/research verify output/research/my-discovery-run
npm run dev
```

Use a fresh output directory for each run. Automatic reference retrieval is on by
default. The two refactor smoke runs used `--no-auto-literature` to isolate the
orchestration change against the public seed paper; they cannot establish an
independent prior-art review. They preserve real model responses, numerical
results and explicit limitations. Test doubles remain restricted to tests.

See `discovery-validation.json` for the measured verification record. The local
development preview was refreshed; no production deployment or publication was
performed.
