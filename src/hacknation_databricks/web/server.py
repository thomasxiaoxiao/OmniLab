"""Local React application server with isolated, validated browser sessions."""

import logging
import os
import re
import secrets
import time
from pathlib import Path
from threading import RLock
from urllib.parse import quote, urlsplit

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
from starlette.middleware.trustedhost import TrustedHostMiddleware

from hacknation_databricks.ui import PAGES, render_page
from hacknation_databricks.web.components import (
    Session,
    UploadedFile,
    apply_event,
    render,
)

app = FastAPI(title="OmniLab", docs_url=None, redoc_url=None)
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=os.environ.get("APP_ALLOWED_HOSTS", "localhost,127.0.0.1,[::1],testserver").split(
        ","
    ),
)
_sessions = {}
_session_lock = RLock()
COOKIE = "omnilab_session"
FRONTEND = Path(os.environ.get("APP_FRONTEND_DIR", Path(__file__).with_name("static")))


def cookie_name(request):
    return f"{COOKIE}_{request.url.port or 80}"


def get_session(request, *, create=False):
    sid = request.cookies.get(cookie_name(request))
    view_id = request.headers.get("x-view-id") or request.query_params.get("view", "default")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", view_id):
        raise HTTPException(400, "Invalid view identifier")
    with _session_lock:
        now = time.monotonic()
        for key, session in list(_sessions.items()):
            if now - session.touched > 7200 and not session.state.get("research_future"):
                del _sessions[key]
        identity = (sid, view_id)
        if identity not in _sessions:
            if not create:
                raise HTTPException(401, "Session expired. Reload the page to reconnect.")
            if len(_sessions) >= 32:
                raise HTTPException(503, "Local session limit reached. Try again later.")
            if not sid or not any(key[0] == sid for key in _sessions):
                sid = secrets.token_urlsafe(32)
            identity = (sid, view_id)
            _sessions[identity] = Session(csrf=secrets.token_urlsafe(32), view_id=view_id)
        session = _sessions[identity]
        session.touched = now
    return sid, session


def check_mutation(request, session):
    if not secrets.compare_digest(request.headers.get("x-csrf-token", ""), session.csrf):
        raise HTTPException(403, "Invalid session token. Reload the page.")
    origin = request.headers.get("origin")
    if origin and urlsplit(origin).netloc != request.headers.get("host"):
        raise HTTPException(403, "Cross-origin actions are not allowed")


def view_response(session, page=None, event=None):
    with session.lock:
        action = None
        if event:
            if event.get("revision") != session.revision:
                raise HTTPException(409, "The view changed. Refresh and retry the action.")
            values = event.get("values", {})
            if not isinstance(values, dict):
                raise ValueError("Expected control values")
            action = event.get("action")
            if action is not None and not isinstance(action, str):
                raise ValueError("Invalid action")
            apply_event(session, values, action)
        if page:
            if page not in {p["id"] for p in PAGES}:
                raise ValueError("Unknown page")
            session.page = page
        return {**render(session, render_page, action), "pages": PAGES}


@app.middleware("http")
async def response_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    if request.url.path.startswith("/api"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/health")
def health():
    # Keep the old probe compatible while deployment configurations migrate.
    return {
        "status": "ok",
        "revision": os.environ.get("APP_REVISION", "development"),
        "frontend": "react",
    }


@app.get("/_stcore/health", include_in_schema=False)
def legacy_health():
    return Response("ok", media_type="text/plain")


@app.get("/api/view")
def get_view(request: Request, page: str | None = None):
    sid, session = get_session(request, create=True)
    try:
        response = JSONResponse(view_response(session, page))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None
    response.set_cookie(
        cookie_name(request),
        sid,
        httponly=True,
        samesite="strict",
        secure=request.url.scheme == "https",
        max_age=7200,
    )
    return response


@app.post("/api/event")
async def event(request: Request):
    _, session = get_session(request)
    check_mutation(request, session)
    raw = bytearray()
    async for part in request.stream():
        raw.extend(part)
        if len(raw) > 65536:
            raise HTTPException(413, "Control request is too large")
    import json

    try:
        payload = json.loads(raw)
        if not isinstance(payload, dict) or set(payload) - {"values", "action", "revision", "page"}:
            raise ValueError("Invalid event")
        return await run_in_threadpool(view_response, session, payload.get("page"), payload)
    except (ValueError, TypeError, KeyError) as exc:
        raise HTTPException(400, str(exc)) from None
    except HTTPException:
        raise
    except Exception:
        logging.exception("View update failed")
        raise HTTPException(
            500, "The view could not update. Refresh to inspect retained artifacts."
        ) from None


@app.post("/api/upload")
async def upload(request: Request, widget: str, name: str):
    _, session = get_session(request)
    check_mutation(request, session)
    with session.lock:
        definition = session.widgets.get(widget, {})
        node = definition.get("node", {})
        if node.get("type") != "file_uploader":
            raise HTTPException(400, "Upload control is unavailable")
        name = Path(name).name
        if Path(name).suffix.lower().lstrip(".") not in node["extensions"]:
            raise HTTPException(400, "Only PDF and Markdown sources are accepted")
    raw = bytearray()
    async for part in request.stream():
        raw.extend(part)
        if len(raw) > 10 * 1024 * 1024:
            raise HTTPException(413, "Maximum source size is 10 MiB")
    with session.lock:
        if sum(len(f.data) for f in session.uploads.values()) + len(raw) > 32 * 1024 * 1024:
            raise HTTPException(413, "Submit this batch before uploading more files")
        token = secrets.token_urlsafe(24)
        session.uploads[token] = UploadedFile(name, bytes(raw))
    return {"token": token, "name": name}


def read_blob(request, token):
    _, session = get_session(request)
    with session.lock:
        if token not in session.blobs:
            raise HTTPException(404, "Download expired. Refresh the selected artifact.")
        return session.blobs[token]


@app.get("/api/download/{token}")
def download(request: Request, token: str):
    data, name, mime = read_blob(request, token)
    # SVG used as an image is inert; HTML and every other artifact download as attachments.
    disposition = "inline" if mime.startswith("image/") else "attachment"
    return Response(
        data,
        media_type=mime,
        headers={
            "Content-Disposition": f"{disposition}; filename*=UTF-8''{quote(Path(name).name)}",
            "Content-Security-Policy": "sandbox; default-src 'none'; style-src 'unsafe-inline'",
        },
    )


@app.get("/api/embed/{token}")
def embed(request: Request, token: str):
    data, _, mime = read_blob(request, token)
    if mime != "text/html":
        raise HTTPException(400, "Invalid visualization")
    # A trusted local player only. No same-origin capability, network or navigation.
    resize = (
        b"<script>new ResizeObserver(()=>parent.postMessage({"
        b"type:'omnigent-player-height',height:document.body.scrollHeight},"
        b"'*')).observe(document.body)</script>"
    )
    data = data.replace(b"</body>", resize + b"</body>")
    return Response(
        data,
        media_type="text/html",
        headers={
            "Content-Security-Policy": "sandbox allow-scripts; default-src 'none'; "
            "script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
            "img-src data:; connect-src 'none'",
        },
    )


if (FRONTEND / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=FRONTEND / "assets"), name="assets")


@app.get("/{path:path}")
def frontend(path: str):
    if path and path not in {p["id"] for p in PAGES}:
        raise HTTPException(404, "Not found")
    index = FRONTEND / "index.html"
    if not index.is_file():
        raise HTTPException(503, "React build is missing. Run npm ci && npm run build.")
    return FileResponse(index, headers={"Cache-Control": "no-cache"})
