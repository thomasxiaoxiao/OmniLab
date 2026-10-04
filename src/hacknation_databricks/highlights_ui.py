"""Paper findings beside new simulation artifacts, with local controls kept explicit."""

from hacknation_databricks.research.highlights import research_highlights
from hacknation_databricks.web import components as ui


def render_highlights(bundle: dict) -> None:
    highlights = research_highlights(bundle)
    reference = highlights["reference"]
    original, proposed = ui.columns(2)
    with original, ui.container(border=True, height="stretch"):
        ui.markdown("**Original paper · cited result**")
        if reference:
            if reference.get("rate") is not None:
                ui.metric("Published wrapping probability", f"{reference['rate']:.3%}")
            ui.write(reference["finding"])
            ui.markdown(f"[Source: {reference['location']}]({reference['url']})")
            ui.caption("Published evidence; no new simulation of the original paper is implied.")
        else:
            ui.info(
                "A published numerical benchmark has not been mapped for this source and endpoint."
            )
    with proposed, ui.container(border=True, height="stretch"):
        ui.markdown("**Proposed simulation · agent-selected change**")
        proposal = bundle.get("proposal", {})
        if proposal.get("title"):
            ui.markdown(f"**{proposal['title']}**")
        for row in highlights["rows"]:
            ui.metric(row["Scenario"], row["Follow-up"])
        ui.write(highlights["change"])
        if proposal.get("hypothesis"):
            with ui.expander("Proposed hypothesis and context"):
                ui.write(proposal["hypothesis"])
        if bundle.get("recipe_artifact"):
            ui.caption("Executed recipe: " + bundle["recipe_artifact"])
        ui.caption("Agent-selected parameters executed by the bounded simulation tool.")
    ui.markdown("**Key metric · how to read the result**")
    ui.write(highlights["meaning"])
    if highlights["rows"]:
        if reference and reference.get("rate") is not None:
            ui.caption(
                "The paper reports a critical, infinite-size estimate. The proposed simulations "
                "use the recorded finite sizes and fixed occupation probability. Their rates "
                "are a contextual comparison, not a measured improvement over the paper."
            )
        ui.markdown("**Measured change against the local control**")
        for row in highlights["rows"]:
            with ui.container(border=True):
                ui.caption(row["Scenario"])
                ui.markdown(f"**{row['What changed']}**")
                ui.write(f"Local control {row['Local original']} → proposed {row['Follow-up']}")
                ui.write(row["Uncertainty"])
                if row.get("False-alert tradeoff"):
                    ui.write("False-alert tradeoff: " + row["False-alert tradeoff"])
                ui.caption("Samples (control / proposed): " + row["Samples (original / follow-up)"])
        ui.markdown("**Scientific insight · what this establishes**")
        ui.write(highlights["implication"])
        ui.caption(bundle["scope"])
    else:
        ui.info("No completed proposed simulation is available yet; no difference can be claimed.")
