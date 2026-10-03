"""Model-selected scientific decisions inside an explicit, executable action catalog.

Retrieval proposes evidence candidates, never answers. AnyJev scores each closed
question with local model logits. The only prose below documents the option that
won; it is not presented as a generated explanation or a chain of thought.
"""

import hashlib
import math
import re
import time

from .agents import AgentBudgetExceeded, RoleBackend, T
from .artifacts import canonical
from .decision_runtime import DecisionProcess
from .sources import Source

PROMPT_VERSION = "bounded-decisions-v4"


class DecisionAbstained(RuntimeError):
    """An explicit model stop/defer choice or ambiguous option distribution."""


def passages(source: Source, query: str, limit: int = 5) -> tuple[list[dict], dict]:
    """Scan every page; rank overlapping exact spans, with retrieval scope recorded."""
    terms = set(re.findall(r"[a-z]{3,}", query.lower())) - {
        "the",
        "and",
        "each",
        "with",
        "change",
        "instead",
        "one",
        "fixed",
    }
    candidates = []
    for page, text in enumerate(source.pages, 1):
        words = list(re.finditer(r"\S+", text))
        # Include sentence starts so a future-work sentence retains its subject.
        starts = {0} | {m.end() for m in re.finditer(r"[.!?]\s+", text)}
        starts |= {words[i].start() for i in range(0, len(words), 45)}
        for start in sorted(starts):
            ends = [w.end() for w in words if start < w.end() <= start + 560]
            if not ends:
                continue
            quote = text[start : max(ends)].strip()
            if 8 <= len(quote) <= 600:
                item = {"source_id": source.source_id, "page": page, "quote": quote}
                tokens = set(re.findall(r"[a-z]{3,}", quote.lower()))
                candidates.append((item, tokens))
    frequencies = {term: sum(term in tokens for _, tokens in candidates) for term in terms}

    def rank(candidate):
        item, tokens = candidate
        score = sum(math.log((1 + len(candidates)) / (1 + frequencies[t])) for t in terms & tokens)
        future = bool(
            re.search(
                r"\b(could|future|extend|extended|extensions|further)\b", item["quote"].lower()
            )
        )
        return score * (1.6 if future else 1)

    ranked = [(rank(candidate), candidate[0]) for candidate in candidates]
    ranked.sort(key=lambda item: -item[0])
    picked = []
    for _, item in ranked:
        words = set(item["quote"].split())
        near_duplicate = any(
            item["page"] == prior["page"]
            and len(words & set(prior["quote"].split())) / max(1, len(words)) > 0.5
            for prior in picked
        )
        if not near_duplicate:
            picked.append(item)
        if len(picked) == limit:
            break
    return picked, {
        "source_id": source.source_id,
        "pages_scanned": len(source.pages),
        "spans_scanned": len(candidates),
        "spans_presented": len(picked),
        "method": "IDF lexical retrieval over all pages; sentence and overlapping exact spans",
        "query": query,
        "full_text_reviewed_by_model": False,
    }


class AnyJevRoles(RoleBackend):
    name = "anyjev"

    def __init__(self, sources, store, config):
        super().__init__(sources, store, config)
        self.worker = None
        self.decision_calls = 0
        self.prefills = 0
        self.input_tokens = 0
        self.round = 0
        self.role = "reader"

    def close(self) -> None:
        if self.worker is not None:
            self.worker.close()

    def choose(self, key: str, state: dict, question: str, choices: dict[str, str]) -> dict:
        if self.decision_calls >= self.config.max_decision_calls:
            raise AgentBudgetExceeded("Decision call budget exhausted")
        if time.monotonic() >= self.deadline:
            raise TimeoutError("Decision deadline exhausted")
        if self.worker is None:
            self.worker = DecisionProcess(self.deadline, self.config.agent_timeout_seconds)
            self.store.write("decision-model.json", self.worker.manifest)
        self.decision_calls += 1
        stage = self.role if self.round == 0 else f"rounds/{self.round:02d}/{self.role}"
        if self.role == "validator":
            stage = f"rounds/{self.round:02d}/validation"
        request = {"state": state, "question": question, "choices": choices}
        record = {
            "id": key,
            "stage": stage,
            "backend": self.name,
            "prompt_version": PROMPT_VERSION,
            **request,
            "input_sha256": hashlib.sha256(canonical(request).encode()).hexdigest(),
        }
        path = f"decisions/{self.decision_calls:02d}-{key}.json"
        self.store.write(path, record)
        result = self.worker.decide(**request)
        self.prefills += result["usage"]["prefills"]
        self.input_tokens += result["usage"]["input_tokens"]
        # A declared operational ambiguity gate, not a calibrated confidence claim.
        weights = sorted(result["probabilities"].values(), reverse=True)
        ambiguous = weights[0] - weights[1] < 0.05
        record.update(
            result=result, ambiguity_gate={"minimum_margin": 0.05, "passed": not ambiguous}
        )
        self.store.write(path, record)
        if ambiguous:
            raise DecisionAbstained(f"Ambiguous model choice: {key}; recorded for review")
        return result

    @staticmethod
    def explanation(result: dict, choices: dict[str, str]) -> str:
        answer = result["answer"]
        return (
            f"Model selected {answer}: {choices[answer]} "
            f"L0 option weight {result['probabilities'][answer]:.3f}; uncalibrated. "
            "See the recorded state and competing options for the decision basis."
        )

    def ask(self, role: str, payload: dict, contract: type[T]) -> T:
        if self.calls >= self.config.max_agent_calls:
            raise AgentBudgetExceeded("Role call budget exhausted")
        self.calls += 1
        self.role = role
        if role == "literature":
            self.round += 1
        result = getattr(self, f"_{role}")(payload)
        validated = contract.model_validate(result)
        self.store.write(
            f"roles/{self.calls:02d}-{role}.json",
            {
                "backend": self.name,
                "prompt_version": PROMPT_VERSION,
                "output": validated.model_dump(),
                "decision_calls_so_far": self.decision_calls,
                "usage": {
                    "prefills_so_far": self.prefills,
                    "input_tokens_so_far": self.input_tokens,
                    "generated_tokens": 0,
                },
            },
        )
        return validated

    def _reader(self, payload: dict) -> dict:
        proposals = []
        for experiment, recipe in payload["experiment_catalog"].items():
            query = experiment.replace("_", " ")
            evidence, scope = passages(self.sources[0], query)
            choices = {
                f"passage_{i}": f"Passage {i} explicitly suggests this direction."
                for i in range(len(evidence))
            }
            choices.update(
                unsupported="None of these passages suggests this direction.",
                uncertain="The supplied passages are insufficient to decide.",
            )
            result = self.choose(
                f"source-{experiment}",
                {
                    "direction": experiment,
                    "candidate_passages": dict(zip(list(choices), evidence, strict=False)),
                    "retrieval_scope": scope,
                },
                "Which passage explicitly proposes the named direction as FUTURE or "
                "UNEXPLORED work? Select the passage that suggests an extension, not one "
                "describing an already-studied model or how its baseline works. "
                "A mention or a citation alone is insufficient. Select unsupported if no "
                "passage proposes this direction, or uncertain if the evidence is ambiguous.",
                choices,
            )
            answer = result["answer"]
            if answer in {"unsupported", "uncertain"}:
                continue
            proposals.append(
                {
                    "id": experiment,
                    "experiment": experiment,
                    "title": experiment.replace("_", " ").capitalize(),
                    "hypothesis": recipe["question"],
                    "evidence": evidence[int(answer.removeprefix("passage_"))],
                }
            )
        if not proposals:
            raise DecisionAbstained("No source-supported direction selected by the model")
        return {"proposals": proposals}

    def _critic(self, payload: dict) -> dict:
        critiques = []
        choices = {
            "accept": "Feasible source-backed experiment within these limits; not a novelty claim.",
            "reject": "Unsupported or not meaningfully testable with this recipe.",
            "defer": "Evidence or feasibility is too uncertain; require review.",
        }
        for proposal in payload["proposals"]:
            grounding_choices = {
                "supported": "The quotation proposes the same change or a broader extension "
                "that includes it. The specific numerical parameters may be experiment choices.",
                "topic_only": "The quotation shares a topic but proposes a different change, "
                "or only describes prior work; it does not support this proposed extension.",
                "unclear": "The quotation lacks enough detail to establish this connection.",
            }
            grounding = self.choose(
                f"grounding-{proposal['id']}",
                {
                    "proposed_change": proposal["hypothesis"],
                    "direction": proposal["experiment"],
                    "quotation": proposal["evidence"],
                },
                "Is the proposed experiment a reasonable operationalization of the "
                "future-work direction in this quotation? We are checking the connection "
                "to a suggested direction, not whether the paper proves the experiment's "
                "outcome or specifies its numerical parameters. An extension to site "
                "occupation does not justify a different extension to bidirectional bonds. "
                "A topic mention alone is insufficient.",
                grounding_choices,
            )
            if grounding["answer"] != "supported":
                critiques.append(
                    {
                        "proposal_id": proposal["id"],
                        "decision": "reject" if grounding["answer"] == "topic_only" else "defer",
                        "rationale": self.explanation(grounding, grounding_choices),
                        "risks": ["Source does not establish support for the proposed mechanism"],
                    }
                )
                continue
            result = self.choose(
                f"critique-{proposal['id']}",
                {
                    "proposal": proposal,
                    "limits": self.config.model_dump(),
                    "capabilities": "Seeded lattice simulation, matched control, "
                    "wrapping intervals. "
                    "No critical-point search, scaling fit, or network literature search.",
                },
                "Should this finite-size experiment proceed? Accept only if its quote "
                "supports an extension rather than just an existing baseline description, "
                "and the declared experiment can meaningfully test it within the limits.",
                choices,
            )
            critiques.append(
                {
                    "proposal_id": proposal["id"],
                    "decision": result["answer"],
                    "rationale": self.explanation(result, choices),
                    "risks": [
                        "Finite-size effects",
                        "Limited supplied literature",
                        "Fixed p does not locate a new critical point",
                    ],
                }
            )
        accepted_ids = {c["proposal_id"] for c in critiques if c["decision"] == "accept"}
        accepted = [p for p in payload["proposals"] if p["id"] in accepted_ids]
        if self.config.preferred_experiment:
            accepted = [p for p in accepted if p["experiment"] == self.config.preferred_experiment]
        selected = None
        if accepted:
            choices = {p["id"]: p["hypothesis"] for p in accepted}
            choices["stop"] = "None is sufficiently realistic under the declared resource limits."
            result = self.choose(
                "select-direction",
                {
                    "accepted": accepted,
                    "limits": self.config.model_dump(),
                    "selection_goal": "Pick the most realistic useful next experiment: "
                    "source support, "
                    "minimal change to the validated model, clean comparable control, "
                    "and an interpretable finite-size result within budget.",
                },
                "Which accepted direction is the most realistic next action?",
                choices,
            )
            if result["answer"] != "stop":
                selected = result["answer"]
        return {"critiques": critiques, "selected_proposal_id": selected}

    def _literature(self, payload: dict) -> dict:
        proposal = payload["proposal"]
        evidence, scopes = [], []
        for source in self.sources:
            items, scope = passages(source, proposal["title"], 2)
            evidence.extend(items)
            scopes.append(scope)
        if len(evidence) > 8:
            raise ValueError("More than eight literature passages; narrow the source set")
        choices = {
            "unverified": "The supplied evidence is insufficient to establish a gap.",
            "known_overlap": "The supplied evidence already studies this same experiment.",
            "candidate_gap": "The compared sources support a specific unstudied extension.",
        }
        result = self.choose(
            "literature-assessment",
            {
                "proposal": proposal,
                "passages": evidence,
                "retrieval_scopes": scopes,
                "scope": "No external search. Retrieval candidates only, "
                "not exhaustive full-text review.",
            },
            "Does the supplied literature establish overlap or a candidate research gap? "
            "A seed's suggestion alone cannot establish novelty.",
            choices,
        )
        return {
            "assessment": result["answer"],
            "sources": evidence,
            "reasoning": self.explanation(result, choices),
            "search_scope": "Local lexical retrieval over all supplied pages; model reviews "
            "two exact passages per source. No live search or global novelty claim.",
        }

    def _planner(self, payload: dict) -> dict:
        choices = {
            "execute": "Execute this reviewed recipe with its recorded controls and limits.",
            "stop": "The proposal, evidence or controls do not justify execution.",
        }
        result = self.choose(
            "authorize-experiment",
            payload,
            "Is this bounded experiment worth executing as an exploratory test, "
            "even if scientific novelty remains unverified?",
            choices,
        )
        if result["answer"] == "stop":
            raise DecisionAbstained("Planner declined the experiment")
        return {
            "proposal_id": payload["proposal"]["id"],
            "experiment": payload["proposal"]["experiment"],
            "rationale": self.explanation(result, choices),
        }

    def _validator(self, payload: dict) -> dict:
        choices = {
            "supported": "Checks and intervals support the declared finite-size effect.",
            "inconclusive": "Valid measurements, but insufficient evidence for the effect.",
            "reject": "Invalid measurements, mismatched control, or unsupported interpretation.",
        }
        state = {
            "proposal": payload["proposal"],
            "checks": payload["checks"],
            "baseline_passed": payload["baseline"]["passed"],
            "literature_assessment": payload["literature"]["assessment"],
            "summary": payload["summary"],
        }
        result = self.choose(
            "validate-measurements",
            state,
            "Does the actual evidence support the declared finite-size effect? "
            "Passing numerical checks alone does not establish an effect or novelty.",
            choices,
        )
        return {
            "decision": result["answer"],
            "reasoning": self.explanation(result, choices),
            "limitations": [
                "Same local model with a separate validation question",
                "Small lattices and finite samples",
                "No global novelty verification",
            ],
        }
