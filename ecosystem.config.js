const fs = require("node:fs");
const path = require("node:path");

const root = process.env.PROJECT_ROOT || __dirname;
const runtime = path.join(root, ".runtime");
const currentFile = path.join(runtime, "current.json");
const current = fs.existsSync(currentFile)
  ? JSON.parse(fs.readFileSync(currentFile, "utf8"))
  : null;
const appDir = process.env.APP_DIR || (current && current.path) || root;
const revision = process.env.APP_REVISION || (current && current.revision) || "development";
fs.mkdirSync(path.join(runtime, "logs"), { recursive: true });

module.exports = {
  apps: [
    {
      name: "omnilab-app",
      cwd: appDir,
      script: path.join(appDir, ".venv", "bin", "python"),
      args: ["-m", fs.existsSync(path.join(appDir, "src", "omnilab")) ? "omnilab" : "hacknation_databricks"],
      interpreter: "none",
      exec_mode: "fork",
      instances: 1,
      autorestart: true,
      watch: false,
      min_uptime: "10s",
      max_restarts: 10,
      exp_backoff_restart_delay: 1000,
      kill_timeout: 10000,
      max_memory_restart: "512M",
      out_file: path.join(runtime, "logs", "api-out.log"),
      error_file: path.join(runtime, "logs", "api-error.log"),
      time: true,
      env: {
        PYTHONUNBUFFERED: "1",
        APP_ENV_FILE: path.join(root, ".env"),
        APP_REVISION: revision,
        APP_DIR: appDir,
      },
    },
    {
      name: "omnilab-cd",
      cwd: root,
      script: path.join(root, "scripts", "deploy.py"),
      interpreter: process.env.DEPLOY_PYTHON || "python3",
      args: ["--watch"],
      autorestart: true,
      exp_backoff_restart_delay: 5000,
      kill_timeout: 30000,
      out_file: path.join(runtime, "logs", "cd-out.log"),
      error_file: path.join(runtime, "logs", "cd-error.log"),
      time: true,
      env: {
        PYTHONUNBUFFERED: "1",
        PROJECT_ROOT: root,
        PM2_HOME: path.join(runtime, "pm2"),
      },
    },
  ],
};
