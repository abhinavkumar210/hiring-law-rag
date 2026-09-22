"""Compose a grounded answer from retrieved chunks.

DESIGN: guardrails are enforced in code, not requested in a prompt.

A prompt that says "always cite your sources" is a request. A composer that
cannot construct a response object without citations is a guarantee. Everything
this project promises about output safety is therefore structural:

  * an Answer cannot be built with zero citations unless it is a refusal
  * withdrawn sources force a disclosure field to be populated
  * below the abstention threshold, the only constructible result is a refusal
  * legal-advice questions are refused before retrieval runs at all

Synthesis by a language model is deliberately optional and off by default. The
extractive path is fully offline, reproducible, and testable, which keeps the
air-gapped deployment story intact (ADR 0003) and means the evaluation harness
measures retrieval rather than a model's phrasing.
"""
from __future__ import annotations

import dataclasses
import re

from retrieve.search import Index, Result

# Questions asking for legal advice rather than what the regulations say. These
# are refused before retrieval: the failure mode is not a bad retrieval, it is
# answering at all.
ADVICE_PATTERNS = [
    r"\bshould i\b",
    r"\bwill i win\b",
    r"\bdo i have a case\b",
    r"\bcan i sue\b",
    r"\bam i going to\b",
    r"\bwhat are my chances\b",
    r"\bshould we settle\b",
    r"\bis it worth suing\b",
]

ADVICE_REFUSAL = (
    "This system reports what published regulations say, with citations. It "
    "cannot advise on litigation strategy, predict case outcomes, or tell you "
    "what to do in your situation - that is legal advice and requires a "
    "licensed attorney who knows your facts. Ask what a regulation requires and "
    "it will answer with sources."
)

OUT_OF_SCOPE_REFUSAL = (
    "Nothing in the indexed corpus answers this with enough confidence to be "
    "worth quoting. The corpus covers federal employment-discrimination "
    "regulations and AI-hiring rules for NYC and Colorado. It does not cover "
    "wage and hour law, benefits, labor relations, or case law."
)

WITHDRAWN_DISCLOSURE = (
    "At least one source below has been WITHDRAWN and is no longer current "
    "agency guidance. It is retained for historical reference because employers "
    "relied on it and state regimes still track its concepts. Do not treat it as "
    "current federal guidance."
)


@dataclasses.dataclass(frozen=True)
class Citation:
    citations: list[str]
    jurisdiction: str
    status: str
    excerpt: str
    score: float


@dataclasses.dataclass(frozen=True)
class Answer:
    question: str
    refused: bool
    refusal_reason: str | None
    summary: str
    citations: list[Citation]
    disclosures: list[str]

    def __post_init__(self) -> None:
        # The structural guarantee: a non-refusal answer must carry citations.
        if not self.refused and not self.citations:
            raise ValueError(
                "an answer that is not a refusal must cite at least one source"
            )
        if self.refused and self.citations:
            raise ValueError("a refusal must not present sources as support")
        # Withdrawn material must always be disclosed.
        if any(c.status != "in_force" for c in self.citations):
            if WITHDRAWN_DISCLOSURE not in self.disclosures:
                raise ValueError(
                    "withdrawn sources present without the required disclosure"
                )

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


def is_legal_advice(question: str) -> bool:
    q = question.lower()
    return any(re.search(p, q) for p in ADVICE_PATTERNS)


def _excerpt(text: str, limit: int = 420) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    cut = text.rfind(" ", 0, limit)
    return text[: cut if cut > 0 else limit].rstrip() + "..."


def refuse(question: str, reason: str) -> Answer:
    return Answer(
        question=question,
        refused=True,
        refusal_reason=reason,
        summary=reason,
        citations=[],
        disclosures=[],
    )


def compose(question: str, index: Index, k: int = 5) -> Answer:
    if is_legal_advice(question):
        return refuse(question, ADVICE_REFUSAL)

    results: list[Result] = index.search(question, k=k)
    if index.should_abstain(results):
        return refuse(question, OUT_OF_SCOPE_REFUSAL)

    citations = [
        Citation(
            citations=r.citations,
            jurisdiction=r.jurisdiction,
            status=r.status,
            excerpt=_excerpt(r.body),
            score=round(r.score, 4),
        )
        for r in results
    ]

    disclosures: list[str] = []
    if any(c.status != "in_force" for c in citations):
        disclosures.append(WITHDRAWN_DISCLOSURE)

    jurisdictions = sorted({c.jurisdiction for c in citations})
    if len(jurisdictions) > 1:
        disclosures.append(
            "Sources below span more than one jurisdiction ("
            + ", ".join(jurisdictions)
            + "). Obligations can differ, and more than one regime may apply to "
            "you at the same time."
        )

    lead = citations[0]
    summary = (
        f"The most relevant provision is {', '.join(lead.citations)}. "
        f"{_excerpt(lead.excerpt, 260)}"
    )

    return Answer(
        question=question,
        refused=False,
        refusal_reason=None,
        summary=summary,
        citations=citations,
        disclosures=disclosures,
    )
