"""Server-side view composition for the React client.

Views emit a small, explicit JSON component protocol. Only registered controls can
change session state; callbacks and scientific objects never cross the wire.
The browser owns tabs, disclosures, focus, form drafts and graph interaction.
"""

import copy
import hashlib
import io
import json as jsonlib
import math
import time
from collections import OrderedDict
from collections.abc import MutableMapping
from contextvars import ContextVar
from dataclasses import dataclass, field
from functools import wraps
from threading import RLock
from types import SimpleNamespace
from typing import Any

_CURRENT = ContextVar("research_view")


class RenderAgain(Exception):
    pass


@dataclass
class UploadedFile:
    name: str
    data: bytes

    def getvalue(self):
        return self.data


@dataclass
class Session:
    state: dict = field(default_factory=dict)
    widgets: dict = field(default_factory=dict)
    blobs: dict = field(default_factory=dict)
    uploads: dict = field(default_factory=dict)
    page: str = "sources"
    lock: Any = field(default_factory=RLock)
    touched: float = field(default_factory=time.monotonic)
    revision: int = 0
    csrf: str = ""
    view_id: str = "default"


class State(MutableMapping):
    def __getitem__(self, key):
        return _CURRENT.get().session.state[key]

    def __setitem__(self, key, value):
        _CURRENT.get().session.state[key] = value

    def __delitem__(self, key):
        del _CURRENT.get().session.state[key]

    def __iter__(self):
        return iter(_CURRENT.get().session.state)

    def __len__(self):
        return len(_CURRENT.get().session.state)


session_state = State()


class Block:
    def __init__(self, node):
        self.node = node

    def __enter__(self):
        _CURRENT.get().stack.append(self.node)
        return self

    def __exit__(self, *_):
        _CURRENT.get().stack.pop()

    def __getattr__(self, name):
        function = globals().get(name)
        if not callable(function):
            raise AttributeError(name)

        def call(*args, **kwargs):
            with self:
                return function(*args, **kwargs)

        return call

    def update(self, **kwargs):
        self.node.update(kwargs)


class Sidebar:
    def __enter__(self):
        return Block(_CURRENT.get().sidebar).__enter__()

    def __exit__(self, *args):
        _CURRENT.get().stack.pop()


sidebar = Sidebar()


class View:
    def __init__(self, session, action=None):
        self.session = session
        self.action = action
        self.main = {"id": "main", "type": "root", "children": []}
        self.sidebar = {"id": "sidebar", "type": "root", "children": []}
        self.stack = [self.main]
        self.widgets = {}
        self.blobs = {}
        self.counts = {}
        self.refresh = None

    def emit(self, kind, **props):
        parent = self.stack[-1]
        identity = f"{parent['id']}/{kind}:{props.get('label', '')}"
        count = self.counts.get(identity, 0)
        self.counts[identity] = count + 1
        node = {"id": identity + f":{count}", "type": kind, **props}
        parent["children"].append(node)
        return node

    def blob(self, data, filename, mime):
        if isinstance(data, str):
            data = data.encode()
        if isinstance(data, io.BytesIO):
            data = data.getvalue()
        data = bytes(data)
        token = hashlib.sha256(data + filename.encode()).hexdigest()
        self.blobs[token] = (data, filename, mime)
        return f"/api/download/{token}?view={self.session.view_id}"


def _emit(kind, **props):
    return _CURRENT.get().emit(kind, **props)


def container(**kwargs):
    return Block(_emit("container", children=[], **kwargs))


def columns(spec, **kwargs):
    weights = [1] * spec if isinstance(spec, int) else list(spec)
    row = Block(_emit("columns", children=[], weights=weights, **kwargs))
    with row:
        return [Block(_emit("column", children=[])) for _ in weights]


def expander(label, expanded=False, **kwargs):
    return Block(_emit("expander", label=label, expanded=expanded, children=[], **kwargs))


def tabs(labels):
    row = Block(_emit("tabs", labels=labels, children=[]))
    with row:
        return [Block(_emit("tab", label=label, children=[])) for label in labels]


def form(key, clear_on_submit=False, **kwargs):
    return Block(_emit("form", label=key, clear_on_submit=clear_on_submit, children=[], **kwargs))


def spinner(text, **kwargs):
    return container()


def status(label, **kwargs):
    return expander(label, **kwargs)


def _form_id():
    return next((n["id"] for n in reversed(_CURRENT.get().stack) if n["type"] == "form"), None)


def _widget(kind, label, default=None, key=None, on_change=None, options=None, **props):
    view = _CURRENT.get()
    if "type" in props:
        props["variant"] = props.pop("type")
    # Default participates in implicit identity, so profile changes reset its budgets.
    scope = (
        "sidebar"
        if view.stack[0] is view.sidebar or view.sidebar in view.stack
        else view.session.page
    )
    identity = (
        key
        if key is not None
        else jsonlib.dumps([scope, _form_id(), kind, label, default], default=str, sort_keys=True)
    )
    widget_id = hashlib.sha256(identity.encode()).hexdigest()[:24]
    state_key = key if key is not None else "widget:" + widget_id
    state = view.session.state
    if state_key not in state:
        state[state_key] = default
    value = state[state_key]
    if options is not None and value not in options:
        value = default if default in options else (options[0] if options else None)
        state[state_key] = value
    display = props.pop("format_func", str)
    wire_options = [display(o) for o in options] if options is not None else None
    wire_value = options.index(value) if options is not None and value in options else value
    if kind == "file_uploader":
        wire_value = [
            {"token": token, "name": view.session.uploads[token].name}
            for token in (value or [])
            if token in view.session.uploads
        ]
    node = _emit(
        kind,
        label=label,
        value=wire_value,
        widget=widget_id,
        options=wire_options,
        form=_form_id(),
        **props,
    )
    definition = {
        "node": node,
        "state_key": state_key,
        "callback": on_change,
        "options": options,
        "default": default,
        "clear_on_submit": any(n.get("clear_on_submit") for n in view.stack),
    }
    view.widgets[widget_id] = definition
    return value, widget_id


def selectbox(label, options, index=0, **kwargs):
    options = list(options)
    default = options[index] if options and index is not None else None
    return _widget("selectbox", label, default, options=options, **kwargs)[0]


def segmented_control(label, options, default=None, **kwargs):
    return _widget("segmented_control", label, default, options=list(options), **kwargs)[0]


def pills(label, options, default=None, **kwargs):
    return _widget("pills", label, default, options=list(options), **kwargs)[0]


def checkbox(label, value=False, **kwargs):
    return _widget("checkbox", label, value, **kwargs)[0]


def toggle(label, value=False, **kwargs):
    return _widget("toggle", label, value, **kwargs)[0]


def text_input(label, value="", **kwargs):
    return _widget("text_input", label, value, **kwargs)[0]


def number_input(label, min_value=None, max_value=None, value=0, step=None, **kwargs):
    return _widget(
        "number_input",
        label,
        value,
        min_value=min_value,
        max_value=max_value,
        step=step or (1 if isinstance(value, int) else 0.01),
        **kwargs,
    )[0]


def button(label, **kwargs):
    _, widget_id = _widget("button", label, **kwargs)
    return _CURRENT.get().action == widget_id and not kwargs.get("disabled")


def form_submit_button(label, **kwargs):
    return button(label, **kwargs)


def file_uploader(label, type=None, accept_multiple_files=False, **kwargs):
    tokens, _ = _widget(
        "file_uploader", label, [], extensions=type, multiple=accept_multiple_files, **kwargs
    )
    files = [
        _CURRENT.get().session.uploads[t] for t in tokens if t in _CURRENT.get().session.uploads
    ]
    return files if accept_multiple_files else next(iter(files), None)


def execution_graph(key, data, on_selected_change):
    return _widget(
        "execution_graph",
        "Execution timeline",
        data["selected"],
        key=key,
        on_change=on_selected_change,
        graph=data,
    )[0]


def download_button(label, data, file_name="download", mime="application/octet-stream", **kwargs):
    url = _CURRENT.get().blob(data, file_name, mime)
    _emit(
        "download",
        label=label,
        url=url,
        filename=file_name,
        **{k: v for k, v in kwargs.items() if k != "key"},
    )


def link_button(label, url, **kwargs):
    _emit("link", label=label, url=url, **kwargs)


def title(value, **kwargs):
    _emit("title", value=str(value), **kwargs)


def header(value, **kwargs):
    _emit("header", value=str(value), **kwargs)


def subheader(value, **kwargs):
    _emit("subheader", value=str(value), **kwargs)


def caption(value, **kwargs):
    _emit("caption", value=str(value), **kwargs)


def text(value, **kwargs):
    _emit("text", value=str(value), **kwargs)


def markdown(value, unsafe_allow_html=False, **kwargs):
    # Styles belong to the React bundle; all other trusted markup is sanitized there.
    if str(value).lstrip().startswith("<style>"):
        return
    _emit("html" if unsafe_allow_html else "markdown", value=str(value), **kwargs)


def json(value, expanded=True, **kwargs):
    if isinstance(value, str):
        try:
            value = jsonlib.loads(value)
        except ValueError:
            pass
    _emit("json", value=value, expanded=expanded, **kwargs)


def code(value, **kwargs):
    _emit("code", value=str(value), **kwargs)


def write(*values):
    for value in values:
        if isinstance(value, (dict, list, tuple)):
            json(value)
        else:
            markdown(str(value))


def info(value, **kwargs):
    _emit("info", value=str(value), **kwargs)


def warning(value, **kwargs):
    _emit("warning", value=str(value), **kwargs)


def error(value, **kwargs):
    _emit("error", value=str(value), **kwargs)


def success(value, **kwargs):
    _emit("success", value=str(value), **kwargs)


def metric(label, value, delta=None, **kwargs):
    _emit("metric", label=label, value=str(value), delta=delta, **kwargs)


def divider():
    _emit("divider")


def dataframe(data, **kwargs):
    import pandas as pd

    frame = data if isinstance(data, pd.DataFrame) else pd.DataFrame(data)
    _emit(
        "dataframe",
        columns=[str(c) for c in frame.columns],
        rows=jsonlib.loads(frame.to_json(orient="values", date_format="iso")),
        **kwargs,
    )


column_config = SimpleNamespace(NumberColumn=lambda *a, **kw: kw)


def altair_chart(chart, **kwargs):
    _emit("chart", spec=chart.to_dict(), **kwargs)


def line_chart(data, **kwargs):
    import altair as alt

    frame = data.reset_index()
    x = kwargs.pop("x", frame.columns[0])
    y = kwargs.pop("y", list(data.columns))
    if isinstance(y, list):
        frame = frame.melt(id_vars=[x], value_vars=y, var_name="series", value_name="value")
        chart = alt.Chart(frame).mark_line().encode(x=x, y="value:Q", color="series:N")
    else:
        chart = alt.Chart(frame).mark_line().encode(x=x, y=y)
    if kwargs.get("x_label"):
        chart = chart.encode(x=alt.X(x, title=kwargs.pop("x_label")))
    if kwargs.get("y_label"):
        chart = chart.encode(y=alt.Y("value:Q", title=kwargs.pop("y_label")))
    altair_chart(chart, **kwargs)


def graphviz_chart(dot, **kwargs):
    _emit("graphviz", dot=dot, **kwargs)


def image(data, **kwargs):
    mime = "image/svg+xml" if str(data).lstrip().startswith("<svg") else "image/png"
    url = _CURRENT.get().blob(data, "visualization.svg" if "svg" in mime else "image.png", mime)
    _emit("image", url=url, **kwargs)


def iframe(source, **kwargs):
    # Only trusted process_html templates call this. Browser sandboxes script execution.
    url = _CURRENT.get().blob(source, "process.html", "text/html")
    _emit("iframe", url=url.replace("/download/", "/embed/"), **kwargs)


def fragment(function=None, *, run_every=None):
    def decorate(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            # Decide before reading artifacts: sealing during this render must
            # still allow one final poll to fetch the completed snapshot.
            if run_every:
                from hacknation_databricks.tracking_ui import run_root

                session = _CURRENT.get().session
                selected = session.state.get("run_selection")
                live = selected and not (run_root() / selected / "manifest.json").is_file()
                if session.state.get("research_future") is not None or live:
                    _CURRENT.get().refresh = 5
            return fn(*args, **kwargs)

        return wrapped

    return decorate(function) if function else decorate


def rerun():
    raise RenderAgain


def switch_page(path):
    page = path.rsplit("/", 1)[-1].removesuffix(".py")
    if page not in {"sources", "overview", "agents", "policies", "evidence"}:
        raise ValueError("Unknown page")
    _CURRENT.get().session.page = page
    rerun()


def set_page_config(**kwargs):
    pass


def _cache(function=None, *, max_entries=128, ttl=None, resource=False, **kwargs):
    def decorate(fn):
        saved = OrderedDict()
        lock = RLock()

        @wraps(fn)
        def wrapped(*args, **kw):
            key = repr((args, sorted(kw.items())))
            with lock:
                current = saved.get(key)
                if current and (ttl is None or time.monotonic() - current[0] < ttl):
                    saved.move_to_end(key)
                    return current[1] if resource else copy.deepcopy(current[1])
                result = fn(*args, **kw)
                saved[key] = (time.monotonic(), result)
                while len(saved) > max_entries:
                    saved.popitem(last=False)
                return result if resource else copy.deepcopy(result)

        wrapped.clear = saved.clear
        return wrapped

    return decorate(function) if function else decorate


def cache_data(function=None, **kwargs):
    return _cache(function, **kwargs)


def cache_resource(function=None, **kwargs):
    return _cache(function, resource=True, **kwargs)


def apply_event(session, values, action=None):
    """Validate the entire event before changing any values or running callbacks."""
    updates = []
    if action and (
        action not in session.widgets
        or session.widgets[action]["node"]["type"] != "button"
        or session.widgets[action]["node"].get("disabled")
    ):
        raise ValueError("This action is unavailable. Refresh the page.")
    for key, value in values.items():
        if key not in session.widgets:
            raise ValueError("This control is no longer available. Refresh the page.")
        definition = session.widgets[key]
        node = definition["node"]
        kind = node["type"]
        if node.get("disabled") or kind == "button":
            raise ValueError("This control cannot be changed")
        if definition["options"] is not None:
            if type(value) is not int or not 0 <= value < len(definition["options"]):
                raise ValueError("Invalid selection")
            value = definition["options"][value]
        elif kind in {"checkbox", "toggle"}:
            if type(value) is not bool:
                raise ValueError("Expected a boolean")
        elif kind == "number_input":
            if type(value) not in {float, int} or not math.isfinite(value):
                raise ValueError("Expected a finite number")
            if isinstance(definition["default"], int) and value != int(value):
                raise ValueError("Expected a whole number")
            if (node["min_value"] is not None and value < node["min_value"]) or (
                node["max_value"] is not None and value > node["max_value"]
            ):
                raise ValueError("Number is outside the configured bounds")
        elif kind == "file_uploader":
            if (
                not isinstance(value, list)
                or len(value) > 10
                or any(not isinstance(t, str) or t not in session.uploads for t in value)
            ):
                raise ValueError("Invalid upload")
        elif kind == "execution_graph":
            if not isinstance(value, str) or value not in node["graph"]["labels"]:
                raise ValueError("Unknown execution step")
        elif kind == "text_input":
            if not isinstance(value, str) or len(value) > 4096:
                raise ValueError("Text exceeds 4096 characters")
        else:
            raise ValueError("Unsupported control")
        updates.append((definition, value))
    for definition, value in updates:
        session.state[definition["state_key"]] = value
    context = View(session)
    token = _CURRENT.set(context)
    try:
        for definition, _ in updates:
            if definition["callback"]:
                definition["callback"]()
    finally:
        _CURRENT.reset(token)


def render(session, renderer, action=None):
    previous_widgets = session.widgets
    submit_form = previous_widgets.get(action, {}).get("node", {}).get("form")

    def clear_submitted_form():
        if not submit_form:
            return
        for definition in previous_widgets.values():
            node = definition["node"]
            if node.get("form") == submit_form and definition.get("clear_on_submit"):
                session.state.pop(definition["state_key"], None)
                if node["type"] == "file_uploader":
                    session.uploads.clear()

    for _ in range(6):
        view = View(session, action)
        token = _CURRENT.set(view)
        try:
            renderer()
        except RenderAgain:
            clear_submitted_form()
            action = None  # One click can never execute twice, including redirects.
            continue
        finally:
            _CURRENT.reset(token)
        session.widgets = view.widgets
        # Keep previous links valid across refreshes; cap retained count and bytes.
        session.blobs.update(view.blobs)
        retained_bytes = sum(len(blob[0]) for blob in session.blobs.values())
        for key in list(session.blobs):
            if len(session.blobs) <= 256 and retained_bytes <= 128 * 1024 * 1024:
                break
            if key not in view.blobs:
                retained_bytes -= len(session.blobs.pop(key)[0])
        session.revision += 1
        return {
            "page": session.page,
            "main": view.main["children"],
            "sidebar": view.sidebar["children"],
            "refresh": view.refresh,
            "revision": session.revision,
            "csrf": session.csrf,
        }
    raise RuntimeError("View exceeded its transition limit")
