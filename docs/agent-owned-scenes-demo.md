# Two-minute demo: agent-owned simulation and visualization

Open the local testing app at http://127.0.0.1:8000/overview and select
`20261004T061400-agent-scenes-schema`. This is a saved live Omnigent run;
inspection makes no new model calls. Its measured validation is in
[agent-owned-scenes-validation.json](agent-owned-scenes-validation.json).

1. **0:00–0:25 — Question and picture.** Show the recorded lattice crop and scrub
   occupation probability. The agents chose a spatial view of alternating versus
   independently randomized street directions. The full simulated graph is 16×16;
   the displayed 3×3 crop is explicitly limited and cannot establish winding.
   The timeline is occupation probability, not physical time.
2. **0:25–0:55 — Agents and decisions.** Open Agents & execution loops. The reader
   and literature researcher overlapped for 32.628 seconds. Seven sessions include
   one critic citation repair. Show three proposed routes, two deferred routes,
   two candidate tests, and the planner's comparison of visualization options.
3. **0:55–1:25 — Actual executed work.** Generated artifacts contains the agent's
   `code/experiment.py`, the supplied paper, prompts, parameters, seeds and raw
   trials. That program implements the graph and scene generation with NumPy/SciPy;
   it does not import an application lattice kernel or domain visualization adapter.
   The supervisor ran 18 sandbox jobs: eight paired realizations plus sanity/replay.
4. **1:25–2:00 — Learning and stop.** Control wrapping was 0.625 versus 0.75 for the
   treatment, with an exploratory paired interval of −0.411 to +0.661 for the
   difference. The evaluator called this inconclusive and stopped: changing only
   treatment size or occupation would confound the comparison. It proposed a new
   precision study at the same endpoint. Exact archived-code replay matched every
   numerical result and recorded scene with zero model calls.

The earlier `20261004T061600-agent-owned-scenes` attempt remains saved as a failure:
its generated output contained an undeclared measurements field. No results were
rewritten to pass validation. New agents receive the complete output/scene schemas.

## Reproduce and inspect

```bash
.venv/bin/research verify output/research/20261004T061400-agent-scenes-schema
.venv/bin/research replay-code output/research/20261004T061400-agent-scenes-schema \
  --output output/replays/my-new-scene-replay
# Fresh research: requires the running Omnigent server/host and existing authentication.
.venv/bin/research run --paper data/papers/2607.24975v1.pdf \
  --config experiments/agent-owned-scenes.json \
  --output output/research/my-new-agent-experiment
```

Use fresh output directories. A new research run makes its own choices; it is not
expected to reproduce the same proposal or image. Replay reruns the exact archived
program. Neither a sanity pass nor deterministic replay independently validates
physics, author-code equivalence, novelty or real-world applicability. No comparable
manual baseline exists, so an acceleration multiplier remains unverified.
