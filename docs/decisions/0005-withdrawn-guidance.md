# ADR 0005 — Withdrawn guidance stays in the corpus, with status

**Status:** Accepted
**Date:** 2026-09-22

## Context

Fetching the AI-specific layer returned HTTP 404 for both EEOC AI guidance documents.
The links were not stale — **the documents were removed from eeoc.gov in January 2025**,
including "Select Issues: Assessing Adverse Impact in Software, Algorithms, and Artificial
Intelligence Used in Employment Selection Procedures Under Title VII" (May 2023).

This is the only direct federal statement on AI and disparate impact in hiring, and it is
the document most squarely on this project's topic.

**It also retroactively validated ADR 0001.** The rejected scope option — "AI-hiring rules
only" — would have built the corpus predominantly out of recent AI-specific guidance. A
meaningful portion of that corpus would since have been withdrawn. The foundation layer
was chosen for retrieval reasons, and it turned out to be the layer that is still in force:
UGESP at 29 CFR 1607 has been unchanged since 1978 and still governs.

## Decision

**Include the withdrawn guidance from an archived copy, carrying `status: WITHDRAWN` as
first-class metadata that travels from ingestion into the answer.**

Concretely:

- The manifest records status and a note explaining the withdrawal.
- `Unit` and `Chunk` carry `status`, so it survives parsing, chunking and deduplication.
- `structural()` writes `STATUS: WITHDRAWN` into the embedded text, so the flag is present
  in the vector, not only in a sidecar field that a future code path might forget to read.
- `Answer.__post_init__` **raises** if a withdrawn source appears without the disclosure
  populated. Presenting rescinded guidance as current is not possible to construct.

## Options rejected

**Exclude it.** Simpler and defensible — it is not current law. Rejected because employers
built compliance programs on it, state regimes still track its concepts, and the most
useful thing a compliance tool can tell someone relying on that document is *that it was
withdrawn*. Excluding it means the system silently has nothing to say on its own core
topic.

**Include it unmarked.** Rejected outright. Quoting rescinded federal guidance as current
is the single most damaging error this system could make.

## Consequences

- Archived copies come from a third party (ACLU of Massachusetts mirror). Provenance is
  recorded in the manifest. The README must be explicit that this is an archived copy and
  not an official source.
- The golden set includes `status_sensitive` questions so this behaviour is measured rather
  than assumed.
- `status` becomes a retrieval filter: `include_withdrawn=False` is available for callers
  who want only operative law.

## Unresolved sources

Two AI-layer sources could not be fetched and are recorded as unresolved rather than
quietly dropped:

| source | reason |
|---|---|
| Illinois AI Video Interview Act (820 ILCS 42) | ilga.gov serves an incomplete TLS certificate chain, rejected by both certifi and the OS trust store, and returns 403 to direct requests. **Not worked around:** disabling certificate verification to ingest a legal corpus is not acceptable. |
| EU AI Act (Reg. 2024/1689) | EUR-Lex returns 202 Accepted with an empty body on both HTML and PDF endpoints, across retries with backoff. Likely server-side rate limiting. |

Both remain in the manifest with `status: unresolved` so the gap is visible in the corpus
rather than invisible.
