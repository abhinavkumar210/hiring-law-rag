# ADR 0001 — Corpus scope

**Status:** Accepted
**Date:** 2026-09-14

## Context

This is a retrieval system over US employment-discrimination law, built specifically to
answer compliance questions about automated employment decision tools (AEDTs) — hiring
software that screens, ranks, or scores candidates.

The corpus scope determines whether the retrieval problem is real or trivial, so it was
decided first.

## Decision

Include two layers:

1. **AI-specific hiring regulation** — NYC Local Law 144 and the DCWP implementing rules,
   Colorado SB 24-205, the Illinois AI Video Interview Act, California FEHA automated-decision
   regulations, the EU AI Act employment provisions, and EEOC technical assistance on AI.

2. **The underlying discrimination law those rules rest on** — Title VII, the ADA, the ADEA,
   the EEOC Compliance Manual, OFCCP regulations at 41 CFR 60, and the Uniform Guidelines on
   Employee Selection Procedures (UGESP) at 29 CFR 1607.

Estimated 2,000–3,000 pages.

## Options rejected

**AI-hiring rules only (~300–600 pages).** Rejected because these documents are largely
self-contained: a question is answered from one chunk of one document. That is lookup, not
retrieval, and it does not justify a vector search architecture. A corpus this small also
invites the fair objection that the whole index could be replaced by a long prompt.

**Adding case law** (Griggs, Ricci, EEOC v. iTutorGroup, Mobley v. Workday). Rejected for now
on two grounds. Judicial opinions are structurally unlike regulations and would require a
second ingestion path, roughly doubling ingestion work before the evaluation harness — the
actual centerpiece — is reached. More seriously, Mobley v. Workday is in active litigation,
so the correct answer to questions about it changes over time. That is disqualifying for a
golden set, which depends on stable ground truth. Revisit as a stretch goal.

## Why layer 2 is the point

NYC Local Law 144 requires a bias audit that computes an "impact ratio." The law does not
define what value of that ratio is acceptable. That threshold is the four-fifths rule, which
lives in 29 CFR 1607.4(D) — a 1978 regulation that the 2023 law does not cite in its operative
text.

So a user question like "does my screening tool pass NYC's bias audit?" requires retrieving
two documents written forty-five years apart with almost no lexical or semantic overlap. A
naive embedding-similarity search retrieves the 2023 law, answers confidently, and omits the
threshold that determines the actual answer.

This is the central retrieval failure the project exists to expose and fix. It is only
available if layer 2 is in the corpus.

## Consequences

- Ingestion must handle mixed formats: eCFR XML, EUR-Lex, state statute HTML, agency guidance.
- The evaluation harness needs multi-document questions, not just single-hop ones, or it will
  not detect this failure class.
- Corpus is large enough that retrieval quality genuinely matters, which is the point.
