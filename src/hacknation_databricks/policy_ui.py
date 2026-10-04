"""Contextual policy controls and evidence from the existing Omnigent workflow."""

from hacknation_databricks.research.activity import load_activity
from hacknation_databricks.research.models import RunConfig
from hacknation_databricks.research_views import recorded_prompt
from hacknation_databricks.web import components as ui

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
    with ui.expander("Omnigent in this step · context and controls"):
        ui.write(CONTEXT[context])
        config = journal.config
        ui.caption(
            f"Recorded run limits: {config.get('max_agent_calls', 'Unrecorded')} agent calls · "
            f"{config.get('max_workers', 'Unrecorded')} workers · "
            f"{config.get('max_simulations', 'Unrecorded')} simulation units. "
            "Enforced by the research supervisor."
        )
        ui.caption(
            "Open Omnigent & policies for session context, enforcement evidence and "
            "next-run controls."
        )


def render_policy_draft():
    # Import locally to keep the shared launcher independent of this view.
    from hacknation_databricks.tracking_ui import run_profiles

    ui.subheader("Policy for the next Omnigent run")
    ui.caption(
        "Save finite resource limits for a launch profile in this app session. "
        "Source intake uses these values; the launched run records them in config.json. "
        "Running and archived runs retain their original limits."
    )
    profile = ui.selectbox("Policy profile", list(run_profiles()), key="policy_profile")
    defaults = run_profiles()[profile].model_dump()
    defaults.update(ui.session_state.get("omnigent_policy_drafts", {}).get(profile, {}))
    defaults["trials"] = min(defaults["trials"], 32)
    fields = [
        ("max_agent_calls", "Agent request budget", 8, 512),
        ("code_timeout_seconds", "Code execution limit per experiment (seconds)", 1, 180),
        ("trials", "Maximum paired replicates", 8, 32),
        ("max_seconds", "Wall-clock limit (seconds)", 60, 21600),
        ("max_simulations", "Simulation budget including replays", 1000, 1000000),
        ("max_rounds", "Maximum experiments", 2, 32),
    ]
    with ui.form(f"policy-draft-{profile}"):
        columns = ui.columns(2)
        draft = {}
        for i, (field, title, minimum, maximum) in enumerate(fields):
            with columns[i % 2]:
                draft[field] = ui.number_input(
                    title, minimum, maximum, defaults[field], key=f"policy-{profile}-{field}"
                )
        ui.caption(
            "These controls configure the Python supervisor around Omnigent sessions. "
            "Repository specialists run sequentially. Source grounding, validated "
            "handoffs and sandbox execution remain required."
        )
        if ui.form_submit_button("Save next-run policy", type="primary"):
            RunConfig.model_validate({**defaults, **draft})
            drafts = dict(ui.session_state.get("omnigent_policy_drafts", {}))
            drafts[profile] = draft
            ui.session_state["omnigent_policy_drafts"] = drafts
            ui.success(
                f"Saved for {profile}. Open Source intake and choose this profile to launch."
            )


def render_policy_evidence(journal):
    ui.subheader("Recorded policy and framework usage")
    ui.caption("Selected run only. Viewing saved evidence makes no model calls.")
    nodes = load_activity(journal)
    calls = [n for n in nodes if n.kind == "omnigent"]
    metrics = ui.columns(3)
    metrics[0].metric(
        "Recorded Omnigent sessions", len({n.session_id for n in calls if n.session_id})
    )
    metrics[1].metric("Validated responses", sum(n.schema_valid is True for n in calls))
    metrics[2].metric("Recorded experiment stages", sum(n.kind == "simulation" for n in nodes))
    ui.dataframe(
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
                    "Validated handoffs, bounded experiments, finite budgets and "
                    "scientific completion gates"
                ),
                "Evidence": "config.json; test_options.json; transition.json; checks.json",
            },
        ],
        hide_index=True,
        width="stretch",
        alt="Framework benefits and policy enforcement owners",
    )
    if journal.report.get("workflow") == "repository":
        ui.caption(
            "Generated Python/C runs through Omnigent's OS sandbox. Each execution.json records "
            "the backend, limits, exit status and output. Model sessions remain separate from "
            "the execution tool; native server policy administration is not claimed."
        )
        from hacknation_databricks.research_views import saved_json

        with ui.expander("Python and C capability and recorded sandbox executions"):
            ui.json(saved_json(journal, "capability.json"))
            for row in journal.report.get("rounds", []):
                execution = saved_json(journal, row["artifact_prefix"] + "/execution.json") or {}
                ui.write(
                    {
                        k: execution.get(k)
                        for k in (
                            "backend",
                            "returncode",
                            "failure",
                            "seconds",
                            "memory_limit_note",
                            "repository_commit",
                            "source_sha256",
                        )
                    }
                )
    else:
        ui.caption(
            "Native Omnigent policy configuration and sandbox enforcement are not attested by "
            "these archives. Shared agent identity and prompts alone do not establish either."
        )
    with ui.expander("Run limits and recorded control policy", expanded=True):
        ui.dataframe(
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
            ui.json(policy, expanded=False)
        else:
            ui.caption("This archive has no separate control-policy record.")
    if not calls:
        ui.info(
            "No Omnigent requests recorded for this run. Framework execution is not established."
        )
        return
    node = ui.selectbox(
        "Specialist policy context",
        calls,
        format_func=lambda n: f"{n.role} · {n.stage} · {n.call_id}",
        key=f"policy-session-{journal.run_id}",
    )
    ui.caption(f"Session: {node.session_id or 'Unrecorded'} · status: {node.status}")
    prompt = recorded_prompt(journal, node)
    if prompt:
        ui.markdown("**Instructions actually sent to this specialist**")
        ui.caption(prompt["input_scope"])
        ui.text(prompt["instructions"])
        with ui.expander("Shared constraints and response contract"):
            ui.text(prompt.get("constraints", "Unrecorded"))
            ui.json(prompt.get("output_schema", {}), expanded=False)
        ui.download_button(
            "Download contextual request",
            prompt["exact_prompt"],
            file_name=f"{node.call_id.rsplit('/', 1)[-1]}-request.json",
            mime="application/json",
        )
    else:
        ui.info("The archived request is unavailable; current instructions are not substituted.")
    with ui.expander("Usage reported by this session"):
        if node.usage:
            ui.json(node.usage)
        else:
            ui.caption("Usage was not reported. Token consumption and cost are unknown.")
    if journal.report.get("checkpoints"):
        from hacknation_databricks.checkpoint_ui import render_checkpoint_story

        with ui.expander("Inspect a policy decision and its actual execution"):
            render_checkpoint_story(journal)
