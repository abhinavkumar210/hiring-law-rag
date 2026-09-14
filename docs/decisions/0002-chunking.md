# ADR 0002 — Chunking strategy

**Status:** Accepted
**Date:** 2026-09-14

## Context

Two retrieval problems were identified in the corpus before any retrieval code was
written (see ADR 0001):

1. A cross-document dependency: NYC LL144 requires an impact ratio but not a threshold;
   the threshold is in 29 CFR 1607.4(D), published 1978.
2. A near-duplicate pair: 29 CFR 1607 and 41 CFR 60-3 are 99.6% textually identical but
   bind different populations (all employers via EEOC vs federal contractors via OFCCP).

**Chunking is aimed at problem 2 only.** No chunk size causes an embedding model to
connect vocabulary in a 2023 city law to vocabulary in a 1978 federal regulation. Problem
1 needs a different mechanism — query expansion, a second hop, or explicit cross-reference
edges — and is deferred to its own ADR.

## Decision

**Strategy C: one chunk per regulatory subsection, with the chunk's own citation
prepended to the embedded text.**

    29 CFR 1607 UGESP | § 1607.4 Information on impact. | 29 CFR 1607.4(D)

    Adverse impact and the "four-fifths rule." A selection rate for any race...

The header puts jurisdiction *inside the vector* rather than hoping the model infers it
from text that never states it. The raw body is stored separately so the header never
contaminates what is shown to the user.

**Strategy A (fixed 512-token windows, 64 overlap) is also implemented, deliberately.**
It is the baseline the harness measures against. Without it, "structure-aware chunking is
better" is an opinion; with it, the improvement is a number that was earned.

## Options rejected

- **A alone.** Splits § 1607.4(D) mid-definition and loses the citation anchor, so answers
  cannot be reliably attributed to a section.
- **B — structure without header injection.** Exact citations, but leaves the near-duplicate
  problem entirely to metadata filtering. Header injection is cheap and additive.
- **D — small-to-big / parent retrieval.** Likely better eventually, but more machinery up
  front and harder to explain. Revisit once the harness can show it helps.

## What measurement actually showed

Two things were expected and did not hold. Both are recorded because they change what the
next step must be.

**1. Strategy A does not produce byte-identical chunks across the near-duplicate parts.**
Predicted collisions; measured zero. The ~100 sentences unique to each part shift the
window offsets, so windows never align exactly.

**2. Exact-match collision is the wrong metric entirely.** Byte equality was never the
risk — high cosine similarity is. Two chunks differing only by a short header can still
embed almost identically. Since strategy A also scores zero exact collisions, this metric
cannot discriminate between the strategies.

**Consequence: header injection is currently a reasoned hypothesis, not a demonstrated
fix.** Validating it requires cosine similarity between the 67 subsection bodies that are
byte-identical across 29 CFR 1607 and 41 CFR 60-3, under a real embedding model. That
measurement belongs in the evaluation harness and must be built before strategy C can be
claimed to work.

## Parser defect found while measuring

The corpus uses two numbering conventions: 1978-era parts mark subsections `A.` `B.`,
modern parts use `(a)` `(b)` with `(1)` `(2)` nested underneath. The initial parser knew
only the first, collapsing 29 CFR 1630 (ADA) from 514 paragraphs into 16 oversized units.

Fixed by treating alphabetic markers of either style as boundaries and numeric markers as
continuations — numeric items nest under an alphabetic parent, so splitting on them
separates a provision from the condition governing it.

| | before | after |
|---|---|---|
| total units | 335 | 760 |
| 29 CFR 1630 units | 16 | 88 |
| largest chunk (est. tokens) | 5,138 | 1,726 |

## Consequences

- Median chunk is ~120 tokens; largest is ~1,726. Whether the tail needs a secondary split
  depends on the embedding model's context limit — folded into the next decision.
- The harness must include a cosine-similarity check on the near-duplicate pair, or the
  central chunking claim stays unverified.
