# HackNation Databricks

Development and deployment foundation for the Rental Housing Law Navigator.
The application currently provides a thin Streamlit landing page and a health
endpoint at `/_stcore/health`. Extraction, address lookup, and change tracking are
still to be implemented.
Not legal advice.

## Development

Prerequisites: Git, Python 3.12 (uv can install it), uv, Node.js 22 or newer,
and GitHub CLI authenticated with access to this repository.

```bash
uv sync --locked
npm ci
cp .env.example .env
npm run dev
```

Development serves http://127.0.0.1:8000 with reload. The PM2 deployment uses
http://127.0.0.1:8010. Edit `.env` for application settings; credentials, local
datasets, environments, runtime state, and logs are ignored by Git.

```bash
uv add <package>        # Updates pyproject.toml and uv.lock together
uv add --dev <package>
npm run check          # Lint, formatting, tests, and PM2 config syntax
uv run ruff format .
```

Commit `uv.lock` and `package-lock.json`. Use feature branches and pull requests
after the initial bootstrap. CI checks all PRs and pushes to `main`.

## Processes and continuous deployment

```bash
npm start              # Start/restart the app under PM2
npm run status
npm run logs
npm run stop
npm run cd:start       # Start the deployment worker
npm run cd:logs
npm run cd:stop        # Pause automatic deployment; keep app running
npm run deploy         # Check for and deploy an approved main commit once
npm run save           # Save this project's PM2 process list
npm run startup        # Install macOS login service after saving
```

The worker checks `origin/main` every 60 seconds. It waits for the latest GitHub
`CI` push run on the exact commit to succeed, exports that commit into a new
`.runtime/releases/` directory, installs its locked production dependencies,
and restarts the app. PM2 must report the expected revision online and Streamlit's
HTTP health check must pass before recording
the release. A failed health check restores the previous release. The deployment
lock prevents overlapping runs. Working files and the development `.venv` are
never reset or reused by deployment.

PM2 runs in `.runtime/pm2`, isolated from other projects. Use the npm commands
above; plain global `pm2 status` addresses a different daemon. Python runs in
fork mode with one worker; restarts can cause a brief interruption.

See [deployment operations](docs/deployment.md) for login startup, configuration,
rollback, and moving to an always-on host.

## Project layout

- `src/hacknation_databricks/`: Python package and thin Streamlit interface
- `tests/`: UI and deployment safety checks
- `scripts/`: process and deployment operations
- `.github/`: CI, issue template, and PR template
- `hackthon-instruction.pdf`: supplied challenge brief

The reference starter dataset/code is not included here yet. Databricks and model
provider credentials are not required for this infrastructure scaffold.
