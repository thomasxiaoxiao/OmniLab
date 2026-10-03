#!/usr/bin/env python3
"""Install this checkout's PM2 login service on macOS."""

import os
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path


def main() -> None:
    if sys.platform != "darwin":
        raise SystemExit("This helper supports macOS; use PM2 startup on Linux.")
    root = Path(__file__).resolve().parents[1]
    runtime = root / ".runtime"
    dump = runtime / "pm2/dump.pm2"
    if not dump.exists():
        raise SystemExit("Start the app/worker and run npm run save first.")
    binaries = {name: shutil.which(name) for name in ("node", "uv", "gh", "git", "python3")}
    if not all(binaries.values()):
        raise SystemExit("Node, uv, gh, Git, and Python must be on PATH.")
    paths = list(dict.fromkeys(str(Path(value).parent) for value in binaries.values()))
    paths += ["/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/bin", "/usr/sbin", "/sbin"]
    label = "com.hacknation.databricks.pm2"
    target = Path.home() / "Library/LaunchAgents" / f"{label}.plist"
    payload = {
        "Label": label,
        "ProgramArguments": [
            binaries["node"],
            str(root / "node_modules/pm2/bin/pm2"),
            "resurrect",
            "--no-daemon",
        ],
        "WorkingDirectory": str(root),
        "EnvironmentVariables": {
            "PATH": ":".join(paths),
            "PM2_HOME": str(runtime / "pm2"),
            "PROJECT_ROOT": str(root),
            "DEPLOY_PYTHON": binaries["python3"],
        },
        "RunAtLoad": True,
        "KeepAlive": True,
        "ThrottleInterval": 30,
        "StandardOutPath": str(runtime / "logs/launchd-out.log"),
        "StandardErrorPath": str(runtime / "logs/launchd-error.log"),
    }
    if "DEPLOY_HEALTH_URL" in os.environ:
        payload["EnvironmentVariables"]["DEPLOY_HEALTH_URL"] = os.environ["DEPLOY_HEALTH_URL"]
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(plistlib.dumps(payload))
    domain = f"gui/{os.getuid()}"
    loaded = subprocess.run(
        ["launchctl", "print", f"{domain}/{label}"], capture_output=True, check=False
    )
    if loaded.returncode == 0:
        subprocess.run(["launchctl", "bootout", f"{domain}/{label}"], check=True)
    subprocess.run(["launchctl", "bootstrap", domain, str(target)], check=True)
    print(f"Installed {target}")


if __name__ == "__main__":
    main()
