"""Start the PM2-managed HTTP service."""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from streamlit.web import cli


def main() -> None:
    load_dotenv(os.environ.get("APP_ENV_FILE", ".env"))
    sys.argv = [
        "streamlit",
        "run",
        str(Path(__file__).with_name("ui.py")),
        "--server.address",
        os.environ.get("APP_HOST", "127.0.0.1"),
        "--server.port",
        os.environ.get("APP_PORT", "8010"),
        "--server.headless",
        "true",
        "--browser.gatherUsageStats",
        "false",
        "--server.fileWatcherType",
        "none",
    ]
    cli.main()


if __name__ == "__main__":
    main()
