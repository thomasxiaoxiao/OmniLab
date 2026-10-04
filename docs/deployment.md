# Deployment operations

## Initial host setup

The initial deployment target is the local Mac. It serves only on loopback.
It is not a public demo link, and cannot serve while the machine is asleep or off.

Run `npm ci`, `npm run build`, `uv sync --locked`, and copy `.env.example` to `.env` on a new host.
Authenticate `gh auth login`, then configure Git HTTPS authentication with
`gh auth setup-git` if needed. Push the repository to GitHub,
and run `npm run deploy` followed by `npm run cd:start` and `npm run save`.

The worker needs Git read access. GitHub Actions read access is needed only when
the optional CI gate is enabled. Existing GitHub
CLI credentials stay in the OS credential store and are not written to the repo.
No inbound webhook, self-hosted Actions runner, or GitHub deployment secret is
needed for this pull-based deployment.

## Configuration

The React/FastAPI app loads the host checkout's `.env`, including `APP_HOST` and `APP_PORT`.
The release builder compiles React before installing the Python wheel; no Node
process is required to serve a built release. `npm start` also rebuilds the UI.
After edits, use `npm start`. If the port changes, set `DEPLOY_HEALTH_URL` to its
`/_stcore/health` URL when starting the worker (or in its login service environment),
then run `npm run cd:start` to refresh the worker environment.

The deployment controller, npm/PM2 tools and process declaration run from the host
checkout. Application code runs from the selected release. The process declaration
uses the `omnilab` launcher for new releases and the historical Python launcher
for older rollback releases. Process names are `omnilab-app` and `omnilab-cd`.
After changing deployment scripts or npm dependencies, update the host checkout
with a normal fast-forward pull, run `npm ci`, and restart the deployment worker.
Do not overwrite a checkout with uncommitted work.

## Persistence

`npm run save` records processes, but does not by itself install an OS startup
service. Run `npm run startup` on macOS to install the project LaunchAgent, which
runs PM2 resurrection at login; on a
Linux server, use PM2's generated systemd startup instructions. Always use the
project's `PM2_HOME` (`<checkout>/.runtime/pm2`) in the service environment.

For this Mac, a generated LaunchAgent can use the absolute Node executable and
`<checkout>/node_modules/pm2/bin/pm2 resurrect --no-daemon`, with `RunAtLoad` and
`KeepAlive`. Include uv, gh, Git, Node, and Python directories in its `PATH`.
It runs after login and does not keep the Mac awake.

To disable login startup, run
`launchctl bootout gui/$(id -u)/com.omnilab.pm2` and remove
`~/Library/LaunchAgents/com.omnilab.pm2.plist`. Stop the worker and
app separately with the npm commands if desired.

## Failures and rollback

Read `npm run cd:logs` and `npm run logs`. The temporary project policy promotes
main regardless of GitHub CI status. Set `DEPLOY_REQUIRE_CI=1` in the worker
environment with `DEPLOY_REQUIRE_CI=1 npm run cd:start` to restore exact-commit CI
gating; use `DEPLOY_REQUIRE_CI=1 npm run deploy` for a gated one-off deployment.
Use `DEPLOY_REQUIRE_CI=0 npm run cd:start` to disable it again. The controller does
not read this setting from the app’s `.env`. With the gate enabled, missing, pending
or failed CI leaves the existing app running. Dependency installation failure leaves
it running in either mode. If a newly started app fails its health check, the controller restarts
the last recorded healthy release and reports the deployment failure.

For an intentional rollback, revert the faulty commit through Git and push the
revert to `main`; the normal deployment path applies. Pause the worker
with `npm run cd:stop` while investigating if necessary.

Releases and logs are retained in `.runtime/` for diagnosis. Remove older inactive
release directories and rotate logs periodically; do not delete the release
referenced by `.runtime/current.json` or the currently running PM2 process.

## Moving to a server

Clone the private repository on an always-on Linux/macOS host and repeat the host
setup. Add TLS and a reverse proxy before exposing it publicly. A PM2 restart is
not a zero-downtime deployment, and rollback does not undo database migrations.
The current scaffold has no database or migration system.

The pinned PM2 7.0.4 dependency currently reports eight high-severity npm audit
findings in its dependency tree. The application does not enable PM2 file watching
or remote dashboards. Review upstream updates before public production use;
`npm audit fix --force` currently proposes a major downgrade rather than a clean fix.

References: [uv locked sync](https://docs.astral.sh/uv/concepts/projects/sync/),
[PM2 ecosystem configuration](https://pm2.keymetrics.io/docs/usage/application-declaration/),
[PM2 startup persistence](https://pm2.keymetrics.io/docs/usage/startup/).
