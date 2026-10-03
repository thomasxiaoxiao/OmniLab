"""Contextual policy controls and evidence from the existing Omnigent workflow."""

import streamlit as st

from hacknation_databricks.research.activity import load_activity
from hacknation_databricks.research.models import RunConfig
from hacknation_databricks.research_views import recorded_prompt

CONTEXT = {
    "Research": (
        "Omnigent specialists turn source evidence into structured decisions; the"
        " supervisor checks those decisions before executing experiments."
    ),
    "Agents": (
        "Omnigent provides separate specialist sessions and streamed responses. "
        "Recorded session IDs connect each instruction to its response and "
        "downstream work."
    ),
    "Comparison": (
        "Omnigent chooses follow-up tests and interprets results. Seeded Python "
        "tools compute the measurements and uncertainty shown here."
    ),
    "Synthesis": (
        "Omnigent reviewers assess the result and recommend the next "
        "investigation. Numerical gates and independent review control "
        "acceptance."
    ),
    "Evidence": (
        "Omnigent session identities and reported usage are retained alongside "
        "prompts and responses. The local artifact manifest verifies saved "
        "evidence."
    ),
}


def render_policy_context(journal, context="Research"):
    if journal.report.get("backend") != "omnigent":
        return
    with st.expander("Omnigent in this step · context and controls"):
        st.write(CONTEXT[context])
        config = journal.config
        st.caption(
            f"Recorded run limits: {config.get('max_agent_calls', 'Unrecorded')} agent calls · "
            f"{config.get('max_workers', 'Unrecorded')} workers · "
            f"{config.get('max_simulations', 'Unrecorded')} simulation units. "
            "Enforced by the research supervisor."
        )
        st.caption(
            "Open Omnigent & policies for session context, enforcement evidence and "
            "next-run controls."
        )


def render_policy_draft():
    # Import locally to keep the shared launcher independent of this view.
    from hacknation_databricks.tracking_ui import run_profiles

    st.subheader("Policy for the next Omnigent run")
    st.caption(
        "Save finite resource limits for a launch profile in this app session. "
        "Source intake uses these values; the launched run records them in config.json. "
        "Running and archived runs retain their original limits."
    )
    profile = st.selectbox("Policy profile", list(run_profiles()), key="policy_profile")
    defaults = run_profiles()[profile].model_dump()
    defaults.update(st.session_state.get("omnigent_policy_drafts", {}).get(profile, {}))
    fields = [
        ("max_agent_calls", "Agent request budget", 8, 512),
        ("max_workers", "Concurrent workers / agents", 1, 16),
        ("max_seconds", "Wall-clock limit (seconds)", 60, 21600),
        ("max_simulations", "Simulation budget including replays", 1000, 1000000),
        ("max_rounds", "Maximum batches per direction", 2, 32),
    ]
    with st.form(f"policy-draft-{profile}"):
        columns = st.columns(2)
        draft = {}
        for i, (field, title, minimum, maximum) in enumerate(fields):
            with columns[i % 2]:
                draft[field] = st.number_input(
                    title, minimum, maximum, defaults[field], key=f"policy-{profile}-{field}"
                )
        st.caption(
            "These controls configure the Python supervisor around Omnigent sessions. "
            "Source grounding, schema validation and the experiment allowlist remain required."
        )
        if st.form_submit_button("Save next-run policy", type="primary"):
            RunConfig.model_validate({**defaults, **draft})
            drafts = dict(st.session_state.get("omnigent_policy_drafts", {}))
            drafts[profile] = draft
            st.session_state["omnigent_policy_drafts"] = drafts
            st.success(
                f"Saved for {profile}. Open Source intake and choose this profile to launch."
            )


def render_policy_evidence(journal):
    st.subheader("Recorded policy and framework usage")
    st.caption("Selected run only. Viewing saved evidence makes no model calls.")
    nodes = load_activity(journal)
    calls = [n for n in nodes if n.kind == "omnigent"]
    metrics = st.columns(3)
    metrics[0].metric(
        "Recorded Omnigent sessions", len({n.session_id for n in calls if n.session_id})
    )
    metrics[1].metric("Validated responses", sum(n.schema_valid is True for n in calls))
    metrics[2].metric("Recorded experiment stages", sum(n.kind == "simulation" for n in nodes))
    st.dataframe(
        [
            {
                "Layer": "Omnigent framework",
                "Benefit": (
                    "Specialist sessions, registered agent identity, streamed responses and "
                    "runner lifecycle"
                ),
                "Evidence": "events.jsonl; roles/*-response.json",
            },
            {
                "Layer": "Contextual instructions",
                "Benefit": "Role-specific task, source/branch context and structured output schema",
                "Evidence": "roles/*-request.json; instructions are not permission enforcement",
            },
            {
                "Layer": "Research supervisor",
                "Benefit": (
                    "Validated handoffs, allowlisted experiments, finite budgets and "
                    "scientific completion gates"
                ),
                "Evidence": "config.json; test_options.json; transition.json; checks.json",
            },
        ],
        hide_index=True,
        width="stretch",
        alt="Framework benefits and policy enforcement owners",
    )
    st.caption(
        "Native Omnigent policy configuration and sandbox enforcement are not attested by these "
        "archives. Shared agent identity and prompt instructions alone do not establish either."
    )
    with st.expander("Run limits and recorded control policy", expanded=True):
        st.dataframe(
            [
                {
                    "Control": key.replace("_", " "),
                    "Saved value": str(journal.config.get(key, "Unrecorded")),
                }
                for key in (
                    "max_agent_calls",
                    "max_agent_retries",
                    "agent_timeout_seconds",
                    "max_workers",
                    "max_seconds",
                    "max_simulations",
                    "max_rounds",
                )
            ],
            hide_index=True,
            width="stretch",
            alt="Immutable configured limits for the selected run",
        )
        policy = journal.report.get("control_policy")
        if policy:
            st.json(policy, expanded=False)
        else:
            st.caption("This archive has no separate control-policy record.")
    if not calls:
        st.info(
            "No Omnigent requests recorded for this run. Framework execution is not established."
        )
        return
    node = st.selectbox(
        "Specialist policy context",
        calls,
        format_func=lambda n: f"{n.role} · {n.stage} · {n.call_id}",
        key=f"policy-session-{journal.run_id}",
    )
    st.caption(f"Session: {node.session_id or 'Unrecorded'} · status: {node.status}")
    prompt = recorded_prompt(journal, node)
    if prompt:
        st.markdown("**Instructions actually sent to this specialist**")
        st.caption(prompt["input_scope"])
        st.text(prompt["instructions"])
        with st.expander("Shared constraints and response contract"):
            st.text(prompt.get("constraints", "Unrecorded"))
            st.json(prompt.get("output_schema", {}), expanded=False)
        st.download_button(
            "Download contextual request",
            prompt["exact_prompt"],
            file_name=f"{node.call_id.rsplit('/', 1)[-1]}-request.json",
            mime="application/json",
        )
    else:
        st.info("The archived request is unavailable; current instructions are not substituted.")
    with st.expander("Usage reported by this session"):
        if node.usage:
            st.json(node.usage)
        else:
            st.caption("Usage was not reported. Token consumption and cost are unknown.")
    if journal.report.get("checkpoints"):
        from hacknation_databricks.checkpoint_ui import render_checkpoint_story

        with st.expander("Inspect a policy decision and its actual execution"):
            render_checkpoint_story(journal)
