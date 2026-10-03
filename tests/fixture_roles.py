"""Deterministic test doubles. Never imported by the application."""

import time

from hacknation_databricks.research.agents import PROMPT_VERSION, AgentBudgetExceeded, T
from hacknation_databricks.research.artifacts import RunStore
from hacknation_databricks.research.models import RunConfig
from hacknation_databricks.research.sources import Source


class FixtureRoles:
    name = "fixture"
    calls = 0

    def __init__(self, sources: list[Source], store: RunStore, config: RunConfig):
        self.sources, self.store, self.config = sources, store, config
        self.calls = 0
        self.deadline = time.monotonic() + config.max_seconds

    def ask(self, role: str, payload: dict, contract: type[T]) -> T:
        if self.calls >= self.config.max_agent_calls:
            raise AgentBudgetExceeded("Role call budget exhausted")
        self.calls += 1
        result = self._respond(role, payload)
        self.store.write(
            f"roles/{self.calls:02d}-{role}.json",
            {
                "backend": self.name,
                "prompt_version": PROMPT_VERSION,
                "input": payload,
                "output": result,
                "usage": {"model_calls": 0},
            },
        )
        if role == "planner" and "tests" in contract.model_fields and "tests" not in result:
            result.update(
                selected_test_id="screen",
                tests=[
                    {
                        "test_id": name,
                        "expected_learning": "Estimate finite-size wrapping effect.",
                        "feasibility": "Allowlisted simulation with bounded cost.",
                    }
                    for name in payload["test_options"]
                ],
            )
        return contract.model_validate(result)

    def _respond(self, role: str, payload: dict) -> dict:
        if role == "reader":
            candidates = [
                (
                    "random_manhattan",
                    "randomly-oriented Manhattan lattice",
                    "Randomized Manhattan street directions",
                    "Randomizing row and column directions changes finite-size wrapping rates.",
                ),
                (
                    "site_percolation",
                    "site (rather than bond) percolation",
                    "Site occupation on a Manhattan lattice",
                    "Replacing bond occupation with site occupation changes wrapping at fixed p.",
                ),
                (
                    "resistor_diode",
                    "resistor-diode lattices",
                    "Bidirectional bonds in a random diode lattice",
                    "Adding bidirectional bonds changes the finite-size wrapping probability.",
                ),
            ]
            proposals = []
            for experiment, phrase, title, hypothesis in candidates:
                pages = list(enumerate(self.sources[0].pages, start=1))
                pages.sort(key=lambda item: "could be extended" not in item[1])
                for page, text in pages:
                    if phrase in text:
                        proposals.append(
                            {
                                "id": experiment,
                                "title": title,
                                "hypothesis": hypothesis,
                                "experiment": experiment,
                                "evidence": {"source_id": "seed", "page": page, "quote": phrase},
                            }
                        )
                        break
            if not proposals:
                raise ValueError("Scripted reader supports only the documented percolation recipe")
            return {"proposals": proposals}
        if role == "critic":
            return {
                "selected_proposal_id": next(
                    (
                        p["id"]
                        for p in payload["proposals"]
                        if not payload.get("preferred_experiment")
                        or p["experiment"] == payload["preferred_experiment"]
                    ),
                    None,
                ),
                "critiques": [
                    {
                        "proposal_id": p["id"],
                        "decision": "accept",
                        "rationale": "The bounded simulator can test this source-backed direction.",
                        "risks": [
                            "Finite-size effects",
                            "Prior-art search is incomplete",
                            "Monte Carlo error",
                        ],
                    }
                    for p in payload["proposals"]
                ],
            }
        if role == "literature":
            return {
                "assessment": "unverified",
                "sources": [payload["proposal"]["evidence"]],
                "reasoning": "The seed suggests this extension but cites related prior work. "
                "Scripted matching cannot establish a research gap.",
                "search_scope": "Seed text only; no autonomous literature search performed.",
            }
        if role == "planner":
            extra = (
                {
                    "selected_test_id": "screen",
                    "tests": [
                        {
                            "test_id": name,
                            "expected_learning": "Estimate finite-size wrapping effect.",
                            "feasibility": "Allowlisted simulation with bounded cost.",
                        }
                        for name in payload["test_options"]
                    ],
                }
                if self.name == "omnigent"
                else {}
            )
            return {
                **extra,
                "proposal_id": payload["proposal"]["id"],
                "experiment": payload["proposal"]["experiment"],
                "rationale": "Use the simulator with recorded seeds and fixed parameters.",
            }
        if role == "validator":
            return {
                "decision": "supported" if payload["checks"]["passed"] else "inconclusive",
                "reasoning": "Deterministic checks and conservative Monte Carlo intervals "
                "were evaluated independently of the proposed narrative.",
                "limitations": [
                    "Small lattices",
                    "No global novelty verification",
                    "Scripted review",
                ],
            }
        if role == "next_decision":
            return {
                "action": "repeat",
                "result_interpretation": "The measured effect needs review.",
                "rationale": "Test fixture requests another bounded measurement.",
                "next_experiment": "Increase trials to inspect sampling uncertainty.",
            }
        if role == "novelty_evaluator":
            return {
                "verdict": "candidate_contribution",
                "rationale": "Synthetic evaluator response for a bounded integration test.",
                "comparisons": [
                    {
                        "original_work": "Synthetic original work used in a test.",
                        "followup_work": "Synthetic follow-up used in a test.",
                        "added_value": "No real scientific claim; integration fixture only.",
                        "evidence": [
                            {"source_id": s.source_id, "page": 1, "quote": s.pages[0][:40]}
                            for s in self.sources
                        ],
                    }
                ],
                "reviewed_source_ids": [s.source_id for s in self.sources],
                "limitations": ["Synthetic test only"],
                "next_experiment": "Run an actual live evaluation with real references.",
            }
        raise ValueError(f"Unknown role: {role}")


def run_fixture(source, output, config=None, **kwargs):
    from hacknation_databricks.research.workflow import run_research

    kwargs.setdefault("backend", "fixture")
    if kwargs["backend"] == "fixture":
        kwargs.setdefault("roles_factory", FixtureRoles)
    return run_research(source, output, config, **kwargs)


class DecisionWorkerFixture:
    """Protocol-level model double; never used by a production run."""

    def __init__(self, deadline, timeout):
        from hacknation_databricks.research.decision_runtime import MODEL_ID, MODEL_REVISION

        self.manifest = {"model": MODEL_ID, "revision": MODEL_REVISION, "files": {}}
        self.closed = False

    def decide(self, state, question, choices):
        from hacknation_databricks.research.decision_runtime import MODEL_ID, MODEL_REVISION

        if "passage_0" in choices:
            answer = "passage_0"
        elif "topic_only" in choices:
            answer = "supported"
        elif "accept" in choices:
            answer = "accept"
        elif "unverified" in choices:
            answer = "unverified"
        elif "execute" in choices:
            answer = "execute"
        elif "inconclusive" in choices:
            answer = "inconclusive"
        else:
            answer = list(choices)[-2]  # Last accepted, explicitly NOT first accepted.
        return {
            "answer": answer,
            "probabilities": {k: float(k == answer) for k in choices},
            "level": "L0",
            "calibrated": False,
            "model": MODEL_ID,
            "revision": MODEL_REVISION,
            "method": "TEST DOUBLE",
            "usage": {"prefills": len(choices), "input_tokens": 500, "generated_tokens": 0},
        }

    def close(self):
        self.closed = True
