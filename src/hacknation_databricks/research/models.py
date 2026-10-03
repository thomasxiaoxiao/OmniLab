"""Strict contracts at the boundary between agents and executable science."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class RunConfig(Contract):
    seed: int = Field(default=20261003, ge=0, le=2**32 - 1)
    sizes: list[int] = Field(default_factory=lambda: [16, 32], min_length=2, max_length=4)
    trials: int = Field(default=128, ge=8, le=4096)
    max_rounds: int = Field(default=2, ge=1, le=4)
    max_workers: int = Field(default=2, ge=1, le=4)
    max_agent_calls: int = Field(default=16, ge=1, le=32)
    max_decision_calls: int = Field(default=32, ge=1, le=64)
    agent_timeout_seconds: int = Field(default=120, ge=1, le=600)
    max_seconds: int = Field(default=300, ge=1, le=3600)
    max_simulations: int = Field(default=20000, ge=16, le=200000)
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
