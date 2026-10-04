"""Source intake controls and a persistent, inspectable library."""

import hashlib
from pathlib import Path

from hacknation_databricks.research.intake import (
    register_arxiv,
    register_upload,
    source_root,
)
from hacknation_databricks.tracking import load_journal
from hacknation_databricks.web import components as ui


def render_paper_selection() -> Path | None:
    """Offer examples or direct intake, never auto-select an old uploaded paper."""
    from hacknation_databricks.source_cache import source_library
    from hacknation_databricks.tracking_ui import (
        available_sources,
        scope_runs_to_source,
        seed_examples,
        switch_paper_collection,
    )

    _, issues = source_library(source_root())
    for issue in issues:
        ui.warning(issue)
    examples = seed_examples()
    all_sources = available_sources()
    ui.caption("Choose an example paper or add your own.")
    collection = ui.segmented_control(
        "Paper collection",
        ["Example papers", "Your papers"],
        default="Example papers" if examples else "Your papers",
        key="paper_collection",
        on_change=switch_paper_collection,
    )
    # Imports may select an existing example by content hash. Keep feedback visible
    # even when successful intake moves the user out of the custom-paper collection.
    render_intake_messages()
    sources = (
        examples
        if collection == "Example papers"
        else {label: path for label, path in all_sources.items() if label not in examples}
    )
    if collection == "Your papers":
        selected = ui.session_state.get("uploaded_paper_source")
        selected = selected if selected in sources else None
        ui.session_state["paper_source"] = selected
        render_sources(show_messages=False)
        if selected:
            ui.caption(f"Ready to use: {selected.rsplit(' · ', 1)[0]}")
    else:
        if ui.session_state.get("paper_source") not in sources:
            remembered = ui.session_state.get("paper_selections", {}).get(collection)
            ui.session_state["paper_source"] = (
                remembered if remembered in sources else next(iter(sources), None)
            )
        selected = None
        if sources:
            selected = ui.selectbox(
                "Paper", list(sources), key="paper_source", on_change=scope_runs_to_source
            )
            ui.session_state.setdefault("paper_selections", {})[collection] = selected
        else:
            ui.info("No example papers are available. Open Your papers to add a source.")
    source = sources.get(selected)
    if source:
        ui.session_state["selected_seed_path"] = str(source.resolve())
    else:
        ui.session_state.pop("selected_seed_path", None)
        ui.session_state.pop("source_scope_sha256", None)
    return source


def render_source_progress() -> None:
    """Show progress only when the run's seed bytes match the prepared source."""
    from hacknation_databricks.activity_ui import render_activity
    from hacknation_databricks.run_feedback_ui import render_run_outcome
    from hacknation_databricks.tracking_ui import run_root

    selected = ui.session_state.get("run_selection")
    source_path = ui.session_state.get("selected_seed_path")
    if not selected or not source_path:
        return
    journal = load_journal(run_root() / selected)
    seed = next((s for s in journal.sources if s.get("source_id") == "seed"), {})
    try:
        digest = hashlib.sha256(Path(source_path).read_bytes()).hexdigest()
    except OSError:
        ui.info("Choose an available source to see its run progress.")
        return
    if not seed.get("sha256") or seed["sha256"] != digest:
        ui.caption(
            f"The selected exploration run belongs to {seed.get('title', 'another paper')}. "
            "Its progress is available in Agents & loops. "
            "Choose a matching run or start a new run for the paper above."
        )
        return
    ui.subheader("Run for this paper")
    ui.text(seed.get("title", "Seed paper"))
    ui.caption(f"Run {journal.run_id} · {'Saved run' if journal.sealed else 'Live snapshot'}")
    if journal.issues:
        ui.error("Evidence verification failed. Inspect this run in Generated artifacts.")
        return
    render_run_outcome(journal)
    with ui.expander("Exploration progress", expanded=not journal.sealed):
        render_activity(journal)


def render_intake_messages() -> None:
    for level, message in ui.session_state.pop("intake_messages", []):
        getattr(ui, level)(message)


def render_sources(*, show_messages: bool = True) -> None:
    ui.caption(
        "Upload a PDF or Markdown document, or import a paper from arXiv. "
        "Your original document and source details are preserved."
    )
    if show_messages:
        render_intake_messages()
    upload, arxiv = ui.tabs(["Upload paper", "Import from arXiv"])
    with upload:
        with ui.form("source_upload", clear_on_submit=True):
            file = ui.file_uploader(
                "PDF or Markdown",
                type=["pdf", "md"],
                accept_multiple_files=False,
                max_upload_size=10,
            )
            ui.caption("10 MiB per file · up to 100 PDF pages · text-based PDFs and UTF-8 Markdown")
            submitted = ui.form_submit_button("Use uploaded paper", width="stretch")
        if submitted:
            messages = []
            if file is not None:
                try:
                    item = register_upload(file.name, file.getvalue(), source_root())
                    ui.session_state["intake_selected"] = str(Path(item.path).resolve())
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
            ui.session_state["intake_messages"] = messages or [
                ("warning", "Choose a paper to upload first.")
            ]
            ui.rerun()
    with arxiv:
        with ui.form("arxiv_intake", clear_on_submit=True):
            link = ui.text_input(
                "arXiv link or identifier", placeholder="Paste an arXiv abstract or PDF link"
            )
            ui.caption(
                "Abstract and PDF links accepted. Unversioned links resolve to a pinned version."
            )
            submitted = ui.form_submit_button("Import arXiv paper", width="stretch")
        if submitted:
            with ui.spinner("Resolving paper version and validating PDF…"):
                try:
                    item = register_arxiv(link, source_root())
                    ui.session_state["intake_selected"] = str(Path(item.path).resolve())
                    ui.session_state["intake_messages"] = [("success", f"Ready: {item.title}")]
                except ValueError as exc:
                    ui.session_state["intake_messages"] = [("error", str(exc))]
                except Exception:
                    ui.session_state["intake_messages"] = [
                        (
                            "error",
                            "arXiv import failed. Check the link "
                            "and connection, retry with a versioned link, or upload the PDF.",
                        )
                    ]
            ui.rerun()
    ui.caption(
        "Intake uses no model calls. Scans require OCR before upload; "
        "oversized sources are rejected, never truncated."
    )
