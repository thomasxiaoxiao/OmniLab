# Remaining research work

These do not block the local CLI, baseline simulations, implemented follow-ups,
artifact verification or UI.

## Account-dependent integration

- Completed: Codex subscription authentication, online Omnigent host/session runners,
  and a real full-paper run. See `codex-live-run.md` for evidence and results.
- If using Databricks, install the optional integration, choose an existing
  workspace profile and serving model, and verify their permissions. No workspace,
  serving endpoint, Unity Catalog volume or cloud deployment was provisioned.
- Verify optional MLflow export against the actual Databricks workspace. Local
  SQLite-backed MLflow logging was exercised; a cloud export has not been run.
- Enable Omnigent's native model tracing on the chosen host if operational token,
  latency and cost monitoring is needed beyond saved session usage/audit events.

## Scientific acceptance beyond the base

- Extend the automated cited-arXiv retrieval beyond its bounded source/context budget,
  especially the directly relevant 2018 randomly oriented Manhattan reference.
  Missing papers stay visible in the audit; no missing source counts as novelty evidence.
- Increase predeclared sample sizes and lattice sizes, inspect finite-size effects,
  and cross-check against the authors' published C implementation. Keep precision
  claims proportional to measurements. No high-precision reproduction is claimed.
- Add square-ice sampling, exponent/hull analyses and threshold estimation only
  if those parts of the original paper become acceptance requirements.
- Completed: a separate evaluator compares the actual measurements with every
  supplied reference, validates quotations and reports added value. Optional domain
  review can corroborate conclusions; it is not a workflow gate. Broader scientific
  novelty still needs stronger empirical and literature evidence.

## Operational follow-ups

- Resume partially completed live sessions without replaying accepted model work;
  current fresh runs reuse numerical caches only.
- Publishing, deployment, recordings and a hackathon submission remain separate
  user/account actions. Existing PM2/GitHub infrastructure is preserved.
- The original housing-law challenge is a different deliverable and is not
  satisfied by this research prototype.
