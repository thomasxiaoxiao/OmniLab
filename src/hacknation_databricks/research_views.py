"""Read-only projections for the lab: recorded executions, datasets and paper evidence."""

import json
import textwrap
from collections import Counter, defaultdict
from itertools import combinations

from hacknation_databricks.research.activity import Activity
from hacknation_databricks.research.comparison import synthesis_dataset as synthesis_dataset
from hacknation_databricks.tracking import Journal, read_artifact

ROLE_LABELS = {
    "researcher": "Paper researcher",
    "reader": "Reader",
    "consolidator": "Critic / consolidator",
    "critic": "Critic",
    "branch_planner": "Experiment planner",
    "planner": "Planner",
    "experiment": "Local simulation",
    "baseline": "Baseline check",
    "decision_agent": "Evaluate direction",
    "validator": "Independent evaluator",
    "novelty_evaluator": "Reference evaluator",
    "next_decision": "Next decision",
    "literature": "Literature researcher",
}


def label(role: str) -> str:
    return ROLE_LABELS.get(role, role.replace("_", " ").capitalize())


def dot_label(value: str, width: int = 34) -> str:
    return json.dumps("\n".join(textwrap.wrap(value, width)), ensure_ascii=False)


def workflow_dot(nodes: list[Activity], selected_role: str | None = None) -> str:
    """Collapse execution instances by role; repeated use is distinct from a handoff."""
    groups = defaultdict(list)
    for node in nodes:
        groups[(node.kind, node.role)].append(node)
    ids = {key: f"r{i}" for i, key in enumerate(groups)}
    edges = Counter()
    by_key, prior_stage = {}, {}
    for i, node in enumerate(nodes):
        target = ids[(node.kind, node.role)]
        parents = node.parents if node.parents is not None else ([nodes[i - 1].key] if i else [])
        for parent in parents:
            parent_node = by_key.get(parent) or prior_stage.get(parent)
            if parent_node:
                origin = ids[(parent_node.kind, parent_node.role)]
                if origin != target:
                    edges[(origin, target)] += 1
        by_key[node.key], prior_stage[node.stage] = node, node
    lines = [
        'digraph workflow { rankdir=LR; bgcolor="transparent";',
        'graph [pad="0.4", nodesep="0.35", ranksep="0.35", fontname="Arial"];',
        'node [shape=box, style="rounded,filled", fillcolor="white", color="#cbd5e1", '
        'fontname="Arial", fontsize=16, margin="0.15,0.12", penwidth=1.5];',
        'edge [color="#94a3b8", arrowsize=0.7, fontname="Arial", fontsize=12];',
    ]
    for (kind, role), members in groups.items():
        identifier = ids[(kind, role)]
        counts = Counter(n.status for n in members)
        color = (
            "#d97706"
            if counts["failed"] or counts["interrupted"]
            else "#2563eb"
            if counts["running"]
            else "#0f766e"
        )
        status = " · ".join(f"{n} {s}" for s, n in counts.items())
        identity = "Python tool" if kind == "simulation" else f"{kind.capitalize()} role"
        shape = (
            "diamond"
            if role in {"decision_agent", "next_decision", "critic", "consolidator"}
            else "box"
        )
        short = {
            "consolidator": "Critique",
            "decision_agent": "Evaluate",
            "next_decision": "Decide next",
        }.get(role, label(role))
        value = "\n".join(textwrap.wrap(short, 16)) + f"\n{status}"
        lines.append(
            f"{identifier} [label={json.dumps(value, ensure_ascii=False)}, "
            f'shape={shape}, color="{color}", '
            f'fillcolor="{"#ecfdf5" if role == selected_role else "#ffffff"}", '
            f"penwidth={3 if role == selected_role else 1.5}, tooltip={json.dumps(identity)}];"
        )
        if len(members) > 1:
            lines.append(
                f'{identifier} -> {identifier} [label="used {len(members)} times", '
                'style=dashed, color="#7c3aed", fontcolor="#7c3aed", constraint=false];'
            )
    for (origin, target), count in edges.items():
        lines.append(f'{origin} -> {target} [label="{count} handoff{"s" if count != 1 else ""}"];')
    return "\n".join([*lines, "}"])


def latest_datasets(report: dict) -> list[dict]:
    """Each adaptive checkpoint is cumulative. Never sum overlapping snapshots."""
    selected = {}
    for item in report.get("rounds", []):
        selected[item.get("branch_id", "follow-up")] = item
    return list(selected.values())


def measurement_rows(dataset: dict) -> list[dict]:
    rows = []
    for check in dataset.get("effect", {}).get("checks", []):
        interval = check.get("difference_interval")
        if interval is None and check.get("control_interval") and check.get("treatment_interval"):
            interval = [
                check["treatment_interval"][0] - check["control_interval"][1],
                check["treatment_interval"][1] - check["control_interval"][0],
            ]
        row = {
            "Scenario": str(check.get("scenario", check.get("size", "All"))),
            "Original / control": check["control"],
            "Follow-up": check["treatment"],
            "Difference": check["difference"],
            "Lower": interval[0] if interval else None,
            "Upper": interval[1] if interval else None,
            "Control samples": check.get("control_samples", dataset.get("trials_per_size")),
            "Follow-up samples": check.get("treatment_samples", dataset.get("trials_per_size")),
            "Conclusion": check.get(
                "conclusion", "threshold met" if check.get("passed") else "inconclusive"
            ),
        }
        if "false_alert_rate" in check:
            row["Control false alerts"] = check["control_false_alert_rate"]
            row["Follow-up false alerts"] = check["false_alert_rate"]
        rows.append(row)
    return rows


def dataset_artifacts(journal: Journal, dataset: dict) -> list[str]:
    """Return trial files belonging to this snapshot, not later or other-branch data."""
    if "branch_id" in dataset:
        prefix = f"branches/{dataset['branch_id']}/batches/"
        return sorted(
            name
            for name in journal.artifacts
            if name.startswith(prefix)
            and name.endswith("/trials.csv")
            and int(name[len(prefix) :].split("/")[0]) <= dataset["batch"]
        )
    return [
        name
        for name in ["baseline/trials.csv", f"rounds/{dataset['round']:02d}/trials.csv"]
        if name in journal.artifacts
    ]


def saved_json(journal: Journal, name: str):
    if journal.sealed and name not in journal.artifacts:
        return None
    if not (journal.directory / name).is_file():
        return None
    return json.loads(read_artifact(journal.directory, name))


def paper_evidence(journal: Journal) -> list[dict]:
    """Extract explicit quote references only; a retrieved paper is not assumed reviewed."""
    found = []

    def walk(value, artifact, concept="Recorded evidence"):
        if isinstance(value, list):
            for item in value:
                walk(item, artifact, concept)
        elif isinstance(value, dict):
            concept = value.get("title") or value.get("original_work") or concept
            if {"source_id", "page", "quote"} <= value.keys():
                found.append({**value, "concept": concept, "artifact": artifact})
            else:
                for item in value.values():
                    walk(item, artifact, concept)

    walk(journal.proposals, "proposals.json")
    walk(journal.report.get("automated_review", {}), "report.json")
    names = ["research_briefs.json", "consolidation.json"]
    names += [
        f"rounds/{r['round']:02d}/literature.json"
        for r in journal.report.get("rounds", [])
        if "branch_id" not in r
    ]
    for name in names:
        value = saved_json(journal, name)
        if value:
            if name == "research_briefs.json":
                for source_id, brief in value.items():
                    walk(brief, f"{name} · {source_id}")
            else:
                walk(value, name)
    sources = {s["source_id"] for s in journal.sources}
    unique = {}
    for record in found:
        if record["source_id"] in sources:
            unique[(record["source_id"], record["quote"], record["concept"])] = record
    return list(unique.values())


def paper_dot(journal: Journal, evidence: list[dict], selected: str | None = None) -> str:
    lines = [
        'graph papers { rankdir=LR; bgcolor="transparent";',
        'graph [pad="0.3", nodesep="0.5", ranksep="0.7"];',
        'node [shape=box, style="rounded,filled", fontname="Arial", fontsize=12, '
        'margin="0.25,0.2", fillcolor="white", color="#cbd5e1"];',
        'edge [color="#a5b4c5", fontname="Arial", fontsize=10];',
    ]
    ids = {s["source_id"]: f"p{i}" for i, s in enumerate(journal.sources)}
    for source in journal.sources:
        sid = source["source_id"]
        refs = [e for e in evidence if e["source_id"] == sid]
        concepts = list(
            dict.fromkeys(
                e["concept"] if e["concept"] != "Recorded evidence" else e["quote"] for e in refs
            )
        )
        concept = (
            textwrap.shorten(concepts[0], width=135, placeholder="…")
            if concepts
            else "No recorded evidence passage"
        )
        title = source.get("title", sid)
        text = f"{'SEED PAPER' if sid == 'seed' else 'PAPER'} · {sid}\n"
        text += "\n".join(textwrap.wrap(title, 36))
        text += "\n\n" + "\n".join(textwrap.wrap(concept, 36))
        text += f"\n{len(refs)} recorded evidence passages"
        lines.append(
            f"{ids[sid]} [label={json.dumps(text, ensure_ascii=False)}, "
            f'color="{"#0f766e" if sid == selected else "#cbd5e1"}", '
            f'fillcolor="{"#ecfdf5" if sid == "seed" else "white"}"];'
        )
    by_artifact = defaultdict(set)
    for item in evidence:
        by_artifact[(item["artifact"], item["concept"])].add(item["source_id"])
    pairs = {pair for group in by_artifact.values() for pair in combinations(sorted(group), 2)}
    for a, b in sorted(pairs):
        lines.append(f'{ids[a]} -- {ids[b]} [label="shared evidence context"];')
    retrieval = saved_json(journal, "reference_retrieval.json") or {}
    if "seed" in ids:
        for record in retrieval.get("records", []):
            if record.get("status") != "retrieved_for_review":
                continue
            target = next(
                (
                    source["source_id"]
                    for source in journal.sources
                    if source.get("sha256") and source["sha256"] == record.get("sha256")
                ),
                None,
            )
            if target and target != "seed":
                edge_label = json.dumps(
                    f"seed citation · p. {record.get('page', '?')}", ensure_ascii=False
                )
                lines.append(
                    f'{ids["seed"]} -- {ids[target]} [label={edge_label}, color="#0f766e"];'
                )
    return "\n".join([*lines, "}"])


def artifact_origin(name: str) -> str:
    if name.startswith("inputs/") or name == "sources.json":
        return "Original source"
    if name.startswith("roles/") and ("-response." in name or name.endswith("-response.txt")):
        return "Agent response"
    if name.endswith("trials.csv"):
        return "Simulation data"
    if name.startswith("code/") or name in {"uv.lock", "environment.json"}:
        return "Reproduction environment"
    if name.startswith("roles/") and "-request." in name:
        return "Agent input"
    return "Workflow record"


def recorded_prompt(journal: Journal, node: Activity) -> dict | None:
    """Inspect this invocation's archived prompt; never substitute today's instructions."""
    if not node.call_id or node.kind != "omnigent":
        return None
    name = f"{node.call_id}-request.json"
    record = saved_json(journal, name)
    if not record or not isinstance(record.get("prompt"), str):
        return None
    try:
        prompt = json.loads(record["prompt"])
    except (TypeError, ValueError):
        return None
    if not isinstance(prompt, dict) or not isinstance(prompt.get("instructions"), str):
        return None
    data = prompt.get("data", {})
    scope = []
    source = data.get("source", {})
    if isinstance(source, dict) and source.get("source_id"):
        scope.append(f"Source: {source['source_id']}")
    for key in ("branch_id", "batch", "round"):
        if key in data:
            scope.append(f"{key.replace('_', ' ')}: {data[key]}")
    if not scope:
        scope.append(node.stage)
    return {
        **prompt,
        "artifact": name,
        "prompt_version": record.get("prompt_version", "Unrecorded"),
        "input_scope": " · ".join(scope),
        "exact_prompt": record["prompt"],
    }


def downstream_steps(nodes: list[Activity], node: Activity) -> list[Activity]:
    """Only direct recorded dependencies; legacy sequential order is labeled by the UI."""
    if node.parents is None:
        index = nodes.index(node)
        return nodes[index + 1 : index + 2]
    last_attempt = not any(n.stage == node.stage for n in nodes[nodes.index(node) + 1 :])
    return [
        n
        for n in nodes
        if node.key in (n.parents or []) or last_attempt and node.stage in (n.parents or [])
    ]
