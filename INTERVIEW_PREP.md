# Interview prep

Running notes: questions asked during the build, answers that came out weak, and
the corrections. Revise from this, not from the code.

## Corpus facts worth knowing cold

- **Four-fifths rule** lives at **29 CFR 1607.4(D)**, UGESP, published 1978
  (43 FR 38295). A selection rate below 80% of the highest-scoring group's rate is
  "evidence of adverse impact."
- **NYC Local Law 144** requires a bias audit computing an "impact ratio" but does
  **not** define an acceptable threshold in its operative text. The threshold comes
  from UGESP. Two documents, 45 years apart, no citation between them.
- **29 CFR 1607 vs 41 CFR 60-3** are 99.6% textually identical (562 shared
  sentences, ~100 unique to each). 1607 is EEOC and reaches most employers; 60-3
  is OFCCP and reaches federal contractors. Same words, different jurisdiction.

## Measured, not asserted

| Claim | How it was measured | Result |
|---|---|---|
| 1607 and 60-3 are near-duplicates | `difflib.SequenceMatcher.quick_ratio` on tag-stripped text | 0.996 |
| Shared sentence count | set intersection on sentence split | 562 shared, 103 / 92 unique |

## Open questions to answer later

- [ ] What chunking strategy, and why that one?
- [ ] How does retrieval distinguish 1607 from 60-3?
- [ ] What does the harness measure, and against what golden set?

## Quiz log

<!-- Date | question | how the answer went | what to fix -->

### 2026-09-14 — Quiz 1 (post-ingestion)

**Q1. Why does the corpus include a 1978 regulation?**
Answered: unsure; guessed it related to discrimination factors.
Verdict: **weak — this is the thesis of the project and must be automatic.**
Correct chain:
1. NYC LL144 (2023) requires an annual bias audit computing an "impact ratio."
2. LL144 never states what ratio is acceptable.
3. The benchmark is the four-fifths rule, 29 CFR 1607.4(D), published 1978.
4. So "does my tool pass?" needs both documents, 45 years apart, neither citing
   the other, with almost no shared vocabulary.
One-sentence version to have ready:
> "The modern law defines the test but not the threshold. The threshold is in a
> 1978 regulation the 2023 law never cites — and that cross-document hop is the
> retrieval failure my evaluation harness was built to catch."

**Q2. How would vector search behave on two 99.6%-identical documents?**
Answered: finer-grained embeddings to reduce similarity; or build a document of
the differences.
Verdict: **half credit.** The "document of differences" instinct is right and is a
real technique. The "finer granularity reduces similarity" mechanism is backwards:
the two documents share 562 sentences, so at smaller chunk sizes those chunks
become *byte-identical* and cosine similarity goes to 1.0. Finer chunking makes
this failure worse, not better.
Correct framing: this is not solvable in embedding space, because the documents
genuinely mean the same thing — they differ in *who they bind*, which is metadata,
not semantics. Fixes are (a) jurisdiction metadata on every chunk plus filtering
on user context, (b) dedupe shared text and index only the deltas separately,
(c) mandatory citation in the answer so the user sees which title it came from.

**Q3. Justify excluding case law.**
Answered: case law is not federally applied, subject matter still new, better to
use nationally applied law.
Verdict: **contains a factual error — fix before any interview.** Federal case law
*is* federally applied. Griggs v. Duke Power (1971) is a unanimous Supreme Court
decision binding nationwide and is the origin of disparate impact doctrine itself.
Saying otherwise in front of anyone in employment or govcon is costly.
The two correct reasons, both already in ADR 0001:
1. **Structural** — judicial opinions are shaped nothing like regulations, so they
   need a second ingestion path. That delays the evaluation harness, which is the
   centerpiece.
2. **Ground-truth instability** — Mobley v. Workday is in active litigation, so the
   correct answer changes over time. A golden set requires stable ground truth.
   (The seed of this was in the "subject matter is still new" instinct — it just
   needs to be aimed at the golden set rather than at the law.)
Reason 2 is the stronger answer because it shows evaluation-first thinking.
