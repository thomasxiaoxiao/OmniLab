"""Reproducible, credential-free CLI plus an explicit live Omnigent mode."""

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from importlib.resources import files
from pathlib import Path

import yaml
from dotenv import load_dotenv

from .artifacts import verify_artifacts
from .models import RunConfig
from .sources import fetch_arxiv, read_source
from .workflow import run_research


def fixture_source() -> Path:
    return Path(str(files("hacknation_databricks.research") / "assets/seed_excerpt.txt"))


def default_source() -> Path:
    return Path("data/papers/2607.24975v1.pdf")


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="Bounded percolation research workflow")
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("prepare-model", help="Download and hash the pinned local decision model")
    fetch = commands.add_parser("fetch", help="Fetch a version-pinned public arXiv PDF")
    fetch.add_argument("--arxiv-id", default="2607.24975v1")
    fetch.add_argument("--destination", type=Path, default=Path("data/papers"))
    run = commands.add_parser("run", help="Execute the strict research workflow")
    run.add_argument("--backend", choices=["anyjev", "omnigent"], default="anyjev")
    run.add_argument("--paper", type=Path, default=default_source())
    run.add_argument("--literature", type=Path, action="append", default=[])
    run.add_argument("--config", type=Path)
    run.add_argument("--output", type=Path)
    run.add_argument("--cache", type=Path, default=Path(".cache/simulations"))
    run.add_argument("--no-cache", action="store_true")
    run.add_argument(
        "--no-auto-literature", action="store_true", help="Disable bounded cited-arXiv retrieval"
    )
    verify = commands.add_parser("verify", help="Verify all saved artifact hashes")
    verify.add_argument("directory", type=Path)
    doctor = commands.add_parser("doctor", help="Validate environment and native Omnigent specs")
    doctor.add_argument("--spec", type=Path, default=Path("agents/research-worker"))
    configure = commands.add_parser("configure-agent", help="Prepare an Omnigent worker bundle")
    configure.add_argument("--model", help="Defaults to your Codex model for subscription auth")
    configure.add_argument("--auth", choices=["subscription", "api-key"], default="subscription")
    configure.add_argument("--reasoning-effort", default="medium")
    configure.add_argument("--databricks-profile")
    configure.add_argument("--output", type=Path, default=Path("agents/local"))
    tracking = commands.add_parser("log-mlflow", help="Log a verified run to an MLflow experiment")
    tracking.add_argument("directory", type=Path)
    tracking.add_argument("--tracking-uri", required=True)
    tracking.add_argument("--experiment", default="research-validation")
    return root


def main(argv: list[str] | None = None) -> int:
    load_dotenv(os.environ.get("APP_ENV_FILE", ".env"))
    load_dotenv(".runtime/research.env")
    args = parser().parse_args(argv)
    try:
        if args.command == "prepare-model":
            from .decision_runtime import prepare_model

            print(prepare_model())
            return 0
        if args.command == "log-mlflow":
            from .tracking import log_to_mlflow

            print(log_to_mlflow(args.directory, args.tracking_uri, args.experiment))
            return 0
        if args.command == "configure-agent":
            import tomllib

            template = Path("agents/research-worker/config.yaml")
            data = yaml.safe_load(template.read_text())
            model = args.model or os.getenv("RESEARCH_MODEL")
            if not model and args.auth == "subscription":
                codex_config = (
                    Path(os.getenv("CODEX_HOME", str(Path.home() / ".codex"))) / "config.toml"
                )
                if codex_config.exists():
                    model = tomllib.loads(codex_config.read_text()).get("model")
            if not model:
                raise ValueError("Specify --model or RESEARCH_MODEL")
            data["executor"]["model"] = data["llm"]["model"] = model
            data["executor"]["reasoning_effort"] = args.reasoning_effort
            data["executor"]["timeout"] = 300
            data["skills"] = "none"
            data["executor"]["config"]["harness"] = (
                "codex"
                if args.auth == "subscription" and not args.databricks_profile
                else "openai-agents"
            )
            if args.databricks_profile:
                data["executor"]["auth"] = {
                    "type": "databricks",
                    "profile": args.databricks_profile,
                }
                data["executor"]["config"]["use_responses"] = False
            args.output.mkdir(parents=True, exist_ok=True)
            target = args.output / "config.yaml"
            target.write_text(yaml.safe_dump(data, sort_keys=False))
            from omnigent.spec import load

            load(args.output)
            print(f"Prepared {args.output}; no credentials were written or tested.")
            return 0
        if args.command == "fetch":
            print(fetch_arxiv(args.arxiv_id, args.destination))
            return 0
        if args.command == "verify":
            failures = verify_artifacts(args.directory)
            print(json.dumps({"passed": not failures, "failures": failures}, indent=2))
            return 1 if failures else 0
        if args.command == "doctor":
            from omnigent.spec import load

            spec = load(args.spec, expand_env=False)
            print(
                json.dumps(
                    {
                        "spec_valid": True,
                        "agent": spec.name,
                        "live_server_configured": bool(os.getenv("OMNIGENT_SERVER_URL")),
                        "databricks_host_configured": bool(os.getenv("DATABRICKS_HOST")),
                        "model_configured": bool(os.getenv("RESEARCH_MODEL")),
                        "note": "Spec validation does not verify a model request or runner.",
                    },
                    indent=2,
                )
            )
            return 0
        config = (
            RunConfig.model_validate_json(args.config.read_text()) if args.config else RunConfig()
        )
        output = args.output or Path("output/research") / datetime.now(UTC).strftime(
            "%Y%m%dT%H%M%S%fZ"
        )
        source = read_source(args.paper)
        literature = [
            read_source(path, source_id=f"literature_{i}")
            for i, path in enumerate(args.literature, start=1)
        ]
        retrieval_report = None
        if args.backend == "omnigent" and not args.no_auto_literature:
            from .literature import retrieve_references

            print("Retrieve cited references for automated evaluation", file=sys.stderr, flush=True)
            retrieved, retrieval_report = retrieve_references(
                source, Path("data/literature"), existing=literature
            )
            literature.extend(retrieved)
        report = run_research(
            source,
            output,
            config,
            backend=args.backend,
            literature=literature,
            cache=None if args.no_cache else args.cache,
            progress=lambda message: print(message, file=sys.stderr, flush=True),
            retrieval_report=retrieval_report,
        )
        print(json.dumps({"output": str(output), **report}, indent=2))
        # A successful base simulation is distinct from achieving the novelty gate.
        successful = {
            "needs_literature_review",
            "candidate_for_human_review",
            "automated_candidate",
            "review_complete",
            "round_budget_exhausted",
        }
        return 0 if report["status"] in successful else 2
    except Exception as exc:
        # Provider bodies and environment values must never end up in CLI logs.
        print(
            f"Research command failed ({type(exc).__name__}). "
            "Check inputs/configuration and the saved run report.",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
