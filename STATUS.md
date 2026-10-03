# Infrastructure setup

Last verified: October 3, 2026, 12:17 PDT. Approximately 11 hours 50 minutes remain
until the application implementation deadline recorded in `AGENTS.md`.

Scope of this setup: GitHub remote, uv environment, PM2 process management, and
continuous deployment. The application pipeline is not implemented by this task.

- Completed locally: Python 3.12 environment and lockfile, Streamlit entry point,
  local PM2 dependency, isolated release deployment with CI gating and rollback,
  CI workflow, issue/PR templates, and macOS login-service installer.
- Infrastructure setup complete: private GitHub remote published, all 12 tests and
  GitHub CI passing, PM2 app and deployment worker online, and macOS login service
  installed. The first approved main release was verified in the browser and over HTTP.
- Running app: http://127.0.0.1:8010. Continuous deployment polls `main` every 60 seconds.
- Verification: [successful main CI run](https://github.com/thomasxiaoxiao/hacknation-databricks/actions/runs/37147272148).
- Next application work: follow `AGENTS.md` for organizer asset intake and the
  extraction/evaluation implementation.
- Blockers: none for infrastructure. Databricks/model credentials and starter data
  are not configured by this scaffold.
- Known limitation: PM2's upstream dependency tree still has npm audit findings;
  see `docs/deployment.md`. Local hosting requires the Mac to be awake and logged in.
