# ADR 0006 — Guardrails enforced in types, not prompts

**Status:** Accepted
**Date:** 2026-09-22

## Context

This system answers questions about regulations that carry legal consequence. Three output
failures matter more than answer quality:

1. Answering without citations, so a user cannot verify anything.
2. Presenting withdrawn guidance as current law.
3. Answering a question the corpus cannot support — legal advice, or a topic outside the
   index — because the retriever always returns *something*.

The common approach is to instruct a language model not to do these things. That is a
request, and it fails silently and non-deterministically.

## Decision

**Every output guarantee is a construction-time invariant on the `Answer` type, and
synthesis by a language model is optional and off by default.**

| Guarantee | Enforcement |
|---|---|
| No uncited answers | `Answer.__post_init__` raises if `not refused and not citations` |
| Refusals cite nothing | raises if `refused and citations` |
| Withdrawn material is disclosed | raises if any citation has `status != in_force` and the disclosure is absent |
| Legal advice is declined | pattern match on the question **before** retrieval runs |
| Out-of-scope is declined | abstention when top score `< ABSTAIN_THRESHOLD` |

There is no code path that returns an uncited answer, including one written later by
someone who has not read this file. That is the point: the invariant outlives the author's
intentions.

### Why generation is optional

The extractive path — retrieve, excerpt, cite — is fully offline, deterministic and
testable. Keeping it the default means:

- the air-gapped deployment story from ADR 0003 stays intact end to end;
- the evaluation harness measures **retrieval**, not a model's phrasing, so a regression in
  the numbers points at one subsystem;
- output cannot hallucinate, because no text is generated — excerpts are verbatim source.

An LLM synthesis adapter can sit on top later. It would inherit the same `Answer` type and
therefore the same invariants.

## Abstention threshold

`ABSTAIN_THRESHOLD = 0.62`, calibrated against the `out_of_scope` and `refusal` items in
the golden set.

This is an explicit precision/recall trade. Raising it produces more "I don't know" and
fewer confident wrong answers; lowering it does the reverse. For a compliance tool the
asymmetry is stark — a wrong citation is worse than an admission of ignorance — so the
threshold is set to favour abstention, and the harness reports `abstain_rate` separately so
the cost is visible rather than buried in an aggregate score.

## Options rejected

**Prompt-based guardrails.** "Always cite your sources" is unenforceable and untestable.

**Post-hoc validation.** Checking an answer after building it leaves a window where an
invalid answer exists and could be returned by an early return or an exception path.
Construction-time invariants have no such window.

**Always answering.** Rejected: a retriever always has a nearest neighbour, so "always
answer" guarantees confident nonsense on out-of-scope questions.

## Consequences

- Tests can assert guarantees directly by attempting to construct invalid answers, which is
  how `scripts/inject_failures.py` demonstrates them.
- The refusal patterns are a blunt instrument and will produce false positives on some
  legitimate questions beginning "should I". Recorded as a known limitation; the honest
  trade is that over-refusing is cheaper here than under-refusing.
