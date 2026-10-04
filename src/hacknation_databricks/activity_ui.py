"""Visible sessions, real loop iterations, and their inspectable outputs."""

import io
import json
from collections import Counter
from dataclasses import asdict
from pathlib import Path

import pandas as pd

from hacknation_databricks.execution_graph_ui import render_execution_graph
from hacknation_databricks.research.activity import activity_export, load_activity, request_overlap
from hacknation_databricks.research_views import (
    downstream_steps,
    label,
    recorded_prompt,
    saved_json,
    workflow_dot,
)
from hacknation_databricks.tracking import Journal, read_artifact
from hacknation_databricks.web import components as ui


def render_prompt_actions(journal, nodes, node, prompts):
    if node.kind == "anyjev":
        ui.subheader("Decision-only evaluation · AnyJev")
        ui.caption(
            "Closed options scored from model logits; zero generated tokens. "
            "Weights are uncalibrated, not scientific confidence."
        )
        for artifact in node.artifacts:
            if artifact.startswith("decisions/"):
                record = saved_json(journal, artifact)
                ui.json(record, expanded=False)
        handoff = saved_json(journal, node.stage.rsplit("/", 1)[0] + "/anyjev-handoff.json")
        if handoff:
            ui.markdown("**Selected action**")
            ui.json(handoff["selected_action"], expanded=False)
        return
    ui.subheader("Complete prompt, inputs and constraints")
    prompt = prompts.get(node.key)
    if not prompt:
        if node.kind == "simulation":
            ui.info(
                "Python executes this simulation from the approved specification; "
                "it has no agent prompt."
            )
        else:
            ui.info("No saved Omnigent prompt is available for this invocation.")
        return
    ui.caption(f"{label(node.role)} · {prompt['input_scope']}")
    ui.code(prompt["exact_prompt"], language="json", wrap_lines=True, height=360)
    ui.download_button(
        "Download exact agent prompt",
        prompt["exact_prompt"],
        file_name=Path(prompt["artifact"]).name,
        mime="application/json",
    )
    left, right = ui.columns(2)
    with left, ui.container(border=True):
        ui.markdown("**Requested output → recorded response**")
        schema = prompt.get("output_schema", {})
        ui.caption(f"Contract: {schema.get('title', 'unrecorded')}")
        ui.caption("Required fields: " + ", ".join(schema.get("required", [])))
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
                        ui.text(f"{key.replace('_', ' ').capitalize()}: {value[key]}")
                if value.get("invest"):
                    ui.text("Invest in: " + ", ".join(value["invest"]))
                if value.get("directions"):
                    ui.text(f"Proposed directions: {len(value['directions'])}")
            ui.json(value, expanded=False)
        else:
            ui.caption("No completed response recorded yet.")
    handoff = saved_json(journal, node.stage.rsplit("/", 1)[0] + "/anyjev-handoff.json")
    if handoff and node.role == "decision_agent":
        ui.markdown("**AnyJev decision · bounded selection after the Omnigent assessment**")
        ui.json(handoff["selected_action"], expanded=False)
        with ui.expander("AnyJev options, weights and handoff"):
            ui.json(saved_json(journal, handoff["decision_artifact"]), expanded=False)
    with right, ui.container(border=True):
        ui.markdown("**Recorded downstream actions**")
        following = downstream_steps(nodes, node)
        ui.caption(
            "Direct dependency handoffs; the supervisor validates responses before dispatch."
            if node.parents is not None
            else "Next recorded step in this legacy sequential workflow."
        )
        for child in following:
            ui.text(f"{label(child.role)} · {child.stage} · {child.status}")
            specifications = [a for a in child.artifacts if a.endswith("/specification.json")]
            for artifact in specifications:
                specification = saved_json(journal, artifact)
                if specification:
                    ui.caption(
                        f"Executed specification: seed {specification.get('seed')} · "
                        f"{specification.get('trials_per_group')} trials per group"
                    )
                    ui.json(specification, expanded=False)
            for event in child.events:
                if event["event"] in {"tool_dispatched", "tool_result"}:
                    ui.json({"event": event["event"], **event["data"]}, expanded=False)
        if not following:
            ui.caption("No downstream step has been recorded.")


def render_artifacts(journal, artifacts):
    ui.markdown("**Saved artifacts**")
    if not artifacts:
        ui.caption("No files saved for this step yet.")
        return
    artifact = ui.pills(
        "Step artifact", artifacts, default=artifacts[0], label_visibility="collapsed"
    )
    if artifact is None:
        return
    try:
        raw = read_artifact(journal.directory, artifact)
        if artifact.endswith(".json"):
            ui.json(json.loads(raw), expanded=False)
        elif artifact.endswith((".csv", ".parquet")):
            frame = (
                pd.read_parquet(io.BytesIO(raw))
                if artifact.endswith(".parquet")
                else pd.read_csv(io.BytesIO(raw))
            )
            ui.caption(
                f"{len(frame):,} rows · {len(frame.columns)} columns · {Path(artifact).suffix}"
            )
            ui.dataframe(frame.head(100), hide_index=True, alt="First 100 saved simulation rows")
            if artifact.endswith(".csv"):
                ui.download_button(
                    "Download as Parquet",
                    frame.to_parquet(index=False),
                    file_name=Path(artifact).with_suffix(".parquet").name,
                    mime="application/octet-stream",
                )
                ui.caption("Parquet is a derived export of the complete saved CSV.")
        else:
            ui.code(raw[:20000].decode("utf-8", errors="replace"), language=None)
            if len(raw) > 20000:
                ui.caption("Preview limited to 20 KB; download includes the complete file.")
        ui.download_button(
            "Download step artifact", raw, file_name=Path(artifact).name, key="activity_artifact"
        )
    except (OSError, ValueError):
        ui.warning("Artifact is not yet readable. Refresh the run.")


def render_simulation(journal, node):
    ui.caption("Experiment implementation bound to this run's source paper.")
    if getattr(node, "stage", "").startswith("preflight/"):
        prefix = node.stage.rsplit("/", 1)[0]
        implementation = saved_json(journal, prefix + "/implementation.json")
        manifest = saved_json(journal, "repository/manifest.json")
        seed = next((s for s in journal.sources if s.get("source_id") == "seed"), {})
        if not manifest or manifest.get("source_sha256") != seed.get("sha256"):
            ui.error("Implementation source does not match this paper.")
            return
        ui.caption("Feasibility check only; this attempt is not an accepted research comparison.")
        if implementation:
            for key, language in [("python_code", "python"), ("c_code", "c")]:
                if implementation.get(key):
                    ui.code(implementation[key], language=language, height=360)
        render_artifacts(journal, node.artifacts)
        return
    manifest_name = (
        "code/provenance.json"
        if (journal.directory / "code/provenance.json").is_file()
        else "implementation.json"
    )
    manifest_path = journal.directory / manifest_name
    code = []
    if manifest_path.is_file():
        implementation = json.loads(read_artifact(journal.directory, manifest_name))
        seed = next((s for s in journal.sources if s.get("source_id") == "seed"), {})
        if implementation.get("source_sha256") != seed.get("sha256"):
            ui.error("Implementation source does not match this paper.")
            return
        code = implementation.get("files", [])
    with ui.expander("Paper-specific simulation implementation", expanded=True):
        if code:
            selected = ui.segmented_control("Archived implementation", code, default=code[0])
            if selected is None:
                selected = code[0]
            raw = read_artifact(journal.directory, selected)
            ui.code(raw.decode("utf-8"), language="python", height=360)
            ui.download_button("Download simulation code", raw, file_name=Path(selected).name)
        else:
            ui.info(
                "This historical run has no source-bound implementation manifest. Its shared "
                "framework snapshot remains in Generated artifacts; it is not presented as "
                "paper-specific simulation code."
            )
    render_artifacts(journal, node.artifacts)


def render_artifact_feed(journal: Journal) -> None:
    """Show files produced by this run, including files written before sealing."""
    paths = [
        p
        for p in journal.directory.rglob("*")
        if p.is_file()
        and not p.is_symlink()
        and p.suffix in {".json", ".csv", ".svg", ".txt"}
        and p.relative_to(journal.directory).parts[0] not in {"inputs", "code"}
        and not any(part.startswith(".") for part in p.relative_to(journal.directory).parts)
    ]
    paths.sort(key=lambda p: p.stat().st_mtime_ns, reverse=True)
    refresh_note = "saved run" if journal.sealed else "refreshed every five seconds"
    ui.caption(f"{len(paths)} produced artifacts · {refresh_note}")
    with ui.expander("Latest artifacts", expanded=not journal.sealed):
        if paths:
            names = [p.relative_to(journal.directory).as_posix() for p in paths]
            ui.dataframe(
                [
                    {"Artifact": n, "Bytes": p.stat().st_size}
                    for n, p in zip(names[:8], paths[:8], strict=True)
                ],
                hide_index=True,
                width="stretch",
                alt="Most recently produced run artifacts",
            )
            name = ui.selectbox(
                "Inspect produced artifact", names, key=f"live-file-{journal.run_id}"
            )
            ui.download_button(
                "Download produced artifact",
                read_artifact(journal.directory, name),
                file_name=name.replace("/", "-"),
                key=f"live-download-{journal.run_id}",
            )
        else:
            ui.caption("Waiting for the first artifact from this run.")


def recorded_failure(journal, node):
    """Explain saved failures without rerunning or rewriting the archived attempt."""
    contract = saved_json(journal, node.stage + "_contract_failure.json")
    if node.error_type == "ValidationError" and contract:
        errors = contract.get("errors", [])
        details = "; ".join(
            f"{'.'.join(map(str, e.get('loc', [])))}: {e.get('msg', e.get('type', 'invalid'))}"
            for e in errors
        )
        return f"The agent response failed its saved output contract: {details}. " + (
            "A later correction completed this stage; this rejected attempt remains in the audit."
            if node.stage_status == "completed"
            else "This attempt is preserved; updating the code does not rerun saved failures."
        )
    execution = saved_json(journal, node.stage.rsplit("/", 1)[0] + "/execution.json")
    if (
        node.kind == "simulation"
        and execution
        and (
            "Baseline preflight failed" in execution.get("stderr", "")
            or "Identical seeded baseline did not replay exactly"
            in journal.report.get("reason", "")
        )
    ):
        return (
            "Identical seeded simulation outputs differed, so the result was rejected. "
            "Measurements and scene data must replay exactly. Wall-clock timing belongs in "
            "execution metadata, not the scientific output. See saved trials or execution details."
        )
    if node.kind == "simulation" and execution and execution.get("failure") == "timeout":
        return (
            "The simulation exceeded its execution or remaining run time budget. "
            "No accepted result was produced; this failed attempt remains saved."
        )
    return f"This step stopped ({node.error_type}). See Technical details for recorded events."


def render_activity(journal: Journal) -> None:
    nodes = load_activity(journal)
    if not nodes:
        ui.info("No stage has started yet. Agent sessions appear after Omnigent creates them.")
        return
    overlap = request_overlap(nodes)
    cols = ui.columns(3)
    cols[0].metric("Active specialist requests", overlap["live"])
    cols[1].metric("Peak concurrent requests", overlap["peak"])
    cols[2].metric("Time with concurrent work", f"{overlap['overlap_seconds']:.1f}s")
    ui.caption(
        "Measured from recorded Omnigent request start/end events, including runtime waits. "
        "Branches sharing a graph level have independent inputs; counts above show actual overlap."
    )
    ui.caption("Click a box to view its prompt, inputs and results.")
    node, graph = render_execution_graph(nodes, journal)
    prompts = {node.key: recorded_prompt(journal, node)}
    if node.error_type == "ConnectError":
        ui.error(
            "Could not connect to Omnigent. The paper remains saved, but this attempt "
            "could not reach the worker runtime. Restore the server and host, then start "
            "a new run from Source intake. This attempt is preserved."
        )
    elif node.error_type:
        ui.error(recorded_failure(journal, node))
    if node.stage_status == "failed" and node.status == "completed":
        ui.warning("The worker responded, but a later evidence check in this stage failed.")
    if node.kind == "simulation":
        render_simulation(journal, node)
    else:
        render_prompt_actions(journal, nodes, node, prompts)
        with ui.expander("Saved step artifacts"):
            render_artifacts(journal, node.artifacts)
    with ui.expander("Technical details · session, validation and events"):
        ui.json({k: v for k, v in asdict(node).items() if k not in {"artifacts", "events"}})
        if prompt := prompts.get(node.key):
            ui.caption(f"{prompt['artifact']} · {prompt['prompt_version']}")
        ui.json(node.events, expanded=False)
    with ui.expander("Run details and exports"):
        render_execution_audit(journal, nodes, node, graph)


def render_execution_audit(journal, nodes, node, graph):
    ui.text(f"Run: {journal.run_id}")
    ui.caption(
        f"{journal.report.get('backend', 'unknown').upper()} · "
        f"{journal.report.get('status', 'running').replace('_', ' ')} · "
        f"{'Artifacts verified' if journal.verified else 'Unsealed live snapshot'}"
    )
    sessions = {n.session_id for n in nodes if n.session_id}
    metrics = ui.columns(4)
    metrics[0].metric("Omnigent sessions", len(sessions))
    metrics[1].metric("Specialist roles", len({n.role for n in nodes if n.kind != "simulation"}))
    metrics[2].metric("Local tool executions", sum(n.kind == "simulation" for n in nodes))
    metrics[3].metric("Produced artifacts", len({a for n in nodes for a in n.artifacts}))
    ui.caption("Session IDs identify actual invocations; shared agent IDs identify configuration.")
    counts = Counter(n.role for n in nodes)
    ui.dataframe(
        [
            {
                "Step": n.stage,
                "Role": label(n.role),
                "Uses of role": counts[n.role],
                "Agent": n.agent_name or n.kind,
                "Agent ID": n.agent_id or "Not recorded",
                "Backend": n.kind,
                "Session": n.session_id or "—",
                "Call": n.call_id or "Python tool",
                "Status": n.status,
                "Seconds": n.seconds,
                "Artifacts": len(n.artifacts),
            }
            for n in nodes
        ],
        hide_index=True,
        width="stretch",
        alt="Recorded execution steps, agent sessions, timing and artifact counts",
    )
    ui.caption(
        "Solid arrows are recorded handoffs. Dashed self-loops count repeated uses of a role; "
        "diamonds are decision roles."
    )
    ui.graphviz_chart(
        workflow_dot(nodes, node.role),
        width="stretch",
        height="content",
        alt="Recorded agent roles and handoffs with self-loops for repeated invocations",
    )
    ui.download_button(
        "Export execution trace",
        activity_export(journal, nodes),
        file_name=f"{journal.run_id}-execution.json",
        mime="application/json",
    )
    ui.download_button(
        "Download state machine",
        workflow_dot(nodes, node.role),
        file_name=f"{journal.run_id}-state-machine.dot",
        mime="text/vnd.graphviz",
    )
    ui.download_button(
        "Download execution timeline",
        graph,
        file_name=f"{journal.run_id}-graph.svg",
        mime="image/svg+xml",
    )
