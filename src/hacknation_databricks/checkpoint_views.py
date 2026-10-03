"""Project decision evidence without attributing concurrent work to the wrong checkpoint."""

import hashlib
import json

from hacknation_databricks.research.activity import load_activity
from hacknation_databricks.research_views import saved_json
from hacknation_databricks.tracking import Journal


def checkpoint_story(journal: Journal, number: int) -> dict:
    """Use the decision's input snapshot and explicit parent edges, never final branch state."""
    if journal.issues:
        raise ValueError("Unverified history cannot support a checkpoint story")
    checkpoint = next(c for c in journal.report["checkpoints"] if c["checkpoint"] == number)
    prefix = f"checkpoints/{number:03d}"
    payload = saved_json(journal, checkpoint["input"])
    if payload is None:
        raise ValueError("Checkpoint input is unavailable")
    nodes = load_activity(journal)
    stage = f"{prefix}/decision"
    attempts = [n for n in nodes if n.stage == stage]
    decision_node = next((n for n in reversed(attempts) if n.schema_valid), None)
    decision = checkpoint["decision"]
    previous = payload.get("previous_decision", {})
    initial = saved_json(journal, "consolidation.json") or {}
    before = previous.get("invest", initial.get("invest", []))
    requested = decision.get("invest", [])
    # Retried planner calls have an attempt as parent. Group by the original stage.
    planner_stages = {
        n.stage
        for n in nodes
        if n.stage.startswith("branches/")
        and n.stage.endswith("/planner")
        and stage in (n.parents or [])
    }
    actions = []
    for planner_stage in sorted(planner_stages):
        batch_prefix = planner_stage.rsplit("/", 1)[0]
        parts = batch_prefix.split("/")
        experiments = [
            n
            for n in nodes
            if n.stage == f"{batch_prefix}/experiment" and planner_stage in (n.parents or [])
        ]
        dispatched = any(e["event"] == "tool_dispatched" for n in experiments for e in n.events)
        completed = any(e["event"] == "tool_result" for n in experiments for e in n.events)
        plan = saved_json(journal, f"{planner_stage}.json") or {}
        options = saved_json(journal, f"{batch_prefix}/test_options.json") or {}
        specification = saved_json(journal, f"{batch_prefix}/specification.json") or {}
        option = options.get(plan.get("selected_test_id"), {})
        actions.append(
            {
                "branch_id": parts[1],
                "batch": int(parts[3]),
                "dispatched": dispatched,
                "completed": completed,
                "plan": plan,
                "option": option,
                "specification": specification,
                "prefix": batch_prefix,
                "status": "Result recorded"
                if completed
                else "Tool dispatched"
                if dispatched
                else "Planner started; no tool dispatch recorded",
            }
        )
    validation = saved_json(journal, f"{prefix}/validation.json")
    validators = [n for n in nodes if n.stage == f"{prefix}/validation"]
    if checkpoint.get("observation_after_stop") and actions:
        raise ValueError("Late review unexpectedly authorized new work")
    if checkpoint.get("observation_after_stop"):
        outcome = "Reviewed a late result; no new allocation"
    elif checkpoint.get("goal_accepted"):
        outcome = "Accepted the numerical goal; stopped new allocation"
    elif checkpoint.get("finalization_blocked"):
        outcome = "Finalization blocked by the research gates"
    elif decision["action"] == "stop":
        outcome = "Stopped new allocation"
    elif any(a["dispatched"] for a in actions):
        outcome = f"Dispatched {sum(a['dispatched'] for a in actions)} new simulation batch(es)"
    elif actions:
        outcome = "Started planning; no simulation dispatch recorded"
    elif validators:
        outcome = "Requested independent validation; acceptance not recorded"
    else:
        outcome = "No new execution recorded for this decision"
    allocation = []
    for key, branch in payload["branches"].items():
        was, now = key in before, key in requested
        change = "Retained" if was and now else "New request" if now else "Removed" if was else "—"
        linked = [a for a in actions if a["branch_id"] == key]
        allocation.append(
            {
                "Branch": key,
                "Direction": branch.get("proposal", {}).get("title", key),
                "Previous request": "Invest" if was else "—",
                "New request": "Invest" if now else "—",
                "Change": change,
                "Already in flight": "Yes" if key in payload.get("in_flight", []) else "No",
                "Execution from this decision": "; ".join(
                    f"Batch {a['batch']}: {a['status'].lower()}" for a in linked
                )
                or "No new batch recorded",
            }
        )
    source_prefix = f"branches/{checkpoint['branch_id']}/batches/{checkpoint['batch']:02d}"
    replay = saved_json(journal, f"{source_prefix}/checks.json")
    accepted = {c["proposal_id"] for c in initial.get("critiques", []) if c["decision"] == "accept"}
    authorized = set(initial.get("invest", [])) & accepted
    referenced = set(requested) | (
        {decision["goal_branch_id"]} if decision.get("goal_branch_id") else set()
    )
    gates = [
        {
            "Boundary": "Structured decision",
            "Enforced by": "Research supervisor",
            "Evidence": "Schema validated after the Omnigent response"
            if decision_node
            else "No schema-validated Omnigent response recorded",
            "Artifact": f"{prefix}/decision.json",
        },
        {
            "Boundary": "Reviewed directions only",
            "Enforced by": "Research supervisor",
            "Evidence": "All referenced branches were accepted and selected"
            if initial and referenced <= authorized
            else "Approved portfolio evidence unavailable or inconsistent",
            "Artifact": "consolidation.json",
        },
        {
            "Boundary": "Reproducible incoming result",
            "Enforced by": "Python experiment tools",
            "Evidence": "Deterministic seed replay passed"
            if replay and replay.get("passed")
            else "Replay confirmation unavailable",
            "Artifact": f"{source_prefix}/checks.json",
        },
    ]
    for action in actions:
        option = action["option"]
        gates.append(
            {
                "Boundary": f"{action['branch_id']} batch {action['batch']} budget",
                "Enforced by": "Research supervisor",
                "Evidence": (
                    f"Selected {action['plan'].get('selected_test_id', '?')} test "
                    "fits the reserved budget"
                )
                if option.get("within_simulation_budget") is True
                else "No affordable selected test recorded",
                "Artifact": f"{action['prefix']}/test_options.json",
            }
        )
    if decision["action"] == "finalize":
        eligible = payload["branches"].get(decision.get("goal_branch_id"), {}).get("goal_eligible")
        gates.append(
            {
                "Boundary": "Completion requires evidence and independent review",
                "Enforced by": "Research supervisor + evaluator",
                "Evidence": f"Numerical eligibility: {bool(eligible)}; review: "
                f"{validation.get('decision', 'unrecorded') if validation else 'unrecorded'}; "
                f"accepted here: {checkpoint.get('goal_accepted', False)}",
                "Artifact": f"{prefix}/transition.json",
            }
        )
    participants = [n for n in nodes if n.kind == "omnigent"]
    created = [n for n in participants if n.session_id]
    agent_ids = {n.agent_id for n in created if n.agent_id}
    shared_agent = bool(created) and len(agent_ids) == 1 and all(n.agent_id for n in created)
    responses = []
    constraints = []
    for node in created:
        response = saved_json(journal, f"{node.call_id}-response.json") if node.call_id else None
        request = saved_json(journal, f"{node.call_id}-request.json") if node.call_id else None
        prompt = json.loads(request["prompt"]) if request and request.get("prompt") else {}
        constraint = prompt.get("constraints")
        constraints.append(constraint)
        responses.append(
            {
                "Role": node.role,
                "Session": node.session_id,
                "Registered agent": node.agent_id,
                "State": node.status,
                "Response saved": bool(response and response.get("session_id") == node.session_id),
                "Schema accepted": node.schema_valid is True,
                "Prompt version": request.get("prompt_version") if request else None,
                "Request constraints SHA-256": hashlib.sha256(constraint.encode()).hexdigest()
                if isinstance(constraint, str)
                else None,
            }
        )
    artifacts = [
        checkpoint["input"],
        f"{prefix}/decision.json",
        f"{prefix}/transition.json",
        f"{source_prefix}/checks.json",
        "config.json",
        "events.jsonl",
    ]
    for node in [*attempts, *validators]:
        if node.call_id:
            artifacts.extend([f"{node.call_id}-request.json", f"{node.call_id}-response.json"])
    for action in actions:
        artifacts.extend(
            f"{action['prefix']}/{name}.json"
            for name in ["planner", "test_options", "specification", "checks"]
        )
    if validation:
        artifacts.append(f"{prefix}/validation.json")
    return {
        "checkpoint": checkpoint,
        "input": payload,
        "previous": previous,
        "decision": decision,
        "decision_node": decision_node,
        "actions": actions,
        "outcome": outcome,
        "allocation": allocation,
        "gates": gates,
        "shared_agent": shared_agent,
        "agent_ids": sorted(agent_ids),
        "sessions": responses,
        "common_constraints": constraints[0]
        if constraints
        and all(isinstance(c, str) and c and c == constraints[0] for c in constraints)
        else None,
        "artifacts": [
            name
            for name in dict.fromkeys(artifacts)
            if (not journal.sealed or name in journal.artifacts)
            and (journal.directory / name).is_file()
        ],
    }
