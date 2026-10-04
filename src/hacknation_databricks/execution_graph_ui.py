"""Clickable recorded executions, with selection preserved across live refreshes."""

from hacknation_databricks.research.activity import activity_svg
from hacknation_databricks.research_views import label
from hacknation_databricks.web import components as ui


def render_execution_graph(nodes, journal):
    """Only a key from the current trace can select a step; clicks pause live follow."""
    scope = str(journal.directory.resolve())
    selection_key = f"execution-selection:{scope}"
    follow_key = f"execution-follow:{scope}"
    component_key = f"execution-graph:{scope}"
    by_key = {node.key: node for node in nodes}
    if ui.session_state.get(selection_key) not in by_key:
        ui.session_state[selection_key] = nodes[0].key
    follow = False
    if not journal.sealed:
        follow = ui.toggle("Follow newest step", value=True, key=follow_key)
    if follow:
        ui.session_state[selection_key] = nodes[-1].key
    selected = ui.session_state[selection_key]

    def select_step():
        clicked = ui.session_state.get(component_key)
        if isinstance(clicked, str) and clicked in by_key:
            ui.session_state[selection_key] = clicked
            ui.session_state[follow_key] = False

    graph = activity_svg(nodes, selected)
    ui.execution_graph(
        key=component_key,
        data={
            "svg": graph,
            "selected": selected,
            "follow": follow,
            "labels": {
                node.key: f"{label(node.role)} · {node.stage} · {node.status}" for node in nodes
            },
        },
        on_selected_change=select_step,
    )
    return by_key[selected], graph
