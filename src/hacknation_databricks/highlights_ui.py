"""Paper findings beside new simulation artifacts, with local controls kept explicit."""

import streamlit as st

from hacknation_databricks.research.highlights import research_highlights


def render_highlights(bundle: dict) -> None:
    highlights = research_highlights(bundle)
    reference = highlights["reference"]
    original, proposed = st.columns(2)
    with original, st.container(border=True, height="stretch"):
        st.markdown("**Original paper · cited result**")
        if reference:
            if reference.get("rate") is not None:
                st.metric("Published wrapping probability", f"{reference['rate']:.3%}")
            st.write(reference["finding"])
            st.markdown(f"[Source: {reference['location']}]({reference['url']})")
            st.caption("Published evidence; no new simulation of the original paper is implied.")
        else:
            st.info(
                "A published numerical benchmark has not been mapped for this source and endpoint."
            )
    with proposed, st.container(border=True, height="stretch"):
        st.markdown("**Proposed simulation · agent-selected change**")
        proposal = bundle.get("proposal", {})
        if proposal.get("title"):
            st.markdown(f"**{proposal['title']}**")
        for row in highlights["rows"]:
            st.metric(row["Scenario"], row["Follow-up"])
        st.write(highlights["change"])
        if proposal.get("hypothesis"):
            with st.expander("Proposed hypothesis and context"):
                st.write(proposal["hypothesis"])
        if bundle.get("recipe_artifact"):
            st.caption("Executed recipe: " + bundle["recipe_artifact"])
        st.caption("Agent-selected parameters executed by the bounded simulation tool.")
    st.markdown("**Key metric · how to read the result**")
    st.write(highlights["meaning"])
    if highlights["rows"]:
        if reference and reference.get("rate") is not None:
            st.caption(
                "The paper reports a critical, infinite-size estimate. The proposed simulations "
                "use the recorded finite sizes and fixed occupation probability. Their rates "
                "are a contextual comparison, not a measured improvement over the paper."
            )
        st.markdown("**Measured change against the local control**")
        for row in highlights["rows"]:
            with st.container(border=True):
                st.caption(row["Scenario"])
                st.markdown(f"**{row['What changed']}**")
                st.write(f"Local control {row['Local original']} → proposed {row['Follow-up']}")
                st.write(row["Uncertainty"])
                if row.get("False-alert tradeoff"):
                    st.write("False-alert tradeoff: " + row["False-alert tradeoff"])
                st.caption("Samples (control / proposed): " + row["Samples (original / follow-up)"])
        st.markdown("**Scientific insight · what this establishes**")
        st.write(highlights["implication"])
        st.caption(bundle["scope"])
    else:
        st.info("No completed proposed simulation is available yet; no difference can be claimed.")
