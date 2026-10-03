"""The measured result, Omnigent decision, and its enforced execution handoff."""

import streamlit as st

from hacknation_databricks.checkpoint_views import checkpoint_story
from hacknation_databricks.research_views import measurement_rows
from hacknation_databricks.tracking import Journal, read_artifact


def render_checkpoint_story(journal: Journal) -> None:
    st.subheader("What changed our next move?")
    st.write(
        "Experimental evidence controls the next investment. Follow the previous plan, "
        "the measured result, the specialist's decision, and the action the workflow executed."
    )
    checkpoints = journal.report.get("checkpoints", [])
    if not checkpoints:
        st.info("The first decision story appears after a simulation result has been reviewed.")
        return
    numbers = [c["checkpoint"] for c in checkpoints]
    default = next((c["checkpoint"] for c in checkpoints if c.get("goal_accepted")), numbers[-1])
    selected = st.selectbox(
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
        st.warning("The checkpoint evidence is incomplete. No execution claim is shown.")
        return
    checkpoint, payload, decision = story["checkpoint"], story["input"], story["decision"]
    node = story["decision_node"]
    if journal.report.get("backend") == "omnigent":
        st.markdown("**One Omnigent runtime · multiple specialists · shared execution gates**")
        session_count = len({s["Session"] for s in story["sessions"]})
        role_count = len({s["Role"] for s in story["sessions"]})
        identity = (
            "one recorded agent identity"
            if story["shared_agent"]
            else "agent identity not uniform or incomplete"
        )
        st.caption(
            f"Across this run: {session_count} sessions · {role_count} specialist roles · "
            f"{identity}. "
            + (
                "Saved live run; inspecting it makes no model calls."
                if journal.sealed
                else "Unsealed run snapshot; recorded events only."
            )
        )
    else:
        st.caption("Auxiliary backend: this view does not establish live Omnigent execution.")

    previous = story["previous"]
    cells = st.columns(4)
    with cells[0], st.container(border=True, height="stretch"):
        st.markdown("**1 · Previous plan**")
        st.write(previous.get("action", "Initial screening").capitalize())
        st.caption(
            "Invest in: "
            + (", ".join(previous.get("invest", [])) or "Initial portfolio / no new allocation")
        )
    with cells[1], st.container(border=True, height="stretch"):
        st.markdown("**2 · New evidence**")
        st.write(f"{checkpoint['branch_id']} · batch {checkpoint['batch']}")
        latest = payload["latest_result"]
        st.caption("Cumulative measurements through this batch")
        st.write("Numerically eligible" if latest.get("goal_eligible") else "More evidence needed")
    with cells[2], st.container(border=True, height="stretch"):
        st.markdown("**3 · Agent decision**")
        st.write(decision["action"].capitalize())
        target = (
            decision.get("goal_branch_id")
            or ", ".join(decision.get("invest", []))
            or "No further allocation"
        )
        st.caption(target)
        st.caption(
            "Omnigent response recorded"
            if node and node.session_id
            else "No validated Omnigent session recorded"
        )
    with cells[3], st.container(border=True, height="stretch"):
        st.markdown("**4 · Actual action**")
        st.write(story["outcome"])
        st.caption("From recorded transitions and parent handoffs")

    if checkpoint.get("observation_after_stop"):
        st.info(
            "This result came from work already authorized before stopping. "
            "Its review did not authorize a new batch."
        )
    elif checkpoint.get("goal_accepted"):
        st.success(
            "The evidence changed the workflow from investing in more batches "
            "to accepting a scoped numerical result."
        )
    elif checkpoint.get("finalization_blocked"):
        st.warning(checkpoint["finalization_blocked"])
    st.markdown("**Why the decision changed · agent interpretation**")
    interpretation = decision["result_interpretation"]
    st.write(interpretation.split(". ", 1)[0].rstrip(".") + ".")
    st.dataframe(
        story["allocation"],
        hide_index=True,
        width="stretch",
        alt="Previous and new requests, in-flight work, and execution linked to this checkpoint",
    )
    st.caption(
        "A changed request does not cancel work already in flight. New executions are linked by "
        "their recorded parent handoffs, not by when they happened to finish."
    )
    enforcement, evidence, trace = st.tabs(
        ["Shared runtime and guardrails", "Measurement and rationale", "Recorded handoff"]
    )
    with evidence:
        st.write(interpretation)
        rows = measurement_rows({"effect": payload["latest_result"]})
        if rows:
            st.dataframe(
                rows,
                hide_index=True,
                width="stretch",
                alt="Measurements and uncertainty available to this decision",
            )
        st.caption(
            "These are the measurements available at this checkpoint; later results are excluded."
        )
        with st.expander("Previous plan and decision rationale"):
            st.markdown("**Previous plan**")
            st.write(previous.get("next_experiment", previous.get("rationale", "Not recorded")))
            st.markdown("**Decision rationale**")
            st.write(decision["rationale"])
        with st.expander("Proposed next experiment and missing evidence"):
            st.caption(
                "Agent recommendation. Only the actual-action record above establishes execution."
            )
            st.write(decision["next_experiment"])
            for item in decision.get("missing_evidence", []):
                st.write("• " + item)
    with enforcement:
        st.write(
            "Specialists use the common Omnigent Sessions API. The research supervisor validates "
            "their structured responses and applies the same branch, budget and completion rules "
            "before dispatching allowlisted Python experiments."
        )
        if story["common_constraints"]:
            st.caption(
                "Every recorded specialist session received the same base request constraints. "
                "Each role also received its own task and structured output schema."
            )
        budget = payload.get("remaining_budget", {})
        cols = st.columns(3)
        cols[0].metric(
            "Simulation units available then",
            f"{budget['simulations']:,}" if "simulations" in budget else "Unrecorded",
        )
        cols[1].metric("Agent calls available then", budget.get("agent_calls", "Unrecorded"))
        cols[2].metric(
            "Time available then",
            f"{budget['seconds'] / 60:.1f} min" if "seconds" in budget else "Unrecorded",
        )
        st.caption(
            "Decision-time snapshot; simulation availability excludes work already reserved, "
            "including replay."
        )
        st.dataframe(
            story["gates"],
            hide_index=True,
            width="stretch",
            alt="Execution boundaries, enforcing components, and their saved evidence",
        )
        with st.expander("Specialist sessions on the shared runtime"):
            if story["sessions"]:
                st.dataframe(
                    story["sessions"],
                    hide_index=True,
                    width="stretch",
                    alt="Recorded specialist session identities, responses and schema validation",
                )
            else:
                st.info("No Omnigent sessions recorded for this run.")
            if story["common_constraints"]:
                st.markdown("**Shared request constraints · archived instructions**")
                st.text(story["common_constraints"])
            st.caption(
                "A shared registered agent ID establishes runtime identity. Native Omnigent policy "
                "configuration was not archived here; scientific and budget enforcement shown "
                "above belongs to the Python supervisor. This is not sandbox attestation."
            )
    with trace:
        if node:
            st.code(
                f"Omnigent session: {node.session_id}\nRegistered agent: {node.agent_id}\n"
                f"Decision: {node.call_id}",
                language="text",
            )
        st.write(
            "Recorded chain: experiment result → Omnigent decision → validated transition "
            "→ downstream planner or evaluator."
        )
        for action in story["actions"]:
            st.markdown(f"**{action['branch_id']} · batch {action['batch']} · {action['status']}**")
            st.json(action["specification"], expanded=False)
        if story["artifacts"]:
            artifact = st.selectbox(
                "Inspect checkpoint evidence",
                story["artifacts"],
                key=f"checkpoint-artifact-{journal.run_id}-{selected}",
            )
            raw = read_artifact(journal.directory, artifact)
            with st.expander("Artifact contents"):
                st.code(raw[:20000].decode("utf-8", errors="replace"), language="json")
                if len(raw) > 20000:
                    st.caption("Preview limited to 20 KB. Download contains the full artifact.")
            st.download_button(
                "Download selected evidence",
                raw,
                file_name=artifact.replace("/", "-"),
                mime="application/json",
                key=f"checkpoint-download-{journal.run_id}-{selected}",
            )
    st.caption(
        "Numerical completion is a scoped simulation finding. "
        "Scientific novelty and real-world validity remain unverified."
    )
