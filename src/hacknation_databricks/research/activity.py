"""Project recorded execution into a graph; never invent sessions or future rounds."""

import json
from dataclasses import asdict, dataclass, field
from html import escape

from hacknation_databricks.tracking import Journal, read_artifact


@dataclass
class Activity:
    stage: str
    role: str
    round: int
    kind: str
    started_at: str
    status: str = "running"
    stage_status: str = "running"
    call_status: str | None = None
    finished_at: str | None = None
    seconds: float | None = None
    session_id: str | None = None
    agent_id: str | None = None
    agent_name: str | None = None
    runner_id: str | None = None
    call_id: str | None = None
    error_type: str | None = None
    usage: dict | None = None
    schema_valid: bool | None = None
    artifacts: list[str] = field(default_factory=list)
    events: list[dict] = field(default_factory=list)

    @property
    def key(self) -> str:
        return f"{self.stage}:{self.call_id or self.kind}"


def load_activity(journal: Journal) -> list[Activity]:
    if journal.issues:
        return []
    events = [
        json.loads(line)
        for line in read_artifact(journal.directory, "events.jsonl").splitlines()
        if line.strip()
    ]
    backend = journal.report.get("backend", "unknown")
    nodes: list[Activity] = []
    active = None
    role_count = 0
    for event in events:
        kind, data = event["event"], event["data"]
        if kind == "stage_started":
            stage = data["stage"]
            role = stage.rsplit("/", 1)[-1]
            worker_kind = "simulation" if role in {"baseline", "experiment"} else backend
            active = Activity(
                stage,
                "validator" if role == "validation" else role,
                int(stage.split("/")[1]) if "/" in stage else 0,
                worker_kind,
                event["time"],
            )
            if worker_kind != "simulation":
                role_count += 1
                # Legacy artifacts predate the lifecycle events but retain call ordering.
                active.call_id = f"roles/{role_count:02d}-{active.role}"
            nodes.append(active)
        if active is None or data.get("stage", active.stage) != active.stage:
            continue
        if kind == "agent_call_started":
            if any(e["event"] == "agent_call_started" for e in active.events):
                active = Activity(active.stage, data["role"], active.round, backend, event["time"])
                nodes.append(active)
                role_count += 1
            active.role = data["role"]
            active.call_id = data["call_id"]
            active.call_status = "running"
        active.events.append(event)
        if kind in {"agent_session_created", "agent_session", "agent_call_completed"}:
            for key in (
                "session_id",
                "agent_id",
                "agent_name",
                "runner_id",
                "call_id",
                "usage",
                "schema_valid",
            ):
                if key in data:
                    setattr(active, key, data[key])
        if kind == "agent_call_failed":
            active.error_type = data.get("error_type")
        if kind in {"agent_call_completed", "agent_call_failed"}:
            active.status = "completed" if kind == "agent_call_completed" else "failed"
            active.call_status = active.status
            active.finished_at = event["time"]
            active.seconds = data.get("seconds")
        if kind == "artifact_written" and data["path"] not in active.artifacts:
            active.artifacts.append(data["path"])
        if kind in {"stage_completed", "stage_failed"}:
            for node in nodes:
                if node.stage != active.stage:
                    continue
                node.stage_status = "completed" if kind == "stage_completed" else "failed"
                if node.call_status is None or node.call_status == "running":
                    node.status = node.stage_status
                    node.finished_at = event["time"]
                    node.seconds = data.get("seconds")
                    node.error_type = data.get("error_type", node.error_type)
            active = None
    recorded_artifacts = set(journal.artifacts)
    recorded_artifacts.update(e["data"]["path"] for e in events if e["event"] == "artifact_written")
    for node in nodes:
        # Backward-compatible projection of saved output files, never planned output names.
        record = next((d for d in journal.decisions if d.stage == node.stage), None)
        names = set(node.artifacts)
        if record and sum(n.stage == node.stage for n in nodes) == 1:
            names.update(record.evidence)
        if node.call_id:
            names.update(
                name
                for name in recorded_artifacts
                if name == node.call_id + ".json" or name.startswith(node.call_id + "-")
            )
        node.artifacts = sorted(
            name
            for name in names
            if (not journal.sealed or name in journal.artifacts)
            and name not in {"sources.json", "config.json", "report.json"}
            and (
                not name.startswith("roles/")
                or name == node.call_id + ".json"
                or name.startswith(node.call_id + "-")
            )
        )
        if node.status == "running" and journal.sealed:
            node.status = "interrupted"
    return nodes


def activity_export(journal: Journal, nodes: list[Activity]) -> str:
    return (
        json.dumps(
            {
                "run_id": journal.run_id,
                "backend": journal.report.get("backend"),
                "verified": journal.verified,
                "activities": [asdict(n) for n in nodes],
            },
            indent=2,
        )
        + "\n"
    )


def activity_dot(nodes: list[Activity], selected_stage: str | None = None) -> str:
    """DOT labels are escaped, and edges exist only for stages that actually started."""
    lines = [
        "digraph execution {",
        "rankdir=TB;",
        'bgcolor="transparent";',
        'graph [pad="0.25", nodesep="0.35", ranksep="0.6"];',
        'node [shape=box, style="rounded,filled", fontname="Arial", fontsize=11];',
        'edge [color="#95a6b0", fontname="Arial", fontsize=9];',
        'controller [label="Research workflow\\nRecorded execution", '
        'fillcolor="#183640", fontcolor="white"];',
    ]
    colors = {
        "completed": "#dff2eb",
        "failed": "#ffe4de",
        "running": "#e5edff",
        "interrupted": "#fff0d5",
    }
    for round_index in dict.fromkeys(n.round for n in nodes):
        lines.append(f"subgraph cluster_{round_index} {{")
        lines.append("rank=same;")
        lines.append(
            "label="
            + json.dumps(f"Round {round_index}" if round_index else "Read, critique & baseline")
            + '; color="#d8e2e7";'
        )
        for i, node in enumerate(nodes):
            if node.round != round_index:
                continue
            identity = (
                "Omnigent session"
                if node.session_id
                else {
                    "simulation": "Python simulation",
                    "omnigent": "Omnigent request",
                    "anyjev": "AnyJev decision",
                    "fixture": "Test fixture",
                    "scripted": "Scripted role",
                }.get(node.kind, "Recorded role")
            )
            label = (
                f"{node.role.capitalize()}\n{identity}\n"
                f"{node.status} · {len(node.artifacts)} artifacts"
            )
            lines.append(
                f"n{i} [label={json.dumps(label, ensure_ascii=False)}, "
                f'fillcolor="{colors[node.status]}", '
                f'color="{"#087e80" if node.key == selected_stage else "#b8cbd2"}", '
                f"penwidth={3 if node.key == selected_stage else 1}, "
                f"tooltip={json.dumps(node.session_id or node.stage)}];"
            )
        lines.append("}")
    for i, node in enumerate(nodes):
        previous = f"n{i - 1}" if i else "controller"
        repeated = i and node.round > nodes[i - 1].round and nodes[i - 1].round > 0
        if repeated:
            lines.append(
                f'n{i - 1} -> n{i} [color="#087e80", label="repeat recorded", penwidth=2];'
            )
        else:
            lines.append(f"{previous} -> n{i};")
        if node.session_id:
            lines.append(f'controller -> n{i} [style=dotted, constraint=false, label="session"];')
    lines.append("}")
    return "\n".join(lines)


def activity_svg(nodes: list[Activity], selected_key: str | None = None) -> str:
    """Responsive rows keep every executed round legible, even on long traces."""
    groups = []
    for round_index in dict.fromkeys(n.round for n in nodes):
        members = [n for n in nodes if n.round == round_index]
        groups.extend((round_index, members[i : i + 5]) for i in range(0, len(members), 5))
    height = 95 + 160 * len(groups)
    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1120 {height}" '
        'role="img" aria-label="Recorded agent executions grouped by round" '
        'style="width:100%;height:auto;display:block;font-family:Arial,sans-serif">',
        '<defs><marker id="arrow" markerWidth="7" markerHeight="7" refX="6" refY="3.5" '
        'orient="auto"><path d="M0,0 L7,3.5 L0,7" fill="#829aa5"/></marker></defs>',
        '<rect x="410" y="6" width="300" height="49" rx="10" fill="#183640"/>',
        '<text x="560" y="28" text-anchor="middle" fill="white" font-size="15" '
        'font-weight="600">Research workflow</text>',
        '<text x="560" y="44" text-anchor="middle" fill="#b8d3da" font-size="11">'
        "Recorded work only</text>",
    ]
    prior = None
    for row, (round_index, members) in enumerate(groups):
        y = 86 + row * 160
        first_x = (1120 - (len(members) * 186 + (len(members) - 1) * 30)) / 2
        title = f"Round {round_index}" if round_index else "Read, critique & baseline"
        svg.extend(
            [
                f'<rect x="9" y="{y}" width="1102" height="137" rx="12" '
                'fill="#f0f5f7" stroke="#dce6eb"/>',
                f'<text x="26" y="{y + 22}" fill="#516b76" font-size="12" '
                f'font-weight="600">{escape(title)}</text>',
            ]
        )
        if prior:
            px, py, previous_round = prior
            label = (
                "Repeat recorded" if round_index > previous_round and previous_round else "Continue"
            )
            svg.append(
                f'<path d="M{px},{py} V{y - 14} H{first_x + 93} V{y + 42}" '
                'fill="none" stroke="#829aa5" stroke-width="1.5" marker-end="url(#arrow)"/>'
            )
            svg.append(
                f'<text x="{min(px, first_x + 93) + 8}" y="{y - 18}" '
                f'font-size="10" fill="#087e80">{label}</text>'
            )
        else:
            svg.append(
                f'<path d="M560,55 V72 H{first_x + 93} V{y + 42}" fill="none" '
                'stroke="#829aa5" stroke-width="1.5" marker-end="url(#arrow)"/>'
            )
        for index, node in enumerate(members):
            x = first_x + index * 216
            fill = {"failed": "#fff0ec", "running": "#edf2ff", "interrupted": "#fff6df"}.get(
                node.status, "#ffffff"
            )
            color = "#087e80" if node.key == selected_key else "#cbdce2"
            kind = (
                "Omnigent session"
                if node.session_id
                else {
                    "anyjev": "AnyJev local inference",
                    "simulation": "Python simulation",
                    "fixture": "Test fixture",
                    "scripted": "Scripted role",
                    "omnigent": "Omnigent request",
                }.get(node.kind, "Recorded execution")
            )
            title = node.role.replace("_", " ").capitalize()
            svg.extend(
                [
                    f"<g><title>{escape(node.session_id or node.stage)}</title>",
                    f'<rect x="{x}" y="{y + 43}" width="186" height="78" rx="9" '
                    f'fill="{fill}" stroke="{color}" '
                    f'stroke-width="{2.5 if node.key == selected_key else 1}"/>',
                    f'<text x="{x + 13}" y="{y + 65}" fill="#183640" font-size="14" '
                    f'font-weight="600">{escape(title)}</text>',
                    f'<text x="{x + 13}" y="{y + 84}" fill="#087e80" font-size="11">{kind}</text>',
                    f'<text x="{x + 13}" y="{y + 105}" fill="#607984" font-size="11">'
                    f"{escape(node.status)} · {len(node.artifacts)} artifacts</text></g>",
                ]
            )
            if index:
                svg.append(
                    f'<path d="M{x - 28},{y + 82} H{x - 4}" fill="none" '
                    'stroke="#829aa5" stroke-width="1.5" marker-end="url(#arrow)"/>'
                )
        prior = (first_x + (len(members) - 1) * 216 + 93, y + 121, round_index)
    svg.append("</svg>")
    return "".join(svg)
