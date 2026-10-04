"""Live research entry point: paper evidence, agent-written code, executed results."""

from .models import RunConfig


def run_research(
    source,
    output,
    config=None,
    backend="omnigent",
    literature=None,
    cache=None,
    progress=None,
    roles_factory=None,
    retrieval_report=None,
):
    config = config or RunConfig(
        workflow="repository", domain="auto", allow_paper_implementation=True
    )
    if config.workflow != "repository":
        raise ValueError(
            "Preset experiment workflows are retired. Use the agent-generated repository workflow."
        )
    from .repository_workflow import run_repository

    return run_repository(
        source,
        output,
        config,
        backend=backend,
        literature=literature,
        progress=progress,
        roles_factory=roles_factory,
        retrieval_report=retrieval_report,
    )
