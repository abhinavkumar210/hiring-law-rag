# ADR 0007 — Evaluation design

**Status:** Accepted
**Date:** 2026-09-22

## Context

Every decision in this project so far was justified by an argument. Arguments are cheap,
and two of them turned out to be wrong when measured (ADR 0002's header hypothesis; the
exact-match metric that could not discriminate between strategies). The harness exists so
that future arguments have to survive contact with numbers.

## Decision

### Ground truth is expressed as matchers against provisions that exist

A golden item does not store an expected answer string. It stores **expected evidence**:

```json
{"citation": "29 CFR 1607.4(D)"}
{"citation_contains": "1630.10"}
{"source_id": "nyc_ll144_rules"}
```

Two consequences. First, correctness is verifiable by a human who can open the CFR and
check. Nothing is invented; every `why` field names the provision that makes the answer
correct. Second, `scripts/validate_golden.py` can assert that every matcher hits real
corpus content, and it runs in CI **before** the harness. A golden question referencing a
citation that is not in the corpus would otherwise produce a permanent failure that looks
exactly like a retrieval bug.

### Scores are reported per question type

Five types: `single_hop`, `cross_document`, `jurisdiction`, `status_sensitive`, and
`refusal`/`out_of_scope`.

An aggregate score hides the only failures worth knowing about. A system can score well
overall while failing every cross-document question, because single-hop lookups dominate
any realistic question set. This corpus was chosen specifically to contain hard
cross-document cases, so collapsing them into an average would discard the reason the
corpus was chosen.

### Abstention is scored, not ignored

`refusal` and `out_of_scope` items expect *no* evidence. Correct behaviour is declining.
They are scored on `abstain_rate` and excluded from `hit@k`/`recall@k`, because a retrieval
metric computed over questions with no correct answer is meaningless.

Conversely, an answerable question that the system abstains on is scored **incorrect** even
though no wrong citation was produced. Silence on an answerable question is a failure, just
a quieter one.

### Regression detection gates CI

Runs write `eval/results/latest.json`. If `baseline.json` exists, every metric is compared
and the run exits non-zero when any drops by more than `REGRESSION_TOLERANCE = 0.02`.
Retrieval quality then fails CI exactly like a broken unit test.

Tolerance is not zero because embedding on different hardware can produce tiny float
differences. It is small enough that a real regression cannot hide inside it.

## Options rejected

**LLM-as-judge.** Score answers by asking a model whether they are good. Rejected: it adds
a non-deterministic, unversioned dependency to the one component that exists to be a stable
reference, it costs money per run, and it cannot be run air-gapped. It also measures
phrasing, whereas the failures in this system are retrieval failures.

**Exact answer strings.** Brittle, and they measure generation rather than retrieval. The
extractive composer returns verbatim source text, so the meaningful question is whether the
right provision was found.

**Aggregate score only.** Rejected above — it hides the cross-document failures the corpus
was chosen to expose.

**Larger auto-generated question set.** A thousand model-generated questions would look
more rigorous and be worth less: ground truth would be model-assumed rather than verifiable,
and the set would inherit the retriever's own blind spots. Thirty-two hand-written
questions whose answers can each be checked against a citation are stronger evidence.

## Consequences

- The golden set is small and must grow deliberately. Each new item needs a `why` naming
  the provision that makes it correct.
- The harness measures retrieval only. If LLM synthesis is added later it needs its own
  evaluation; these numbers will not cover it.
- `eval/results/baseline.json` is committed, so a reviewer can see what the numbers were
  and when they changed.
