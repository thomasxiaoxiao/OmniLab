"""Read-only route and stopping-decision ledger, including paths never executed."""

from .research_views import saved_json
from .web import components as ui


def route_ledger(journal):
    report = journal.report
    repository = report.get("workflow_version") == "5"
    if repository:
        reader = saved_json(journal, "approved_reader.json") or {}
        candidates = reader.get("directions", report.get("proposals", []))
        review = saved_json(journal, "approved_critic.json") or {}
    else:
        candidates = saved_json(journal, "candidates.json") or journal.proposals
        review = saved_json(journal, "consolidation.json") or {}
    critiques = {c["proposal_id"]: c for c in review.get("critiques", [])}
    branches = report.get("branches", {})
    selected = review.get("selected_proposal_id")
    routes = []
    for candidate in candidates:
        identity = candidate["id"]
        critique = critiques.get(identity, {})
        branch = branches.get(identity, {})
        if critique.get("decision") == "reject":
            status = "Rejected before execution"
        elif repository and identity == selected:
            status = (
                "Executed"
                if report.get("rounds")
                else (
                    "Selected · no completed experiment"
                    if journal.sealed
                    else "Selected · awaiting execution"
                )
            )
        elif branch:
            status = (
                f"Executed · {branch.get('batches', 0)} batches · {branch.get('status', 'unknown')}"
                if branch.get("batches")
                else "Accepted · no completed batch"
            )
        elif critique.get("decision") == "accept":
            status = "Accepted · not selected"
        else:
            status = "Awaiting critique"
        routes.append(
            {
                "id": identity,
                "title": candidate.get("title", identity),
                "status": status,
                "hypothesis": candidate.get("hypothesis", ""),
                "rationale": critique.get("rationale", "No critique recorded yet."),
                "risks": critique.get("risks", []),
                "evidence": candidate.get("evidence", []),
            }
        )
    return routes


def render_research_routes(journal):
    if journal.report.get("workflow_version") not in {"4", "5"}:
        return
    report = journal.report
    routes = route_ledger(journal)
    ui.subheader("Routes explored & stopping decisions")
    ui.caption(
        "Follow each idea from source evidence through critique, test selection and measured "
        "results. Rejected or unselected routes are retained; a proposed follow-up is not an "
        "executed experiment."
    )
    if not routes:
        ui.info("Specialists are still preparing the first candidate routes.")
    else:
        ui.dataframe(
            [{"Route": r["title"], "ID": r["id"], "Outcome": r["status"]} for r in routes],
            hide_index=True,
            width="stretch",
            alt="Every recorded research route and its outcome",
        )
    for route in routes:
        with ui.expander(f"{route['title']} · {route['status']}"):
            ui.write(route["hypothesis"])
            ui.markdown("**Why this route was accepted or rejected**")
            ui.write(route["rationale"])
            for risk in route["risks"]:
                ui.write(f"Limitation: {risk}")
            if route["status"] == "Accepted · not selected":
                ui.caption(
                    "The critic accepted this idea but chose another direction for this run. "
                    "No experiment on this route is recorded; acceptance is not validation."
                )
            for evidence in route["evidence"]:
                ui.write(
                    f"{evidence['source_id']} · page {evidence['page']}: “{evidence['quote']}”"
                )
    if report.get("workflow_version") == "5":
        plan = saved_json(journal, "planner.json") or {}
        if plan:
            with ui.expander("Tests considered & selection rationale", expanded=True):
                for test in plan.get("tests", []):
                    state = "Selected" if test["id"] == plan["selected_test_id"] else "Not selected"
                    ui.markdown(
                        f"**{test['id'].capitalize()} · {state} · {test['replicates']} pairs**"
                    )
                    ui.write(test["expected_learning"])
                    ui.write(test["feasibility"])
                ui.markdown("**Why this test**")
                ui.write(plan["rationale"])
        decisions = [
            (f"Experiment {r['round']}", r.get("next_decision", {}), r)
            for r in report.get("rounds", [])
        ]
    else:
        decisions = [
            (f"Checkpoint {r['checkpoint']} · {r['branch_id']}", r.get("decision", {}), r)
            for r in report.get("checkpoints", [])
        ]
    for index, (title, decision, record) in enumerate(decisions):
        with ui.expander(
            f"{title} → {decision.get('action', 'awaiting evaluation').replace('_', ' ')}",
            expanded=index == len(decisions) - 1,
        ):
            ui.markdown("**What the measurements changed**")
            ui.write(decision.get("result_interpretation", "Evaluation is pending."))
            ui.markdown("**Why continue, redirect or stop**")
            ui.write(decision.get("rationale", "No decision has been recorded."))
            if decision.get("invest"):
                ui.write("Next investment: " + ", ".join(decision["invest"]))
            if record.get("pending_branches"):
                ui.write(
                    "Still in flight at this decision: " + ", ".join(record["pending_branches"])
                )
            if decision.get("next_experiment"):
                ui.write("Recommended next experiment: " + decision["next_experiment"])
            for limitation in decision.get("limitations", decision.get("missing_evidence", [])):
                ui.write("Unresolved: " + limitation)
    status = report.get("status", "running")
    ui.markdown(f"**Run outcome: {status.replace('_', ' ')}**")
    if report.get("reason"):
        ui.write(report["reason"])
    if journal.sealed:
        ui.caption(
            "This run is closed. Ready or paused routes were not dispatched again; their "
            "last recorded decisions and unresolved evidence remain above."
        )
