"""Source intake controls and a persistent, inspectable library."""

import hashlib
import json
from pathlib import Path

import streamlit as st

from hacknation_databricks.research.intake import (
    register_arxiv,
    register_upload,
    source_root,
)
from hacknation_databricks.source_cache import source_library
from hacknation_databricks.tracking import load_journal


def render_source_progress() -> None:
    """Show progress only when the run's seed bytes match the prepared source."""
    from hacknation_databricks.activity_ui import render_activity
    from hacknation_databricks.run_feedback_ui import render_run_outcome
    from hacknation_databricks.tracking_ui import run_root

    selected = st.session_state.get("run_selection")
    source_path = st.session_state.get("selected_seed_path")
    if not selected or not source_path:
        return
    journal = load_journal(run_root() / selected)
    seed = next((s for s in journal.sources if s.get("source_id") == "seed"), {})
    try:
        digest = hashlib.sha256(Path(source_path).read_bytes()).hexdigest()
    except OSError:
        st.info("Choose an available source to see its run progress.")
        return
    if not seed.get("sha256") or seed["sha256"] != digest:
        st.caption(
            f"The selected exploration run belongs to {seed.get('title', 'another paper')}. "
            "Its progress is available in Agents & loops. "
            "Choose a matching run or start a new run for the paper above."
        )
        return
    st.subheader("Run for this paper")
    st.text(seed.get("title", "Seed paper"))
    st.caption(f"Run {journal.run_id} · {'Saved run' if journal.sealed else 'Live snapshot'}")
    if journal.issues:
        st.error("Evidence verification failed. Inspect this run in Generated artifacts.")
        return
    render_run_outcome(journal)
    with st.expander("Exploration progress", expanded=not journal.sealed):
        render_activity(journal)


def render_sources() -> None:
    st.caption(
        "Add a seed paper or related literature. Originals and provenance stay with every run."
    )
    for level, message in st.session_state.pop("intake_messages", []):
        getattr(st, level)(message)
    upload, arxiv = st.tabs(["Upload documents", "Import from arXiv"])
    with upload:
        with st.form("source_upload", clear_on_submit=True):
            files = st.file_uploader(
                "PDF or Markdown",
                type=["pdf", "md"],
                accept_multiple_files=True,
                max_upload_size=10,
            )
            st.caption("10 MiB per file · up to 100 PDF pages · text-based PDFs and UTF-8 Markdown")
            submitted = st.form_submit_button("Add files to library", width="stretch")
        if submitted:
            messages = []
            for file in files or []:
                try:
                    item = register_upload(file.name, file.getvalue(), source_root())
                    st.session_state["intake_selected"] = str(Path(item.path).resolve())
                    messages.append(
                        ("success", f"Ready: {item.title} · {len(item.pages)} text pages")
                    )
                except (ValueError, UnicodeError) as exc:
                    messages.append(("error", f"{file.name}: {exc}"))
                except Exception:
                    messages.append(
                        (
                            "error",
                            f"{file.name}: could not extract readable text. "
                            "Use an unencrypted text PDF or UTF-8 Markdown.",
                        )
                    )
            st.session_state["intake_messages"] = messages or [
                ("warning", "Choose files to add first.")
            ]
            st.rerun()
    with arxiv:
        with st.form("arxiv_intake", clear_on_submit=True):
            link = st.text_input(
                "arXiv link or identifier", placeholder="https://arxiv.org/abs/2607.24975v1"
            )
            st.caption(
                "Abstract and PDF links accepted. Unversioned links resolve to a pinned version."
            )
            submitted = st.form_submit_button("Import arXiv paper", width="stretch")
        if submitted:
            with st.spinner("Resolving paper version and validating PDF…"):
                try:
                    item = register_arxiv(link, source_root())
                    st.session_state["intake_selected"] = str(Path(item.path).resolve())
                    st.session_state["intake_messages"] = [("success", f"Ready: {item.title}")]
                except ValueError as exc:
                    st.session_state["intake_messages"] = [("error", str(exc))]
                except Exception:
                    st.session_state["intake_messages"] = [
                        (
                            "error",
                            "arXiv import failed. Check the link "
                            "and connection, retry with a versioned link, or upload the PDF.",
                        )
                    ]
            st.rerun()
    st.caption(
        "Intake uses no model calls. Scans require OCR before upload; "
        "oversized sources are rejected, never truncated."
    )


def render_source_details(path: Path) -> None:
    """Inspect the same source selected for the run, without a second picker."""
    sources, _ = source_library(source_root())
    source = next((item for item in sources if Path(item.path).resolve() == path.resolve()), None)
    if source is None:
        return
    with st.expander("Extracted text & provenance", expanded=False):
        page = st.number_input(
            "Text page",
            min_value=1,
            max_value=len(source.pages),
            value=1,
            key=f"source_page_{source.sha256}",
        )
        st.text(source.pages[page - 1])
        if Path(source.path).suffix == ".md":
            st.caption(
                "Markdown text pages are separated by form feeds; "
                "ordinary documents have one text page."
            )
        sidecar = Path(source.path).with_suffix(Path(source.path).suffix + ".json")
        st.json(json.loads(sidecar.read_text()) if sidecar.is_file() else source.payload())
        st.download_button(
            "Download original source",
            Path(source.path).read_bytes(),
            file_name=source.title
            if Path(source.title).suffix in {".pdf", ".md"}
            else f"{source.sha256[:12]}{Path(source.path).suffix}",
        )
