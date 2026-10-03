# Infrastructure setup

Scope of this setup: GitHub remote, uv environment, PM2 process management, and
continuous deployment. The application pipeline is not implemented by this task.

- Completed locally: Python 3.12 environment and lockfile, Streamlit entry point,
  local PM2 dependency, isolated release deployment with CI gating and rollback,
  CI workflow, issue/PR templates, and macOS login-service installer.
- Current task: publish the initial repository, verify GitHub CI, start deployment,
  and check the running app.
- Next application work: follow `AGENTS.md` for organizer asset intake and the
  extraction/evaluation implementation.
- Blockers: none for infrastructure. Databricks/model credentials and starter data
  are not configured by this scaffold.
- Known limitation: PM2's upstream dependency tree still has npm audit findings;
  see `docs/deployment.md`. Local hosting requires the Mac to be awake and logged in.
