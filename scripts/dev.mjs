import { spawn } from "node:child_process";

const children = [];
let stopping = false;
function stop(signal = "SIGTERM") {
  if (stopping) return;
  stopping = true;
  for (const child of children) if (child.exitCode === null) child.kill(signal);
}
for (const [cmd, args, env] of [
  [
    "uv",
    ["run", "--locked", "python", "-m", "omnilab"],
    { APP_PORT: "8011", APP_HOST: "127.0.0.1" },
  ],
  [
    process.execPath,
    ["node_modules/vite/bin/vite.js", "--config", "frontend/vite.config.ts"],
    {},
  ],
]) {
  const child = spawn(cmd, args, {
    stdio: "inherit",
    env: { ...process.env, ...env },
  });
  children.push(child);
  child.on("error", (error) => {
    console.error(error.message);
    process.exitCode = 1;
    stop();
  });
  child.on("exit", (code) => {
    if (!stopping) {
      process.exitCode = code || 0;
      stop();
    }
  });
}
process.on("SIGINT", () => stop("SIGINT"));
process.on("SIGTERM", () => stop());
