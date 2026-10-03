"""Visible sessions, real loop iterations, and their inspectable outputs."""

import json
from dataclasses import asdict
from pathlib import Path

import streamlit as st

from hacknation_databricks.research.activity import activity_export, activity_svg, load_activity
from hacknation_databricks.tracking import Journal, read_artifact


def render_activity(journal: Journal) -> None:
    st.subheader("Agents & execution loops")
    st.caption(
        "Only recorded work appears here. Select a step to inspect its session, inputs and outputs."
    )
    nodes = load_activity(journal)
    if not nodes:
        st.info("No stage has started yet. Agent sessions appear after Omnigent creates them.")
        return
    sessions = {n.session_id for n in nodes if n.session_id}
    metrics = st.columns(4)
    metrics[0].metric("Omnigent sessions", len(sessions))
    metrics[1].metric("Worker executions", len(nodes))
    metrics[2].metric("Rounds entered", len({n.round for n in nodes if n.round}))
    metrics[3].metric("Produced artifacts", len({a for n in nodes for a in n.artifacts}))
    if not sessions:
        st.info(
            "No Omnigent sessions were recorded in this run. "
            "The graph shows the actual backend's steps."
        )
    st.caption(
        "Arrows follow recorded execution. A repeat appears only when another round ran. "
        "The green outline marks the selected worker."
    )
    selected = st.selectbox(
        "Inspect execution step",
        range(len(nodes)),
        format_func=lambda i: (
            f"{i + 1:02d} · {nodes[i].stage} · {nodes[i].role} · {nodes[i].status}"
        ),
    )
    node = nodes[selected]
    graph = activity_svg(nodes, node.key)
    st.image(graph, width="stretch", alt="Recorded agent executions grouped by round")
    left, right = st.columns([1, 1.4])
    with left, st.container(border=True):
        st.markdown(f"**{node.role.capitalize()} · {node.status}**")
        st.text(f"Session: {node.session_id or 'No Omnigent session recorded'}")
        st.text(f"Agent: {node.agent_name or node.kind}")
        if node.runner_id:
            st.text(f"Runner: {node.runner_id}")
        st.caption(f"Started: {node.started_at}")
        if node.seconds is not None:
            st.caption(f"Duration: {node.seconds:.2f}s")
        if node.error_type:
            st.error(f"Step stopped: {node.error_type}. Inspect the saved response and events.")
        if node.schema_valid:
            st.caption(
                "Response passed its schema. Stage status also includes downstream evidence checks."
            )
        if node.stage_status == "failed" and node.status == "completed":
            st.warning("This agent returned a valid response, but its workflow stage later failed.")
        if node.usage is not None:
            st.json(node.usage, expanded=False)
        with st.expander("Session metadata & lifecycle"):
            st.json({k: v for k, v in asdict(node).items() if k not in {"artifacts", "events"}})
            st.json(node.events, expanded=False)
    with right, st.container(border=True):
        st.markdown("**Inputs & produced artifacts**")
        if node.artifacts:
            artifact = st.selectbox("Step artifact", node.artifacts)
            try:
                raw = read_artifact(journal.directory, artifact)
                if artifact.endswith(".json"):
                    st.json(json.loads(raw), expanded=False)
                else:
                    st.code(raw[:20000].decode("utf-8", errors="replace"), language=None)
                    if len(raw) > 20000:
                        st.caption("Preview limited to 20 KB; download includes the complete file.")
                st.download_button(
                    "Download step artifact",
                    raw,
                    file_name=Path(artifact).name,
                    key="activity_artifact",
                )
            except (OSError, ValueError):
                st.warning("Artifact is not yet readable. Refresh the run.")
        else:
            st.info("This step has not saved an artifact yet.")
    st.dataframe(
        [
            {
                "Step": n.stage,
                "Role": n.role,
                "Backend": n.kind,
                "Session": n.session_id or "—",
                "Status": n.status,
                "Seconds": n.seconds,
                "Artifacts": len(n.artifacts),
            }
            for n in nodes
        ],
        hide_index=True,
        use_container_width=True,
    )
    st.download_button(
        "Export execution trace",
        activity_export(journal, nodes),
        file_name=f"{journal.run_id}-execution.json",
        mime="application/json",
    )
    st.download_button(
        "Download execution graph",
        graph,
        file_name=f"{journal.run_id}-graph.svg",
        mime="image/svg+xml",
    )
