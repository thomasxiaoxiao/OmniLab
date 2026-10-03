"""Domain-independent contracts for paper + directions + simulation repository."""

from typing import Literal

from pydantic import Field, model_validator

from .models import Contract, Critique, Evidence


class RepositoryDirection(Contract):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,39}$")
    title: str = Field(min_length=5, max_length=200)
    hypothesis: str = Field(min_length=10, max_length=1200)
    origin: Literal["paper_suggestion", "agent_hypothesis", "user_suggestion"]
    evidence: list[Evidence] = Field(min_length=1, max_length=3)


class RepositoryBrief(Contract):
    research_question: str = Field(min_length=10, max_length=1200)
    directions: list[RepositoryDirection] = Field(min_length=1, max_length=3)
    repository_fit: str = Field(min_length=10, max_length=2000)
    version_limitations: list[str] = Field(min_length=1, max_length=8)


class RepositoryReview(Contract):
    critiques: list[Critique] = Field(min_length=1, max_length=3)
    selected_proposal_id: str | None
    literature_assessment: str = Field(min_length=10, max_length=3000)
    search_scope: str = Field(min_length=10, max_length=1500)
    evidence: list[Evidence] = Field(min_length=1, max_length=8)
    missing_evidence: list[str] = Field(min_length=1, max_length=8)


class RepositoryTest(Contract):
    id: Literal["screen", "precision"]
    replicates: int = Field(ge=4, le=32)
    expected_learning: str = Field(min_length=10, max_length=1000)
    feasibility: str = Field(min_length=10, max_length=1000)


class RepositoryPlan(Contract):
    proposal_id: str
    hypothesis: str = Field(min_length=10, max_length=1500)
    tests: list[RepositoryTest] = Field(min_length=2, max_length=2)
    selected_test_id: Literal["screen", "precision"]
    rationale: str = Field(min_length=10, max_length=1500)
    primary_module: str = Field(pattern=r"^[a-zA-Z_][a-zA-Z0-9_]*$")
    # PyPI wheel names only; no URLs, shell, editable installs or build scripts.
    dependencies: list[str] = Field(min_length=1, max_length=20)
    metric: str = Field(min_length=3, max_length=200)
    units: str = Field(min_length=1, max_length=100)
    metric_lower: float
    metric_upper: float
    baseline: dict
    treatment: dict
    sanity: dict
    sanity_expected: float
    sanity_tolerance: float = Field(ge=0)
    baseline_scope: str = Field(min_length=10, max_length=1500)
    controls: str = Field(min_length=10, max_length=1500)
    meaningful_difference: float = Field(gt=0)
    limitations: list[str] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def coherent(self):
        import math
        import re

        if {t.id for t in self.tests} != {"screen", "precision"}:
            raise ValueError("Compare screening and precision tests exactly once")
        values = [
            self.metric_lower,
            self.metric_upper,
            self.sanity_expected,
            self.sanity_tolerance,
            self.meaningful_difference,
        ]
        if not all(math.isfinite(x) for x in values) or self.metric_lower >= self.metric_upper:
            raise ValueError("Metrics need finite ordered bounds")
        if not self.metric_lower <= self.sanity_expected <= self.metric_upper:
            raise ValueError("Sanity expectation outside metric bounds")
        if self.baseline == self.treatment:
            raise ValueError("Follow-up must change an experimental parameter")
        if any(
            not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*(?:==[A-Za-z0-9_.+!-]+)?", d)
            for d in self.dependencies
        ):
            raise ValueError("Use PyPI wheel package names or exact version pins")
        return self


class RepositoryImplementation(Contract):
    python_code: str = Field(min_length=50, max_length=16000)
    explanation: str = Field(min_length=10, max_length=2000)
    repository_files: list[str] = Field(min_length=1, max_length=12)


class RepositoryDecision(Contract):
    action: Literal["followup", "stop"]
    result_interpretation: str = Field(min_length=10, max_length=2000)
    rationale: str = Field(min_length=10, max_length=1500)
    next_experiment: str = Field(min_length=10, max_length=1500)
    next_treatment: dict | None
    limitations: list[str] = Field(min_length=1, max_length=8)
