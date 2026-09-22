import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

import pytest

from answer.compose import (
    ADVICE_REFUSAL,
    WITHDRAWN_DISCLOSURE,
    Answer,
    Citation,
    is_legal_advice,
    refuse,
)


def _citation(status: str = "in_force") -> Citation:
    return Citation(
        citations=["29 CFR 1607.4(D)"],
        jurisdiction="US-federal",
        status=status,
        excerpt="A selection rate less than four-fifths...",
        score=0.88,
    )


def test_answer_cannot_be_built_without_citations():
    with pytest.raises(ValueError, match="cite at least one source"):
        Answer(
            question="q",
            refused=False,
            refusal_reason=None,
            summary="s",
            citations=[],
            disclosures=[],
        )


def test_refusal_cannot_carry_supporting_sources():
    with pytest.raises(ValueError, match="must not present sources"):
        Answer(
            question="q",
            refused=True,
            refusal_reason="no",
            summary="no",
            citations=[_citation()],
            disclosures=[],
        )


def test_withdrawn_source_requires_disclosure():
    with pytest.raises(ValueError, match="without the required disclosure"):
        Answer(
            question="q",
            refused=False,
            refusal_reason=None,
            summary="s",
            citations=[_citation(status="WITHDRAWN")],
            disclosures=[],
        )


def test_withdrawn_source_is_allowed_once_disclosed():
    ans = Answer(
        question="q",
        refused=False,
        refusal_reason=None,
        summary="s",
        citations=[_citation(status="WITHDRAWN")],
        disclosures=[WITHDRAWN_DISCLOSURE],
    )
    assert ans.disclosures == [WITHDRAWN_DISCLOSURE]


@pytest.mark.parametrize(
    "question",
    [
        "Should I settle the discrimination lawsuit?",
        "Will I win if I sue my employer?",
        "Do I have a case against my manager?",
        "Can I sue for age discrimination?",
    ],
)
def test_legal_advice_questions_are_detected(question):
    assert is_legal_advice(question)


@pytest.mark.parametrize(
    "question",
    [
        "What selection rate is evidence of adverse impact?",
        "How long must records be preserved?",
        "What must a NYC bias audit calculate?",
    ],
)
def test_regulatory_questions_are_not_treated_as_advice(question):
    assert not is_legal_advice(question)


def test_refuse_builds_a_valid_refusal():
    ans = refuse("Should I settle?", ADVICE_REFUSAL)
    assert ans.refused
    assert ans.citations == []
    assert "legal advice" in ans.refusal_reason
