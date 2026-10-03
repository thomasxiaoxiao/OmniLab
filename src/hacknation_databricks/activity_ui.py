"""Visible sessions, real loop iterations, and their inspectable outputs."""

import json
from collections import Counter
from dataclasses import asdict
from pathlib import Path

import streamlit as st

from hacknation_databricks.research.activity import activity_export, activity_svg, load_activity
from hacknation_databricks.research_views import (
    downstream_steps,
    label,
    recorded_prompt,
    saved_json,
    workflow_dot,
)
from hacknation_databricks.tracking import Journal, read_artifact


def render_prompt_actions(journal, nodes, node, prompts):
    st.subheader("Prompt → response → next action")
    prompt = prompts.get(node.key)
    if not prompt:
        if node.kind == "simulation":
            st.info(
                "Python executes this simulation from the approved specification; "
                "it has no agent prompt."
            )
        else:
            st.info("No saved Omnigent prompt is available for this invocation.")
        return
    st.caption(
        f"{label(node.role)} · {prompt['input_scope']} · "
        f"{node.agent_name or 'Omnigent agent'} · session {node.session_id or 'not recorded'}"
    )
    st.markdown("**Exact specialist instructions sent to Omnigent**")
    st.code(prompt["instructions"], language=None, wrap_lines=True)
    left, right = st.columns(2)
    with left, st.container(border=True):
        st.markdown("**Requested output → recorded response**")
        schema = prompt.get("output_schema", {})
        st.caption(f"Contract: {schema.get('title', 'unrecorded')}")
        st.caption("Required fields: " + ", ".join(schema.get("required", [])))
        response = saved_json(journal, f"{node.call_id}-response.json")
        if response and isinstance(response.get("raw"), str):
            try:
                value = json.loads(
                    response["raw"].strip().removeprefix("```json").removesuffix("```")
                )
            except ValueError:
                value = {"raw": response["raw"]}
            if isinstance(value, dict):
                for key in ("action", "decision", "experiment", "selected_test_id"):
                    if key in value:
                        st.text(f"{key.replace('_', ' ').capitalize()}: {value[key]}")
                if value.get("invest"):
                    st.text("Invest in: " + ", ".join(value["invest"]))
                if value.get("directions"):
                    st.text(f"Proposed directions: {len(value['directions'])}")
            st.json(value, expanded=False)
        else:
            st.caption("No completed response recorded yet.")
    with right, st.container(border=True):
        st.markdown("**Recorded downstream actions**")
        following = downstream_steps(nodes, node)
        st.caption(
            "Direct dependency handoffs; the supervisor validates responses before dispatch."
            if node.parents is not None
            else "Next recorded step in this legacy sequential workflow."
        )
        for child in following:
            st.text(f"{label(child.role)} · {child.stage} · {child.status}")
            specifications = [a for a in child.artifacts if a.endswith("/specification.json")]
            for artifact in specifications:
                specification = saved_json(journal, artifact)
                if specification:
                    st.caption(
                        f"Executed specification: seed {specification.get('seed')} · "
                        f"{specification.get('trials_per_group')} trials per group"
                    )
                    st.json(specification, expanded=False)
            for event in child.events:
                if event["event"] in {"tool_dispatched", "tool_result"}:
                    st.json({"event": event["event"], **event["data"]}, expanded=False)
        if not following:
            st.caption("No downstream step has been recorded.")
    with st.expander("Complete prompt, inputs and constraints"):
        st.caption(f"{prompt['artifact']} · {prompt['prompt_version']}")
        st.code(prompt["exact_prompt"], language="json", wrap_lines=True, height=360)
    st.download_button(
        "Download exact agent prompt",
        prompt["exact_prompt"],
        file_name=Path(prompt["artifact"]).name,
        mime="application/json",
    )


def render_activity(journal: Journal) -> None:
    st.subheader("Execution state machine")
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
    metrics[1].metric("Specialist roles", len({n.role for n in nodes if n.kind != "simulation"}))
    metrics[2].metric("Local tool executions", sum(n.kind == "simulation" for n in nodes))
    metrics[3].metric("Produced artifacts", len({a for n in nodes for a in n.artifacts}))
    if not sessions:
        st.info(
            "No Omnigent sessions were recorded in this run. "
            "The graph shows the actual backend's steps."
        )
    prompts = {n.key: recorded_prompt(journal, n) for n in nodes}
    st.markdown("**How the agents differ**")
    st.caption(
        "A shared research-worker configuration receives different task prompts and inputs in "
        "each session. The table quotes the opening instruction; select a step for the full prompt."
    )
    st.dataframe(
        [
            {
                "Step": n.stage,
                "Specialist": label(n.role),
                "Prompt opening (verbatim)": p["instructions"].split(". ")[0],
                "Assigned inputs": p["input_scope"],
                "Output contract": p.get("output_schema", {}).get("title", "Unrecorded"),
            }
            for n in nodes
            if (p := prompts[n.key])
        ],
        hide_index=True,
        width="stretch",
        alt="Differences between the actual recorded specialist prompts, inputs and outputs",
    )
    st.caption(
        "Solid arrows are recorded handoffs. Dashed self-loops count repeated uses of a role, "
        "which may be separate sessions or parallel invocations. Diamonds are decision roles."
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
    view = st.segmented_control(
        "Workflow view", ["State machine", "Execution timeline"], default="State machine"
    )
    if view == "Execution timeline":
        with st.container(height=540, border=True):
            st.image(
                graph, width="stretch", alt="Each recorded execution and its actual dependencies"
            )
    else:
        st.graphviz_chart(
            workflow_dot(nodes, node.role),
            width="stretch",
            height="content",
            alt="Recorded agent roles and handoffs with self-loops for repeated invocations",
        )
    render_prompt_actions(journal, nodes, node, prompts)
    with st.expander("Created agents and sessions", expanded=False):
        st.caption(
            "Roles are specialist assignments. Shared agent IDs identify "
            "a reused configuration; session IDs identify actual invocations."
        )
        counts = Counter(n.role for n in nodes)
        st.dataframe(
            [
                {
                    "Role": label(n.role),
                    "Uses of role": counts[n.role],
                    "Agent": n.agent_name or n.kind,
                    "Agent ID": n.agent_id or "Not recorded",
                    "Session": n.session_id or "No session",
                    "Call": n.call_id or "Python tool",
                    "Status": n.status,
                }
                for n in nodes
            ],
            hide_index=True,
            width="stretch",
            alt="Created agent identities, specialist assignments and recorded sessions",
        )
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
        width="stretch",
    )
    st.download_button(
        "Export execution trace",
        activity_export(journal, nodes),
        file_name=f"{journal.run_id}-execution.json",
        mime="application/json",
    )
    st.download_button(
        "Download state machine",
        workflow_dot(nodes, node.role),
        file_name=f"{journal.run_id}-state-machine.dot",
        mime="text/vnd.graphviz",
    )
    st.download_button(
        "Download execution timeline",
        graph,
        file_name=f"{journal.run_id}-graph.svg",
        mime="image/svg+xml",
    )
