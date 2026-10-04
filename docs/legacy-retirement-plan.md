# Proposed retirement of obsolete preset tests

The application already contains no preset simulation kernels. These remaining
kernels live only in tests/legacy and are excluded from the wheel. The user now
requests their removal from the repository as well.

Removing that package makes the following older tests unable to run because they
execute its v3/v4 kernels directly or through fixture_roles. Proposed retirement:
fixture_roles.py; test_activity.py; test_adaptive.py; test_checkpoint_views.py;
test_comparison_outputs.py; test_decisions.py; test_discovery.py;
test_measurement_contract.py; test_paper_isolation.py; test_process_visualization.py;
test_reference_review.py; test_research.py; test_simulation.py; test_tracking.py.
Four legacy-only cases in test_tracking_ui.py, test_intake_ui.py and
test_frontend_views.py also depend on it.

The risk is loss of older workflow regression coverage, including tracking and
corruption scenarios. Current generated-workflow tests remain: repository execution,
provenance/tampering/replay, UI/API intake, route decisions, live refresh, budgets,
artifact hashing, security, deployment and sandbox tests. No current test will be
relabeled as historical scientific evidence. Existing Git history preserves the
retired sources. This proposal has not been executed: automatic approval review
rejected the broad test retirement pending explicit human approval.
