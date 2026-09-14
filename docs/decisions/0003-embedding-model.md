# ADR 0003 — Embedding model

**Status:** Accepted
**Date:** 2026-09-14

## Context

Chunk token distribution over the 760-chunk foundation corpus (estimated tokens):

| median | p90 | p99 | max |
|---|---|---|---|
| 119 | 375 | 1,410 | 1,726 |

| threshold | chunks over | share |
|---|---|---|
| 256 | 146 | 19.2% |
| 512 | 40 | 5.3% |
| 1024 | 16 | 2.1% |

The 512-token cliff is what makes this a decision rather than a default.

## Decision

**`nomic-embed-text-v1.5`, run locally via sentence-transformers on CPU.**

Two reasons, in order of weight:

1. **8,192-token context.** No chunk in the corpus is truncated. In regulatory text the
   tail of a long provision is where the exceptions and conditions live, so silent
   truncation is not a cosmetic loss — it removes exactly the material that changes an
   answer.
2. **Local inference.** Re-indexing is free, which matters because tuning the evaluation
   harness means rebuilding the index many times. It also preserves the air-gapped story
   that makes this project meaningful for federal work, where sending regulated queries to
   a third-party API is frequently not permitted.

## Options rejected

**`bge-small-en-v1.5` (512 tokens).** Lighter and faster, but truncates 40 chunks (5.3%)
unless a secondary splitter is added. Rejected because the fix is work that buys nothing:
splitting long provisions to satisfy a model limit introduces a new boundary problem in
order to avoid a model that does not have one.

**OpenAI `text-embedding-3-small`.** Strong quality and trivial setup, but forfeits the
air-gap story, bills on every re-index during harness tuning, and exercises no local model
skills.

## Operational notes

- **Task prefixes are mandatory for this model.** Documents must be embedded as
  `search_document: <text>` and queries as `search_query: <text>`. Omitting them, or using
  the same prefix for both, measurably degrades retrieval. This is a common silent error:
  nothing fails, results just get worse.
- **`trust_remote_code=True` is required**, meaning model-repo code executes locally at
  load time. Acceptable here for a public research project. It would *not* be acceptable
  unreviewed in the federal deployment this project is meant to evoke, and the README must
  say so rather than quietly demonstrating a practice that would fail a security review.
- CPU-only torch is installed deliberately. 760 chunks do not justify a CUDA dependency.

## Consequences

- First run downloads roughly 550 MB of model weights; after that the system is fully
  offline.
- Embedding dimension is 768. Matryoshka truncation to 256 is available if index size ever
  matters; not used now, since 760 chunks is tiny.
- The cosine-similarity check on the 67 byte-identical bodies shared by 29 CFR 1607 and
  41 CFR 60-3 is now possible. That check is what will finally confirm or refute the
  header-injection hypothesis from ADR 0002.
