# ADR 0004 — Handling jurisdiction confusion by deduplication

**Status:** Accepted
**Date:** 2026-09-14

## Context

ADR 0002 hypothesised that embedding each chunk's citation would separate 29 CFR 1607
(EEOC) from 41 CFR 60-3 (OFCCP). Measurement partially refuted it: headers moved all 67
byte-identical pairs below 0.99 cosine, but only to a mean of 0.9515 — not enough to
reorder a ranked list. A probe query about *federal contractor* obligations still ranked
29 CFR 1607 above 41 CFR 60-3.

While deciding the fix, a legal fact reframed the problem:

**A federal contractor is subject to both regimes.** 41 CFR 60-3 applies to them as a
contractor; 29 CFR 1607 applies to them as an employer under Title VII. They are not
alternatives.

So the system was never failing to pick the right document. It was failing to **disclose
which regime it was quoting**. That is a disclosure problem, not a ranking problem, and
ranking machinery cannot fix it.

## Decision

**Deduplicate chunks with byte-identical bodies, and have the surviving chunk carry every
citation the text appears under.**

Identical regulatory text is one rule published in two places. It is indexed once, its
embedded header names all of its citations, and answers cite all of them.

## Options rejected

**Hard filter on user context** ("are you a federal contractor?"). Rejected as legally
wrong: filtering to the contractor regime hides Title VII obligations that also apply.
This option is worse than the bug — it converts a visible ranking error into a silent
omission.

**Hybrid lexical + vector search.** Genuinely useful and likely worth adding later for the
non-duplicate remainder, where lexical signal on "contractor" or "41 CFR" helps. Rejected
*as the fix for this*, because it treats the ranking symptom rather than the duplication
cause, and it still picks a winner where both answers apply.

**Cross-encoder reranker.** Most machinery, least explanatory power, same winner-picking
flaw.

## Result

| | chunks |
|---|---|
| before dedup | 760 |
| after dedup | 683 |
| removed | 77 (10.1%) |
| multi-citation chunks | 76 |

Duplication found, by source pair:

| parts sharing identical text | chunks |
|---|---|
| 41 CFR 60-3 + 29 CFR 1607 | 67 |
| 41 CFR 60-1 + 41 CFR 60-741 | 6 |
| 29 CFR 1630 (ADA) + 41 CFR 60-741 | 2 |
| 29 CFR 1606 + 41 CFR 60-1 + 29 CFR 1604 | 1 |

**Only the first pair was predicted.** The other nine duplicate relationships — including a
three-way overlap — were found because the deduplicator was written generically rather
than special-cased to the pair already known about. Had it been special-cased, nine
duplicate-vector problems would have remained in the index, undetected, since nothing in
the design was looking for them.

The four-fifths rule now resolves to a single chunk citing both
`29 CFR 1607.4(D)` and `41 CFR 60-3.4(D)`.

## Known limitation

Citations on a merged chunk are ordered by source filename, not by canonical relevance. The
four-fifths chunk currently lists `41 CFR 60-3.4(D)` first, though `29 CFR 1607.4(D)` is the
far more widely recognised citation and the correct lead for a general employer. Ordering
needs a rule; none is obviously right yet, so this is recorded rather than guessed at.

## Consequences

- Retrieval returns one vector per distinct rule, so near-duplicate crowding of the top-k
  is eliminated by construction rather than managed by scoring.
- Answers must render all citations on a chunk, not just the first. The generation layer
  has to be built with that assumption from the start.
- The golden set still needs jurisdiction-sensitive queries — dedup removes the identical
  case, but the ~40 bodies unique to each part can still be confused, and that is untested.
