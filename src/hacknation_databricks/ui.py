"""Page composition shared by the React application and view contract tests."""

from importlib import import_module

from hacknation_databricks.tracking_ui import render_sidebar
from hacknation_databricks.web.components import _CURRENT

PAGES = [
    {"id": "sources", "title": "Source intake", "icon": "library", "group": "Research"},
    {"id": "overview", "title": "Discovery overview", "icon": "science", "group": "Research"},
    {"id": "agents", "title": "Agents & execution loops", "icon": "tree", "group": "Research"},
    {"id": "policies", "title": "Omnigent & policies", "icon": "shield", "group": "Platform"},
    {"id": "evidence", "title": "Generated artifacts", "icon": "archive", "group": "Audit"},
]


def render_page():
    render_sidebar()
    page = _CURRENT.get().session.page
    if page not in {p["id"] for p in PAGES}:
        raise ValueError("Unknown page")
    import_module(f"hacknation_databricks.app_pages.{page}").render()
