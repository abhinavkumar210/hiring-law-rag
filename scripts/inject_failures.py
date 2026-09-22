"""Inject real failures and show the system's response.

"I handle withdrawn guidance" is a claim. A script that strips the status flag
and shows the composer refuse to build the answer is proof. Each scenario below
breaks something on purpose and prints what happens, so behaviour can be
demonstrated on a screenshare rather than described.

Run:  python scripts/inject_failures.py
"""
from __future__ import annotations

import dataclasses
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402

from answer.compose import (  # noqa: E402
    WITHDRAWN_DISCLOSURE,
    Answer,
    Citation,
    compose,
)
from index.chunkers import deduplicate, structural  # noqa: E402
from ingest.parse_ecfr import parse_part  # noqa: E402
from ingest.text_normalize import repair_ligatures  # noqa: E402
from retrieve.search import Index  # noqa: E402

RULE = "=" * 72


def header(n: int, title: str) -> None:
    print(f"\n{RULE}\n{n}. {title}\n{RULE}")


def scenario_ligature_corruption() -> None:
    header(1, "PDF ligature corruption silently breaks the corpus's key term")
    corrupted = "A selection rate below four-fi\x00hs of the highest rate..."
    print(f"  raw from pypdf   : {corrupted!r}")
    print(f"  contains 'four-fifths'? {'four-fifths' in corrupted}")
    repaired, residual = repair_ligatures(corrupted)
    print(f"  after repair     : {repaired!r}")
    print(f"  contains 'four-fifths'? {'four-fifths' in repaired}")
    print(f"  unresolved gaps reported: {residual}")
    print("\n  Why it matters: nothing errors. Without repair, the one federal")
    print("  document on applying the four-fifths rule to AI never matches a")
    print("  query about the four-fifths rule.")


def scenario_withdrawn_without_disclosure() -> None:
    header(2, "Withdrawn guidance cannot be presented without disclosure")
    withdrawn = Citation(
        citations=["EEOC AI guidance (archived)"],
        jurisdiction="US-federal",
        status="WITHDRAWN",
        excerpt="Assessing adverse impact in algorithmic selection procedures...",
        score=0.91,
    )
    print("  attempting to build an Answer citing WITHDRAWN guidance with no")
    print("  disclosure field populated...")
    try:
        Answer(
            question="what does EEOC say about AI hiring?",
            refused=False,
            refusal_reason=None,
            summary="EEOC guidance says...",
            citations=[withdrawn],
            disclosures=[],
        )
        print("  FAILED: object constructed. The guarantee is not enforced.")
    except ValueError as exc:
        print(f"  blocked at construction: {exc}")
    ok = Answer(
        question="what does EEOC say about AI hiring?",
        refused=False,
        refusal_reason=None,
        summary="EEOC guidance says...",
        citations=[withdrawn],
        disclosures=[WITHDRAWN_DISCLOSURE],
    )
    print(f"  with disclosure  : constructed, {len(ok.disclosures)} disclosure(s)")


def scenario_answer_without_citations() -> None:
    header(3, "An answer cannot exist without citations")
    try:
        Answer(
            question="what is the four-fifths rule?",
            refused=False,
            refusal_reason=None,
            summary="It is 80 percent.",
            citations=[],
            disclosures=[],
        )
        print("  FAILED: uncited answer constructed.")
    except ValueError as exc:
        print(f"  blocked at construction: {exc}")
    print("\n  This is why guardrails live in the type, not the prompt. There is")
    print("  no code path that returns an uncited answer, including a future one.")


def scenario_index_corruption() -> None:
    header(4, "A corrupt index fails loudly instead of returning wrong answers")
    try:
        Index(chunks=[{"chunk_id": "a"}, {"chunk_id": "b"}],
              vectors=np.zeros((5, 768), dtype=np.float32), meta={})
        print("  FAILED: mismatched index accepted.")
    except ValueError as exc:
        print(f"  blocked at load: {exc}")
    print("\n  Without this check, chunk i would be described by vector i from a")
    print("  different build: every answer plausible, every citation wrong.")


def scenario_dedup_disabled() -> None:
    header(5, "Disabling dedup restores near-duplicate crowding")
    ug = structural(parse_part(ROOT / "data/raw/ecfr/ugesp.xml", "ugesp"))
    of = structural(parse_part(ROOT / "data/raw/ecfr/ofccp_60_3.xml", "ofccp_60_3"))
    raw = ug + of
    merged = deduplicate(raw)
    shared = {c.body for c in ug} & {c.body for c in of}
    print(f"  without dedup : {len(raw)} chunks, {len(shared)} bodies duplicated")
    print(f"  with dedup    : {len(merged)} chunks")
    multi = [c for c in merged if len(c.citations) > 1]
    print(f"  merged chunks carrying both citations: {len(multi)}")
    if multi:
        print(f"  example       : {multi[0].citations}")
    print("\n  Measured earlier: duplicate bodies embed at cosine 1.00 without")
    print("  headers and 0.95 with them - close enough to crowd the top-k either")
    print("  way. Dedup removes the pair instead of trying to rank it.")


def scenario_live_refusals() -> None:
    header(6, "Live refusal behaviour (requires a built index)")
    try:
        index = Index.load()
    except FileNotFoundError as exc:
        print(f"  skipped: {exc}")
        return

    probes = [
        ("Should I settle the discrimination lawsuit?", "legal advice"),
        ("What is the minimum wage in New Jersey?", "out of corpus scope"),
        ("What selection rate is evidence of adverse impact?", "answerable"),
    ]
    for q, label in probes:
        ans = compose(q, index)
        verdict = "REFUSED" if ans.refused else "answered"
        print(f"\n  [{label}] {q}")
        print(f"    -> {verdict}")
        if ans.refused:
            print(f"    -> {ans.refusal_reason[:96]}...")
        else:
            print(f"    -> cites {ans.citations[0].citations} "
                  f"(score {ans.citations[0].score})")
            if ans.disclosures:
                print(f"    -> {len(ans.disclosures)} disclosure(s) attached")


def main() -> int:
    print("Failure injection: breaking things on purpose")
    scenario_ligature_corruption()
    scenario_withdrawn_without_disclosure()
    scenario_answer_without_citations()
    scenario_index_corruption()
    scenario_dedup_disabled()
    scenario_live_refusals()
    print(f"\n{RULE}\nall scenarios executed\n{RULE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
