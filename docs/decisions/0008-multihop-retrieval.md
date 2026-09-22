# ADR 0008 — Two-stage retrieval for cross-document questions

**Status:** Accepted
**Date:** 2026-09-22

## Context

ADR 0002 said chunking could not solve the cross-document problem and deferred it. The
evaluation harness then measured exactly how badly it failed.

Single-stage retrieval, k=5:

| type | correct |
|---|---|
| single_hop | 0.952 |
| **cross_document** | **0.000** |
| jurisdiction | 0.667 |
| status_sensitive | 0.500 |
| **overall** | **0.844** |

An overall of 0.844 reads as a working system. The capability the corpus was *chosen* to
test scored zero. This is the argument for per-type reporting (ADR 0007) paying for itself
on the first run.

### Diagnosis

For *"Where does the 80 percent benchmark used in NYC bias audits come from?"* the entire
top-20 was NYC documents. The query speaks 2023 NYC vocabulary — "bias audit", "impact
ratio" — and the answer is written in 1978 federal vocabulary — "selection rate",
"four-fifths", "adverse impact". No shared terms, no citation between them.

29 CFR 1607.4(D) was not missing from the index. It was at **rank 28**.

Using a retrieved NYC chunk as its own query put it at **cross-source rank 3**. The
relationship exists in the corpus; it just is not reachable from the user's phrasing in one
step.

## Decision

**Two-stage retrieval with reserved slots.**

Stage 1 answers the question as asked. Stage 2 takes the best stage-1 chunks and asks what
else in the corpus is about the same thing, under an exclusion that forces the hop to land
somewhere new. Two of the k slots are reserved for stage-2 results.

Reserved slots rather than score-merged: a stage-2 hit scores lower than a good direct hit
almost by construction, so merging by score would never surface it. Reserving guarantees
the crossing while capping what it can displace.

### Two exclusions are required, not one

This was found by measuring, not by design. Each strategy fixes what the other misses:

| exclusion | fixes | fails |
|---|---|---|
| different `source_id` | jurisdiction 0.667→1.000, status 0.500→1.000 | cross_document stays 0.000 |
| different `jurisdiction` | cross_document 0.000→1.000 | jurisdiction and status fall back |

**Why source-exclusion alone fails cross-document:** `nyc_ll144_rules` and `nyc_aedt_faq`
are different sources describing the same regime. The hop went sideways within NYC and
returned nothing the user did not already have.

**Why jurisdiction-exclusion alone fails the others:** the withdrawn EEOC guidance and
UGESP are both `US-federal`, so a jurisdiction hop can never connect them.

Running both — one reserved slot each — fixes all three.

## Result

| type | single-stage | two-stage |
|---|---|---|
| cross_document | 0.000 | **1.000** |
| jurisdiction | 0.667 | **1.000** |
| status_sensitive | 0.500 | **1.000** |
| single_hop | 0.952 | 0.905 |
| refusal | 1.000 | 1.000 |
| out_of_scope | 1.000 | 1.000 |
| **overall correct** | **0.844** | **0.938** |
| recall@k | 0.857 | 0.929 |

## The cost, stated plainly

**single_hop drops from 0.952 to 0.905.** Two questions lose their correct citation because
a reserved slot displaced it at rank 4 or 5. That is not a rounding artefact, it is the
mechanism working as designed: reserving slots means taking them from somewhere.

The trade is accepted because the corpus is one where multi-document questions are the
realistic ones — a compliance question almost always spans a local rule and the federal
regulation underneath it — and because a confidently incomplete answer to a
cross-jurisdiction question is the more damaging failure.

It is recoverable if the trade stops being worth it: raise `k`, or lower
`MULTIHOP_RESERVE` to 1 and accept losing one of the two hop strategies.

## Options rejected

**Diversity cap / MMR.** Capping results per source would not reach rank 28 — other
sources sit between, so the capped list still never gets there. Measured, not assumed.

**Hybrid BM25.** "80 percent" versus UGESP's "eighty percent", and "impact ratio" appears
nowhere in UGESP. Lexical matching does not bridge this particular gap either. Still worth
adding later for other query shapes.

**Curated cross-reference edges.** Hand-mapping "impact ratio" → 29 CFR 1607.4(D) would
work and be fully explainable, but it does not generalise: every new relationship needs a
human. The second hop discovers relationships the curator never thought of, which is how
jurisdiction and status_sensitive improved as a side effect.

**Raising k instead.** Returning 30 results would technically include rank 28, but pushes
the selection problem onto the reader and degrades the composer's summary, which leads with
the top hit.

## Consequences

- Retrieval now costs three embedding passes per query instead of one — roughly 3× latency.
  Acceptable at ~2s/query on CPU; it would need batching or caching under load.
- `compose()` uses multihop by default, so the API and the harness exercise the same path.
- `python src/eval/harness.py --no-multihop` reproduces the single-stage numbers above, so
  the comparison stays runnable rather than being a claim in a document.
