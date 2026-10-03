# Two-minute adaptive discovery demo

Open the local preview at http://127.0.0.1:8504. Select
`omnigent-adaptive-percolation-validated` in the persistent run selector. This is
a saved **live Omnigent** run; inspecting it makes no new model calls. To show a
new live run, use Source intake → Standard exploration → Start bounded run and
allow about five minutes before the two-minute walkthrough.

1. **0:00–0:20 — Question and evidence.** In Discovery overview, open the pinned
   percolation paper and the source passages. Explain that three researchers
   independently read the seed and retrieved citations. A consolidator critiques
   their candidates and invests in three executable directions.
2. **0:20–0:45 — One runtime, shared execution gates.** In Discovery overview,
   open **Shared runtime and guardrails** under **What changed our next move?**
   The run recorded 22 sessions across five specialist roles under one registered
   Omnigent agent identity, with 21 completed responses. Expand the session table
   to inspect the archived common request constraints and per-role responses.
   Omnigent supplies the common session interface; the Python supervisor enforces
   scientific and budget gates. Native Omnigent policy configuration was not
   archived, so do not claim server-side policy or sandbox attestation.
3. **0:45–1:10 — Result changes investment.** Switch from checkpoint 5 to 6.
   Follow **previous plan → new evidence → agent decision → actual action**.
   Checkpoint 5 links to the next site-percolation batch. At checkpoint 6 the
   bidirectional-diode result meets the numerical goal, independent review
   supports it, and new allocation stops. In **Measurement and rationale**, L=8
   and L=16 show wrapping increases of 0.215 and 0.248. **Recorded handoff** exposes
   the exact input, response, transition and downstream execution artifacts.
   Checkpoints 7–8 review already authorized work; they did not launch new batches.
   A reverse-edge-fraction sweep remains a recommendation, not executed work.
4. **1:10–1:40 — Second paper and tradeoff.** Select
   `omnigent-adaptive-astrosat-validated`. Three competing spatial guards receive
   nine result reviews. The three-sigma guard reduces fresh misses from 15.3%
   to 0/897 and stale misses from 12.7% to 2/880, while false-alert rates rise
   from about 15% to 56–58%. Show the recovery/false-alert table and checkpoint 7.
   These are simulated candidates, not observed satellite predictions.
5. **1:40–2:00 — Honest finish.** Open Baseline and final validation and Generated
   artifacts. Point to raw trials, seed/replay checks, source hashes, session IDs
   and the manifest. Both goals are limited numerical findings; novelty, exact
   interval coverage and operational benefit remain unproven. Median time from
   partial result to decision, including queueing, was about 46 seconds in each
   run. There is no measured human baseline and no verified speedup multiplier.

Both loops stopped after accepted goals, then reviewed already authorized late
batches without launching new work. Earlier failed and interrupted attempts are
preserved separately. The demonstration is local; no recording, public deployment,
publication or submission is implied.

Reproduction commands and model assumptions are in `docs/adaptive-discovery.md`.
Measured counts and archive verification are in `docs/adaptive-validation.json`.
Compact portable snapshots are in `examples/{percolation,astrosat}/adaptive-results/`;
complete immutable run archives remain under `output/research/`.
