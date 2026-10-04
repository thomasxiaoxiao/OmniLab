"""In-process contract driver for the same view protocol served to React.

These migrated assertions preserve the old scientific UI regression coverage.
HTTP/security tests and real browser checks separately exercise the transport and DOM.
"""

import runpy
from pathlib import Path
from types import SimpleNamespace

from hacknation_databricks.web.components import Session, apply_event, render


def walk(nodes):
    for node in nodes:
        yield node
        yield from walk(node.get("children", []))


class Elements(list):
    def __call__(self, *, key):
        return next(element for element in self if element.key == key)


class Element:
    def __init__(self, app, node):
        self.app = app
        self.node = node

    @property
    def label(self):
        return self.node.get("label", "")

    @property
    def key(self):
        return self.app.session.widgets.get(self.node.get("widget"), {}).get("state_key")

    @property
    def options(self):
        return self.node.get("options", [])

    @property
    def expanded(self):
        return self.node.get("expanded", False)

    @property
    def value(self):
        if self.node["type"] == "dataframe":
            import pandas as pd

            return pd.DataFrame(self.node["rows"], columns=self.node["columns"])
        definition = self.app.session.widgets.get(self.node.get("widget"))
        if definition:
            return self.app.session.state.get(definition["state_key"])
        return self.node.get("value")

    def set_value(self, value):
        definition = self.app.session.widgets[self.node["widget"]]
        if definition["options"] is not None:
            value = definition["options"].index(value)
        self.app.pending[self.node["widget"]] = value
        return self

    def select(self, label):
        self.app.pending[self.node["widget"]] = self.options.index(label)
        return self

    def click(self):
        self.app.action = self.node["widget"]
        return self

    def run(self, **kwargs):
        return self.app.run(**kwargs)

    def __getattr__(self, kind):
        return self.app.elements(kind, self.node.get("children", []))


class ViewTest:
    def __init__(self, renderer):
        self.renderer = renderer
        self.session = Session()
        self.session_state = self.session.state
        self.pending = {}
        self.action = None
        self.snapshot = {"main": [], "sidebar": []}
        self.exception = []

    @classmethod
    def from_file(cls, path):
        path = Path(path)
        if path.name == "ui.py":
            from hacknation_databricks.ui import render_page

            return cls(render_page)
        return cls(lambda: runpy.run_path(str(path), run_name="__main__"))

    @classmethod
    def from_function(cls, function, args=()):
        return cls(lambda: function(*args))

    @classmethod
    def from_string(cls, script):
        return cls(lambda: exec(script, {"__name__": "__main__"}))

    def run(self, **kwargs):
        self.exception = []
        try:
            apply_event(self.session, self.pending, self.action)
            self.snapshot = render(self.session, self.renderer, self.action)
        except Exception as exc:
            self.exception = [SimpleNamespace(value=str(exc), message=str(exc))]
            raise  # Preserve traceback; a render failure must fail the test.
        finally:
            self.pending = {}
            self.action = None
        return self

    def switch_page(self, path):
        self.session.page = Path(path).stem
        return self

    def elements(self, kind, nodes=None):
        kinds = {"markdown", "html"} if kind == "markdown" else {kind}
        if nodes is None:
            nodes = self.snapshot["main"] + self.snapshot["sidebar"]
        return Elements(Element(self, n) for n in walk(nodes) if n["type"] in kinds)

    def __getattr__(self, kind):
        return self.elements(kind)
