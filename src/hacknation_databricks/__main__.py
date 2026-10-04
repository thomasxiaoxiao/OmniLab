"""Start the React UI and Python API as one local, PM2-compatible service."""

import os

import uvicorn
from dotenv import load_dotenv


def main() -> None:
    load_dotenv(os.environ.get("APP_ENV_FILE", ".env"))
    uvicorn.run(
        "hacknation_databricks.web.server:app",
        host=os.environ.get("APP_HOST", "127.0.0.1"),
        port=int(os.environ.get("APP_PORT", "8010")),
        workers=1,
    )


if __name__ == "__main__":
    main()
