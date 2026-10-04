"""Strict contracts at the boundary between agents and executable science."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class RunConfig(Contract):
    workflow: Literal["sequential", "adaptive", "repository"] = "sequential"
    decision_backend: Literal["codex", "anyjev"] = "codex"
    repository_url: str = Field(default="", max_length=300)
    allow_paper_implementation: bool = False
    repository_ref: str = Field(default="HEAD", max_length=100)
    research_areas: list[str] = Field(default_factory=list, max_length=3)
    code_timeout_seconds: int = Field(default=60, ge=1, le=180)
    domain: Literal["auto", "percolation", "astrosat"] = "percolation"
    seed: int = Field(default=20261003, ge=0, le=2**32 - 1)
    sizes: list[int] = Field(default_factory=lambda: [16, 32], min_length=2, max_length=4)
    trials: int = Field(default=128, ge=8, le=4096)
    max_rounds: int = Field(default=8, ge=1, le=32)
    max_workers: int = Field(default=6, ge=1, le=16)
    max_agent_calls: int = Field(default=96, ge=1, le=512)
    max_agent_retries: int = Field(default=1, ge=0, le=2)
    max_decision_calls: int = Field(default=32, ge=1, le=64)
    agent_timeout_seconds: int = Field(default=120, ge=1, le=600)
    max_seconds: int = Field(default=3600, ge=1, le=21600)
    max_simulations: int = Field(default=100000, ge=16, le=1000000)
    goal_min_batches: int = Field(default=2, ge=2, le=32)
    goal_max_interval_width: float = Field(default=0.25, gt=0, le=0.5)
    finite_size_tolerance: float = Field(default=0.12, gt=0, le=0.2)
    minimum_effect: float = Field(default=0.05, gt=0, le=0.5)
    preferred_experiment: (
        Literal["random_manhattan", "site_percolation", "resistor_diode"] | None
    ) = None

    @field_validator("sizes")
    @classmethod
    def even_sizes(cls, values: list[int]) -> list[int]:
        if len(set(values)) != len(values) or any(v < 4 or v > 128 or v % 2 for v in values):
            raise ValueError("Use distinct even lattice sizes between 4 and 128")
        return sorted(values)


class Evidence(Contract):
    source_id: str = "seed"
    page: int = Field(ge=1)
    quote: str = Field(min_length=8, max_length=600)


class ResearchContext(Contract):
    research_question: str = Field(min_length=10, max_length=1500)
    summary: str = Field(min_length=10, max_length=3000)
    domain: Literal["percolation", "astrosat", "unsupported"]
    rationale: str = Field(min_length=10, max_length=1500)
    evidence: list[Evidence] = Field(min_length=1, max_length=3)


class PaperDirection(Contract):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,39}$")
    title: str = Field(min_length=5, max_length=200)
    hypothesis: str = Field(min_length=10, max_length=1200)
    origin: Literal["paper_suggestion", "agent_hypothesis"]
    evidence: list[Evidence] = Field(min_length=1, max_length=4)


class PaperBrief(Contract):
    """Paper-first research; no preset domain, metric, or experiment choices."""

    research_question: str = Field(min_length=10, max_length=1500)
    summary: str = Field(min_length=10, max_length=3000)
    directions: list[PaperDirection] = Field(max_length=3)
    search_scope: str = Field(min_length=10, max_length=1200)
    missing_evidence: list[str] = Field(max_length=8)

    @field_validator("directions")
    @classmethod
    def unique_directions(cls, values):
        if len({value.id for value in values}) != len(values):
            raise ValueError("Paper direction IDs must be unique")
        return values


class Proposal(Contract):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,39}$")
    title: str = Field(min_length=5, max_length=200)
    hypothesis: str = Field(min_length=10, max_length=1000)
    experiment: Literal["random_manhattan", "site_percolation", "resistor_diode"]
    evidence: Evidence


class ProposalBatch(Contract):
    proposals: list[Proposal] = Field(min_length=1, max_length=3)

    @field_validator("proposals")
    @classmethod
    def unique_proposals(cls, proposals: list[Proposal]) -> list[Proposal]:
        if len({p.id for p in proposals}) != len(proposals):
            raise ValueError("Proposal IDs must be unique")
        if len({p.experiment for p in proposals}) != len(proposals):
            raise ValueError("Do not repeat an experiment as a new proposal")
        return proposals


class Critique(Contract):
    proposal_id: str
    decision: Literal["accept", "reject", "defer"]
    rationale: str = Field(min_length=10, max_length=2000)
    risks: list[str] = Field(min_length=1, max_length=8)


class CritiqueBatch(Contract):
    selected_proposal_id: str | None = None
    critiques: list[Critique] = Field(min_length=1, max_length=3)


class LiteratureReview(Contract):
    assessment: Literal["unverified", "known_overlap", "candidate_gap"]
    sources: list[Evidence] = Field(min_length=1, max_length=8)
    reasoning: str = Field(min_length=10, max_length=3000)
    # Source-backed gap assessment is distinct from a global novelty claim.
    search_scope: str = Field(min_length=5, max_length=1000)


class ExperimentPlan(Contract):
    proposal_id: str
    experiment: Literal["random_manhattan", "site_percolation", "resistor_diode"]
    rationale: str = Field(min_length=10, max_length=1500)


class ValidationReview(Contract):
    decision: Literal["supported", "inconclusive", "reject"]
    reasoning: str = Field(min_length=10, max_length=3000)
    limitations: list[str] = Field(min_length=1, max_length=8)


class Contribution(Contract):
    original_work: str = Field(min_length=10, max_length=1200)
    followup_work: str = Field(min_length=10, max_length=1200)
    added_value: str = Field(min_length=10, max_length=1200)
    evidence: list[Evidence] = Field(min_length=1, max_length=4)


class NoveltyReview(Contract):
    verdict: Literal[
        "candidate_contribution", "incremental_extension", "known_overlap", "not_demonstrated"
    ]
    rationale: str = Field(min_length=10, max_length=3000)
    comparisons: list[Contribution] = Field(min_length=1, max_length=4)
    reviewed_source_ids: list[str] = Field(min_length=1, max_length=8)
    limitations: list[str] = Field(min_length=1, max_length=8)
    next_experiment: str = Field(min_length=10, max_length=1500)


class TestAssessment(Contract):
    test_id: Literal["screen", "precision"]
    expected_learning: str = Field(min_length=10, max_length=600)
    feasibility: str = Field(min_length=10, max_length=600)


class DiscoveryPlan(ExperimentPlan):
    tests: list[TestAssessment] = Field(min_length=2, max_length=2)
    selected_test_id: Literal["screen", "precision"]

    @field_validator("tests")
    @classmethod
    def compare_both_tests(cls, tests: list[TestAssessment]) -> list[TestAssessment]:
        if {test.test_id for test in tests} != {"screen", "precision"}:
            raise ValueError("Compare both screen and precision tests exactly once")
        return tests


class NextDecision(Contract):
    action: Literal["repeat", "literature", "stop"]
    result_interpretation: str = Field(min_length=10, max_length=1500)
    rationale: str = Field(min_length=10, max_length=1500)
    next_experiment: str = Field(min_length=10, max_length=1500)


class ResearchDirection(Contract):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,39}$")
    title: str = Field(min_length=5, max_length=200)
    hypothesis: str = Field(min_length=10, max_length=1200)
    experiment: Literal[
        "random_manhattan",
        "site_percolation",
        "resistor_diode",
        "transit_margin_1",
        "transit_margin_2",
        "transit_margin_3",
    ]
    origin: Literal["paper_suggestion", "agent_hypothesis"]
    evidence: list[Evidence] = Field(min_length=1, max_length=4)


class ResearchBrief(Contract):
    directions: list[ResearchDirection] = Field(max_length=3)
    search_scope: str = Field(min_length=10, max_length=1200)
    missing_evidence: list[str] = Field(max_length=8)


class PortfolioSelection(Contract):
    critiques: list[Critique] = Field(min_length=1, max_length=24)
    invest: list[str] = Field(max_length=3)
    rationale: str = Field(min_length=10, max_length=2000)


class BranchPlan(Contract):
    branch_id: str
    experiment: str
    tests: list[TestAssessment] = Field(min_length=2, max_length=2)
    selected_test_id: Literal["screen", "precision"]
    rationale: str = Field(min_length=10, max_length=1500)

    @field_validator("tests")
    @classmethod
    def compare_tests(cls, tests):
        return DiscoveryPlan.compare_both_tests(tests)


class InvestmentDecision(Contract):
    action: Literal["invest", "finalize", "stop"]
    invest: list[str] = Field(max_length=3)
    goal_branch_id: str | None = None
    result_interpretation: str = Field(min_length=10, max_length=2000)
    rationale: str = Field(min_length=10, max_length=2000)
    next_experiment: str = Field(min_length=10, max_length=1500)
    missing_evidence: list[str] = Field(max_length=8)
