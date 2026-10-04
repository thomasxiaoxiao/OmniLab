"""The measured result, Omnigent decision, and its enforced execution handoff."""

from hacknation_databricks.checkpoint_views import checkpoint_story
from hacknation_databricks.research_views import measurement_rows
from hacknation_databricks.synthesis_ui import render_comparison_outputs
from hacknation_databricks.tracking import Journal, read_artifact
from hacknation_databricks.web import components as ui


def render_checkpoint_story(journal: Journal, *, show_comparison=True) -> None:
    ui.subheader("What changed our next move?")
    ui.write(
        "Compare the original paper’s finding with the proposed simulation, then see "
        "how the new evidence changed the next experiment."
    )
    checkpoints = journal.report.get("checkpoints", [])
    if not checkpoints:
        ui.info("The first decision story appears after a simulation result has been reviewed.")
        return
    numbers = [c["checkpoint"] for c in checkpoints]
    default = next((c["checkpoint"] for c in checkpoints if c.get("goal_accepted")), numbers[-1])
    selected = ui.selectbox(
        "Decision checkpoint",
        numbers,
        index=numbers.index(default),
        format_func=lambda n: (
            f"Checkpoint {n} · "
            + next(c["branch_id"] for c in checkpoints if c["checkpoint"] == n)
            + (
                " · goal accepted"
                if any(c["checkpoint"] == n and c.get("goal_accepted") for c in checkpoints)
                else ""
            )
        ),
        key=f"checkpoint-story-{journal.run_id}",
    )
    try:
        story = checkpoint_story(journal, selected)
    except (ValueError, KeyError, OSError):
        ui.warning("The checkpoint evidence is incomplete. No execution claim is shown.")
        return
    checkpoint, payload, decision = story["checkpoint"], story["input"], story["decision"]
    node = story["decision_node"]
    previous = story["previous"]
    dataset = {
        "round": selected,
        "branch_id": checkpoint["branch_id"],
        "batch": checkpoint["batch"],
        "effect": payload["latest_result"],
    }
    if show_comparison:
        render_comparison_outputs(journal, dataset)
    ui.markdown("**Next move · recorded agent recommendation**")
    ui.write(decision["next_experiment"])
    ui.caption(
        "The execution record below distinguishes this recommendation from work actually run."
    )
    cells = ui.columns(4)
    with cells[0], ui.container(border=True, height="stretch"):
        ui.markdown("**1 · Previous plan**")
        ui.write(previous.get("action", "Initial screening").capitalize())
        ui.caption(
            "Invest in: "
            + (", ".join(previous.get("invest", [])) or "Initial portfolio / no new allocation")
        )
    with cells[1], ui.container(border=True, height="stretch"):
        ui.markdown("**2 · New evidence**")
        ui.write(f"{checkpoint['branch_id']} · batch {checkpoint['batch']}")
        latest = payload["latest_result"]
        ui.caption("Cumulative measurements through this batch")
        ui.write("Numerically eligible" if latest.get("goal_eligible") else "More evidence needed")
    with cells[2], ui.container(border=True, height="stretch"):
        ui.markdown("**3 · Agent decision**")
        ui.write(decision["action"].capitalize())
        target = (
            decision.get("goal_branch_id")
            or ", ".join(decision.get("invest", []))
            or "No further allocation"
        )
        ui.caption(target)
        ui.caption(
            (
                "AnyJev selection · Omnigent assessment recorded"
                if journal.config.get("decision_backend") == "anyjev"
                else "Omnigent response recorded"
            )
            if node and node.session_id
            else "No validated Omnigent session recorded"
        )
    with cells[3], ui.container(border=True, height="stretch"):
        ui.markdown("**4 · Actual action**")
        ui.write(story["outcome"])
        ui.caption("From recorded transitions and parent handoffs")

    if checkpoint.get("observation_after_stop"):
        ui.info(
            "This result came from work already authorized before stopping. "
            "Its review did not authorize a new batch."
        )
    elif checkpoint.get("goal_accepted"):
        ui.success(
            "The evidence changed the workflow from investing in more batches "
            "to accepting a scoped numerical result."
        )
    elif checkpoint.get("finalization_blocked"):
        ui.warning(checkpoint["finalization_blocked"])
    ui.markdown("**Why the decision changed · agent interpretation**")
    interpretation = decision["result_interpretation"]
    ui.write(decision["rationale"])
    ui.dataframe(
        story["allocation"],
        hide_index=True,
        width="stretch",
        alt="Previous and new requests, in-flight work, and execution linked to this checkpoint",
    )
    ui.caption(
        "A changed request does not cancel work already in flight. New executions are linked by "
        "their recorded parent handoffs, not by when they happened to finish."
    )
    enforcement, evidence, trace = ui.tabs(
        ["Shared runtime and guardrails", "Measurement and rationale", "Recorded handoff"]
    )
    with evidence:
        ui.write(interpretation)
        rows = measurement_rows({"effect": payload["latest_result"]})
        if rows:
            ui.dataframe(
                rows,
                hide_index=True,
                width="stretch",
                alt="Measurements and uncertainty available to this decision",
            )
        ui.caption(
            "These are the measurements available at this checkpoint; later results are excluded."
        )
        with ui.expander("Previous plan and decision rationale"):
            ui.markdown("**Previous plan**")
            ui.write(previous.get("next_experiment", previous.get("rationale", "Not recorded")))
            ui.markdown("**Decision rationale**")
            ui.write(decision["rationale"])
        with ui.expander("Proposed next experiment and missing evidence"):
            ui.caption(
                "Agent recommendation. Only the actual-action record above establishes execution."
            )
            ui.write(decision["next_experiment"])
            for item in decision.get("missing_evidence", []):
                ui.write("• " + item)
    with enforcement:
        ui.write(
            "Specialists use the common Omnigent Sessions API. The research supervisor validates "
            "their structured responses and applies the same branch, budget and completion rules "
            "before dispatching allowlisted Python experiments."
        )
        if story["common_constraints"]:
            ui.caption(
                "Every recorded specialist session received the same base request constraints. "
                "Each role also received its own task and structured output schema."
            )
        budget = payload.get("remaining_budget", {})
        cols = ui.columns(3)
        cols[0].metric(
            "Simulation units available then",
            f"{budget['simulations']:,}" if "simulations" in budget else "Unrecorded",
        )
        cols[1].metric("Agent calls available then", budget.get("agent_calls", "Unrecorded"))
        cols[2].metric(
            "Time available then",
            f"{budget['seconds'] / 60:.1f} min" if "seconds" in budget else "Unrecorded",
        )
        ui.caption(
            "Decision-time snapshot; simulation availability excludes work already reserved, "
            "including replay."
        )
        ui.dataframe(
            story["gates"],
            hide_index=True,
            width="stretch",
            alt="Execution boundaries, enforcing components, and their saved evidence",
        )
        with ui.expander("Specialist sessions on the shared runtime"):
            if story["sessions"]:
                ui.dataframe(
                    story["sessions"],
                    hide_index=True,
                    width="stretch",
                    alt="Recorded specialist session identities, responses and schema validation",
                )
            else:
                ui.info("No Omnigent sessions recorded for this run.")
            if story["common_constraints"]:
                ui.markdown("**Shared request constraints · archived instructions**")
                ui.text(story["common_constraints"])
            ui.caption(
                "A shared registered agent ID establishes runtime identity. Native Omnigent policy "
                "configuration was not archived here; scientific and budget enforcement shown "
                "above belongs to the Python supervisor. This is not sandbox attestation."
            )
    with trace:
        if node:
            ui.code(
                f"Omnigent session: {node.session_id}\nRegistered agent: {node.agent_id}\n"
                f"Decision: {node.call_id}",
                language="text",
            )
        ui.write(
            "Recorded chain: experiment result → Omnigent decision → validated transition "
            "→ downstream planner or evaluator."
        )
        for action in story["actions"]:
            ui.markdown(f"**{action['branch_id']} · batch {action['batch']} · {action['status']}**")
            ui.json(action["specification"], expanded=False)
        if story["artifacts"]:
            artifact = ui.selectbox(
                "Inspect checkpoint evidence",
                story["artifacts"],
                key=f"checkpoint-artifact-{journal.run_id}-{selected}",
            )
            raw = read_artifact(journal.directory, artifact)
            with ui.expander("Artifact contents"):
                ui.code(raw[:20000].decode("utf-8", errors="replace"), language="json")
                if len(raw) > 20000:
                    ui.caption("Preview limited to 20 KB. Download contains the full artifact.")
            ui.download_button(
                "Download selected evidence",
                raw,
                file_name=artifact.replace("/", "-"),
                mime="application/json",
                key=f"checkpoint-download-{journal.run_id}-{selected}",
            )
    ui.caption(
        "Numerical completion is a scoped simulation finding. "
        "Scientific novelty and real-world validity remain unverified."
    )
