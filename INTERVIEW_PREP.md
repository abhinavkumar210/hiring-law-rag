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
