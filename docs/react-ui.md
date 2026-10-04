# React UI migration

The application now uses React 19, TypeScript and Vite for the browser UI, with
FastAPI serving the existing Python research workflow. Streamlit is removed from
the application dependencies, imports, test runner and launch commands.

The five pages keep their existing content and order: Source intake, Discovery
overview, Agents & execution loops, Omnigent & policies, and Generated artifacts.
The original colors, typography, cards, expandable evidence, tabs, budget forms,
metrics, charts, player and graph are retained as React components. Framework-only
Streamlit deployment/menu chrome is retired.

## Run locally

```bash
npm ci
uv sync --locked
npm run dev
```

Open http://127.0.0.1:8000. Vite proxies the API to the loopback Python service on
8011 and supports frontend hot updates. The dev launcher stops both child processes
on interruption. Python edits require restarting the command.

For a single production-style local process:

```bash
npm run build
APP_PORT=8010 uv run --locked python -m omnilab
```

The build is generated inside `src/hacknation_databricks/web/static/` and is bundled
in the Python wheel. PM2's existing `npm start` command builds the UI first. The
release builder installs Node dependencies and builds React before producing the
non-editable Python installation. `/health` reports the revision and frontend;
`/_stcore/health` is a compatibility probe returning `ok` for the existing deployer.
The retired Streamlit theme is preserved in `docs/legacy-streamlit-theme.toml`;
there is no active Streamlit configuration.

## Boundaries and state

`web/components.py` composes a small JSON view protocol. Existing Python view
functions retain their scientific projections and callbacks; they import this
module instead of Streamlit. React owns the rendered controls, local form drafts,
expanders, tabs, searchable selections, graph interaction and playback frames.
This preserves one implementation of the scientific presentation rules.

The server keeps scientific objects, futures, source paths, callbacks and policy
drafts in a browser-view session. Separate tabs/views have independent state and
revisions. Clients submit registered control IDs and typed values,
not arbitrary session keys or file paths. Numeric limits, choices, disabled actions,
source identity and artifact verification are checked in Python. Forms submit their
fields together. Launch uses the Omnigent specialist workflow with either supplied repository code
or an explicitly recorded paper-based implementation, and redirects to the
preallocated run ID. Only the two pinned seed examples appear under Seed paper;
uploads/imports have their own selector and can launch without a repository. Live
views poll every five seconds until the final artifacts are sealed, including runs
opened in a fresh tab. Unsubmitted form drafts do not pause the feed and remain
intact. The toolbar shows the live interval and last successful update; returning
to the tab or reconnecting requests an immediate catch-up. Browsers may throttle
background timers. Selected steps, tabs and expanders survive polling; turning off
**Follow newest step** only stops automatic step selection. Viewing artifacts makes
no model calls.

The local service uses port-specific HttpOnly, SameSite cookies, a per-view action
token, same-origin mutation checks and a host allowlist. Session state is in memory;
server restart clears UI drafts while preserving research archives. Run one Python
worker. This remains a local research prototype, without multi-user account access.
Set `APP_ALLOWED_HOSTS` explicitly when using an authorized reverse proxy; changing
that setting does not add authentication.

Original artifacts are served as downloads through session-bound opaque IDs. The
playable simulation is regenerated from validated process data and a trusted local
template, with scripts sandboxed without same-origin access, navigation or network.
Archived/agent HTML is never embedded as an executable page. SVG/markup is sanitized
in the React renderer. Uploads retain the existing source size/extraction limits.

## Verification

```bash
npm run build
npm run check:frontend
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked pytest -q
uv build --wheel
```

The former Streamlit UI assertions now run against the same view protocol used by
React through `tests/view_test.py`. HTTP tests in `tests/test_web_api.py` additionally
cover sessions, CSRF, bounds, stale actions, uploads, policy-to-launch propagation,
launch failure, graph selection, exact downloads and artifact quarantine. Live
model calls are replaced by explicit fixtures only in tests. Browser checks cover
the real rendered components and existing saved research runs.

The October 3 migration checkpoint passed the production build, TypeScript,
Prettier, Ruff and **259 tests**, with three optional real-sandbox tests skipped.
Browser checks covered all five pages, upload deduplication and form clearing,
policy propagation, selectable graph nodes, playback, artifact download and a
narrow viewport without horizontal page overflow. The development proxy and
shutdown of both development processes were also checked. The built Python wheel
contains the frontend assets and no Streamlit dependency. See
[`react-ui-validation.json`](react-ui-validation.json) for the scoped record.

Pixel-identical rendering across browsers is not asserted. The existing product
layout and interactions are retained; browser-native rendering and the retired
Streamlit framework menu differ. The build reports large lazy-loaded visualization
chunks and harmless `use client` directives in the icon dependency. The existing
PM2 dependency tree still has the advisories recorded in `docs/deployment.md`.

The scientific scope, acceptance gates and unresolved limitations remain those in
the original run artifacts. This frontend migration establishes no new scientific
result, independent replication, or discovery acceleration measurement.

Implementation references: [React components and state](https://react.dev/learn),
[Vite build tooling](https://vite.dev/guide/), and
[FastAPI response types](https://fastapi.tiangolo.com/advanced/custom-response/).
