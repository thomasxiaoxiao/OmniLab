"""Domain-independent contracts for paper + directions + simulation repository."""

from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator

from .models import Contract, Critique, Evidence, ParameterSweep


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
    repository_files: list[str] = Field(max_length=12)


class RepositoryReview(Contract):
    critiques: list[Critique] = Field(min_length=1, max_length=3)
    selected_proposal_id: str | None
    literature_assessment: str = Field(min_length=10, max_length=3000)
    search_scope: str = Field(min_length=10, max_length=1500)
    evidence: list[Evidence] = Field(min_length=1, max_length=8)
    missing_evidence: list[str] = Field(min_length=1, max_length=8)
    history_assessment: str = ""


class ExplorationRepositoryReview(RepositoryReview):
    history_assessment: str = Field(min_length=20, max_length=1200)


class RepositoryLiterature(Contract):
    literature_assessment: str = Field(min_length=10, max_length=3000)
    search_scope: str = Field(min_length=10, max_length=1500)
    evidence: list[Evidence] = Field(min_length=1, max_length=8)
    missing_evidence: list[str] = Field(min_length=1, max_length=8)


class RepositoryTest(Contract):
    id: Literal["screen", "precision"]
    replicates: int = Field(ge=4, le=32)
    expected_learning: str = Field(min_length=10, max_length=1000)
    feasibility: str = Field(min_length=10, max_length=1000)


class RepositoryFollowup(Contract):
    question: str = Field(min_length=10, max_length=300)
    treatment: dict
    expected_learning: str = Field(min_length=10, max_length=500)


class RepositoryLearningDesign(Contract):
    verification_only: bool = Field(
        description="True if the primary outcome only verifies an identity, conversion, or "
        "target used to construct the treatment. Such checks belong in sanity, not research."
    )
    unresolved_question: str = Field(min_length=20, max_length=600)
    outcome_rationale: str = Field(
        min_length=20,
        max_length=1000,
        description="Explain why the primary metric is not fixed by an imposed target or "
        "algebraic identity, what can falsify the hypothesis, and what the seeds actually vary.",
    )
    followups: list[RepositoryFollowup] = Field(max_length=2)


class ScenarioComparison(Contract):
    baseline_label: str = Field(min_length=3, max_length=80)
    proposed_label: str = Field(min_length=3, max_length=80)
    difference: str = Field(min_length=20, max_length=300)
    held_constant: str = Field(min_length=10, max_length=240)


class RepositoryPlan(Contract):
    proposal_id: str
    hypothesis: str = Field(min_length=10, max_length=1500)
    tests: list[RepositoryTest] = Field(min_length=2, max_length=2)
    selected_test_id: Literal["screen", "precision"]
    rationale: str = Field(min_length=10, max_length=1500)
    visualization_options: list[str] = Field(default_factory=list, max_length=3)
    visualization_plan: str = Field(default="", max_length=2000)
    primary_module: str = Field(pattern=r"^[a-zA-Z_][a-zA-Z0-9_]*$")
    # PyPI wheel names only; no URLs, shell, editable installs or build scripts.
    dependencies: list[
        Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*(?:==[A-Za-z0-9_.+!-]+)?$")]
    ] = Field(
        min_length=1,
        max_length=20,
        description="Package names only: numpy, scipy, ephem, or primary_module. No source paths, "
        "function names or explanatory prose. Standard-library modules need not be listed.",
    )
    metric: str = Field(min_length=3, max_length=200)
    units: str = Field(min_length=1, max_length=100)
    trajectory_label: str | None = Field(default=None, min_length=1, max_length=200)
    trajectory_units: str | None = Field(default=None, min_length=1, max_length=100)
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
    learning_design: RepositoryLearningDesign | None = None
    comparison: ScenarioComparison | None = None
    sweep: ParameterSweep | None = None
    history_difference: str = ""

    @model_validator(mode="after")
    def coherent(self):
        import math

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
        if not self.baseline or any(
            set(parameters) != set(self.baseline) for parameters in (self.treatment, self.sanity)
        ):
            raise ValueError(
                "Baseline, treatment and sanity must supply the same complete parameter keys; "
                "prose-only inherited configurations are not executable"
            )
        return self


class AgentRepositoryPlan(RepositoryPlan):
    """New runs must explain representation choices; old plans remain readable."""

    visualization_options: list[str] = Field(min_length=2, max_length=3)
    visualization_plan: str = Field(min_length=30, max_length=2000)
    learning_design: RepositoryLearningDesign

    @model_validator(mode="after")
    def informative(self):
        design = self.learning_design
        if design.verification_only:
            raise ValueError(
                "An algebraic identity or target-construction check is not the primary research "
                "experiment. Keep it as sanity and test an unresolved consequence of the "
                "reviewed hypothesis, with the metric and thresholds defined before execution."
            )
        if not design.followups:
            raise ValueError("Plan at least one informative parameter follow-up before execution")
        prior = [self.baseline, self.treatment]
        for followup in design.followups:
            if set(followup.treatment) != set(self.baseline) or followup.treatment in prior:
                raise ValueError("Planned follow-ups need distinct, complete treatment parameters")
            prior.append(followup.treatment)
        return self


class ExplorationRepositoryPlan(AgentRepositoryPlan):
    comparison: ScenarioComparison
    history_difference: str = Field(min_length=20, max_length=1000)

    @model_validator(mode="after")
    def complete_sweep(self):
        import math

        if self.sweep:
            sweep = self.sweep
            if not math.isfinite(sweep.lower + sweep.upper) or sweep.lower >= sweep.upper:
                raise ValueError("Sweep endpoints must be finite and ordered")
            for parameters in [
                self.baseline,
                self.treatment,
                *[f.treatment for f in self.learning_design.followups],
            ]:
                values = parameters.get(sweep.parameter)
                if (
                    not isinstance(values, list)
                    or not 2 <= len(values) <= 120
                    or any(type(v) not in (int, float) or not math.isfinite(v) for v in values)
                    or values[0] != sweep.lower
                    or values[-1] != sweep.upper
                    or any(b <= a for a, b in zip(values, values[1:], strict=False))
                ):
                    raise ValueError(
                        "Every comparison/follow-up sweep must include both "
                        "declared endpoints in strictly increasing order"
                    )
                self.validate_sweep(parameters)
        return self

    def validate_sweep(self, parameters):
        if self.sweep and parameters.get(self.sweep.parameter) != self.baseline.get(
            self.sweep.parameter
        ):
            raise ValueError(
                "Comparison and follow-up must preserve the complete baseline sweep grid"
            )


class RepositoryImplementation(Contract):
    python_code: str = Field(min_length=50, max_length=64000)
    c_code: str = Field(default="", max_length=64000)
    c_repository_files: list[str] = Field(default_factory=list, max_length=8)
    explanation: str = Field(min_length=10, max_length=4000)
    repository_files: list[str] = Field(max_length=12)


class RepositoryDecision(Contract):
    action: Literal["followup", "precision", "stop"]
    result_interpretation: str = Field(min_length=10, max_length=2000)
    rationale: str = Field(min_length=10, max_length=1500)
    next_experiment: str = Field(min_length=10, max_length=1500)
    next_treatment: dict | None
    limitations: list[str] = Field(min_length=1, max_length=8)


class AgentRepositoryDecision(RepositoryDecision):
    """Concise new responses; historical decisions retain their original contract."""

    next_experiment: str = Field(
        min_length=10,
        max_length=140,
        description="One plain action sentence, at most 20 words and 140 characters. "
        "State the test and what changes. Put conditions and rationale in rationale.",
    )

    @field_validator("next_experiment")
    @classmethod
    def short_action(cls, value):
        import re

        if len(value.split()) > 20 or "\n" in value or len(re.findall(r"[.!?](?:\s|$)", value)) > 1:
            raise ValueError("Next experiment must be one sentence of at most 20 words")
        return value
