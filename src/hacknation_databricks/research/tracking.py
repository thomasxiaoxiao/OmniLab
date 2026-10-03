"""Optional MLflow export of a verified run; never needed to run experiments."""

import json
from pathlib import Path
from urllib.parse import urlsplit

from .artifacts import verify_artifacts


def log_to_mlflow(directory: Path, tracking_uri: str, experiment: str) -> str:
    failures = verify_artifacts(directory)
    if failures:
        raise ValueError("Refusing to log a run with damaged artifacts")
    parsed = urlsplit(tracking_uri)
    if parsed.username or parsed.password:
        raise ValueError("Supply tracking credentials through the environment, not the URI")
    try:
        import mlflow
    except ImportError:
        raise RuntimeError("Install tracking support: uv sync --locked --extra tracking") from None

    report = json.loads((directory / "report.json").read_text())
    config = json.loads((directory / "config.json").read_text())
    environment = json.loads((directory / "environment.json").read_text())
    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment(experiment)
    with mlflow.start_run(run_name=directory.name) as run:
        mlflow.log_params({key: json.dumps(value) for key, value in config.items()})
        mlflow.set_tags(
            {
                "research.backend": report["backend"],
                "research.status": report["status"],
                "research.scientific_novelty": "unverified",
                "research.code_sha256": environment["code_sha256"],
                "research.source_kind": report["source_kind"],
            }
        )
        metrics = {f"acceptance.{key}": float(value) for key, value in report["acceptance"].items()}
        metrics["computed_simulations"] = report["computed_simulations"]
        mlflow.log_metrics(metrics)
        for result in report["rounds"]:
            for check in result["effect"]["checks"]:
                mlflow.log_metric(
                    f"wrapping_effect.L{check['size']}", check["difference"], step=result["round"]
                )
        mlflow.log_artifacts(str(directory.resolve()), artifact_path="research")
        return run.info.run_id
