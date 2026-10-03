"""Source intake controls and a persistent, inspectable library."""

import json
from pathlib import Path

import streamlit as st

from hacknation_databricks.research.intake import (
    list_sources,
    register_arxiv,
    register_upload,
    source_root,
)


def render_sources() -> None:
    st.subheader("Source intake")
    st.caption(
        "Add a seed paper or related literature. Originals and provenance stay with every run."
    )
    for level, message in st.session_state.pop("intake_messages", []):
        getattr(st, level)(message)
    upload, arxiv = st.columns([1.15, 1])
    with upload, st.container(border=True):
        st.markdown("**Upload documents**")
        with st.form("source_upload", clear_on_submit=True):
            files = st.file_uploader(
                "PDF or Markdown",
                type=["pdf", "md"],
                accept_multiple_files=True,
                max_upload_size=10,
            )
            st.caption("10 MiB per file · up to 100 PDF pages · text-based PDFs and UTF-8 Markdown")
            submitted = st.form_submit_button("Add files to library", use_container_width=True)
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
    with arxiv, st.container(border=True):
        st.markdown("**Import from arXiv**")
        with st.form("arxiv_intake", clear_on_submit=True):
            link = st.text_input(
                "arXiv link or identifier", placeholder="https://arxiv.org/abs/2607.24975v1"
            )
            st.caption(
                "Abstract and PDF links accepted. Unversioned links resolve to a pinned version."
            )
            submitted = st.form_submit_button("Import arXiv paper", use_container_width=True)
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
    sources, issues = list_sources(source_root())
    for issue in issues:
        st.warning(issue)
    st.markdown(f"**Source library · {len(sources)} ready**")
    if not sources:
        st.info(
            "Add a source above, then choose it as the seed or related literature in the sidebar."
        )
        return
    st.dataframe(
        [
            {
                "Title": s.title,
                "Format": Path(s.path).suffix[1:].upper(),
                "Text pages": len(s.pages),
                "Characters": sum(map(len, s.pages)),
                "Imported (UTC)": s.retrieved_at,
                "Source": s.url or "Local upload",
                "SHA-256": s.sha256,
            }
            for s in sources
        ],
        hide_index=True,
        use_container_width=True,
    )
    selected = st.selectbox(
        "Inspect source", range(len(sources)), format_func=lambda i: sources[i].title
    )
    source = sources[selected]
    with st.expander("Extracted text & provenance", expanded=False):
        page = st.number_input("Text page", min_value=1, max_value=len(source.pages), value=1)
        st.text(source.pages[page - 1])
        if Path(source.path).suffix == ".md":
            st.caption(
                "Markdown text pages are separated by form feeds; "
                "ordinary documents have one text page."
            )
        st.json(
            json.loads(
                Path(source.path).with_suffix(Path(source.path).suffix + ".json").read_text()
            )
        )
        st.download_button(
            "Download original source",
            Path(source.path).read_bytes(),
            file_name=source.title
            if Path(source.title).suffix in {".pdf", ".md"}
            else f"{source.sha256[:12]}{Path(source.path).suffix}",
        )
