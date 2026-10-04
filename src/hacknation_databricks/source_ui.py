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


def render_sources() -> None:
    ui.caption(
        "Upload your own paper. It stays separate from the two seed examples; "
        "originals and provenance stay with its run."
    )
    for level, message in ui.session_state.pop("intake_messages", []):
        getattr(ui, level)(message)
    upload, arxiv = ui.tabs(["Upload documents", "Import from arXiv"])
    with upload:
        with ui.form("source_upload", clear_on_submit=True):
            files = ui.file_uploader(
                "PDF or Markdown",
                type=["pdf", "md"],
                accept_multiple_files=True,
                max_upload_size=10,
            )
            ui.caption("10 MiB per file · up to 100 PDF pages · text-based PDFs and UTF-8 Markdown")
            submitted = ui.form_submit_button("Add files to library", width="stretch")
        if submitted:
            messages = []
            for file in files or []:
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
                ("warning", "Choose files to add first.")
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
