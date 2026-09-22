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

### 2026-09-14 — Quiz 1, re-ask

**Q1 — pass on substance.** Two refinements:
- Precision: LL144 *does* require computing an impact ratio. What it omits is the
  *acceptable threshold*. Say "no defined threshold," not "no defined impact ratio" —
  an employment-side interviewer will hear the difference.
- Incomplete: the legal chain is only half the answer. The other half is why it's a
  hard *retrieval* problem — 45 years apart, no shared vocabulary, neither cites the
  other, so embedding similarity will never connect them. That half is what makes it
  your project rather than a legal fact.

**Q2 — pass.** Both reasons present, led with ground-truth stability. Factual error
about federal case law is gone.

**Q3 — good instinct, one refinement.** Correctly identified the tension: bigger
chunks help disambiguate near-duplicates, but chunking finer risks breaking the
cross-document dependency.
Refinement: **chunk size cannot fix the cross-document hop at all.** No chunk size
makes an embedding model connect "impact ratio" (2023) to "four-fifths" (1978) —
that needs a different mechanism (query expansion, a second retrieval hop, or
explicit cross-reference edges). Knowing which problem a given knob *can't* solve is
the senior answer.
So: chunking is aimed at the near-duplicate problem. The cross-document hop is a
separate decision, deferred to its own ADR.


## Measured results worth quoting

**Near-duplicate separation, 29 CFR 1607 vs 41 CFR 60-3** (67 byte-identical bodies,
gte-modernbert-base):

| | mean cosine | pairs > 0.99 |
|---|---|---|
| no citation header | 1.0001 | 67 / 67 |
| with citation header | 0.9515 | 0 / 67 |

The header moved every pair below 0.99 but only bought +0.049 mean separation — not
enough to reorder a ranked list. A probe query about *federal contractor* obligations
still ranked 29 CFR 1607 (EEOC, not contractors) above 41 CFR 60-3 (OFCCP, contractors).

**The story this supports:** "I hypothesised that embedding the citation would separate
two near-identical regulations. I measured it. It moved similarity from 1.00 to 0.95,
which sounds like a win until you notice 0.95 still ranks the wrong document first. So I
stopped trying to solve a metadata problem in embedding space and filtered on
jurisdiction instead."

That is a stronger answer than if the hypothesis had simply worked.

---

# Build-out notes (2026-09-22)

## Four findings, in order of how well they land

**1. PDF extraction corrupted "four-fifths" 19 times, silently.**
`pypdf` emits NUL (0x00) where a glyph has no character mapping. In the EEOC guidance that
hit f-ligatures: `four-fi\x00hs`. Unrepaired, the one federal document about applying the
four-fifths rule to AI would never match a query about the four-fifths rule, and nothing
raises an error.
Why it lands: it is a concrete, specific, *silent* data-quality bug in the most important
term in the corpus. The repair reports what it cannot resolve instead of guessing.
Follow-up they will ask: "how did you find it?" Answer: the units looked too large, so I
inspected the raw extraction, saw a gap, and checked the codepoints. It was a NUL, not a
space — which is why searching for "arti cial" found nothing.

**2. The EEOC withdrew its AI hiring guidance in January 2025.**
Both documents 404 on eeoc.gov. Not stale links — removed.
Why it lands: it retroactively validated the scope decision. The rejected "AI rules only"
corpus would have been built largely from guidance that has since been rescinded. The
foundation layer was chosen for retrieval reasons and turned out to be the layer still in
force. UGESP is from 1978 and still governs.
The design consequence: withdrawn guidance is *kept*, with status metadata that travels
into the embedded text and into the answer, and the composer cannot construct an answer
citing it without a disclosure.

**3. The header hypothesis was measured and half-refuted.**
See the results table above. Moving similarity 1.00 -> 0.95 sounds like a win until you
notice 0.95 still ranks the wrong jurisdiction first.
The better insight underneath: a federal contractor is subject to *both* 41 CFR 60-3 and
29 CFR 1607. So the system was never failing to pick the right document — it was failing to
disclose which regime it was quoting. That reframes a ranking problem as a disclosure
problem, and the fix became deduplication, not reranking.

**4. Writing the deduplicator generically found nine duplicate relationships I did not
know existed**, including a three-way overlap, because it was not special-cased to the one
pair I had measured.

## Numbers that are real (all measured, none estimated)

| | |
|---|---|
| corpus | 754 chunks, 13 sources, 718 distinct citations |
| near-duplicate cosine, no header | 1.0001 mean, 67/67 pairs > 0.99 |
| near-duplicate cosine, with header | 0.9515 mean, 0/67 pairs > 0.99 |
| dedup | 760 -> 683 eCFR chunks, 76 multi-citation |
| parser fix | 335 -> 760 units; largest chunk 5,138 -> 1,726 est. tokens |
| chunk size | median 119 est. tokens, p99 1,410, max 1,726 |
| ligature corruption | 82 NUL sites, 19 in "four-fifths", 1 unresolved |
| golden set | 32 questions, 5 types, all matchers validated against corpus |

## Questions to be ready for

**"Why is a 1978 regulation in an AI project?"** — LL144 defines the test but not the
threshold; the threshold is 29 CFR 1607.4(D), which LL144 never cites; 45 years apart, no
shared vocabulary, so embedding similarity will never connect them. That is the retrieval
failure the harness measures.

**"How do you know retrieval works?"** — 32 hand-written golden questions with expected
evidence expressed as citation matchers, validated in CI against the corpus so a bad golden
item cannot masquerade as a retrieval bug. Scored per type because an aggregate hides
cross-document failures. Regression gate at 2 points fails CI.

**"Why not LLM-as-judge?"** — non-deterministic, unversioned, costs money per run, cannot
run air-gapped, and it measures phrasing when the failures here are retrieval failures.

**"Why not OpenAI embeddings?"** — strongest reason is the air-gapped deployment case, not
cost: a federal deployment frequently cannot send regulated queries to a third-party API.
Second reason: re-indexing is free, and tuning the harness means rebuilding the index many
times. Third: it exercises no local-model skills.

**"Describe a bug that would not throw an error."** — three from this project: the NUL
ligature corruption; the parser knowing only one of two CFR numbering conventions and
collapsing 514 paragraphs into 16 chunks; and using the wrong task prefix after a model
swap (nomic needs `search_document:`, gte-modernbert needs none).

**"Tell me about testing that gave you false confidence."** — the exact-match collision
metric. It returned zero collisions, which looked clean, but it returned zero for *every*
strategy, so it could not discriminate between them. Byte equality was never the risk;
cosine similarity was. Clean metric, useless metric.

**"How do you handle a dependency you do not control?"** — nomic-embed requires
`trust_remote_code=True`; its vendor code targets transformers 4.x and dies under 5.x
inside `forward()`. Rather than pin an old transformers, I moved to gte-modernbert, which
reaches the same 8k context natively and executes no third-party code at load. The ADR had
already flagged remote code as something that would fail a federal security review, so the
failure argued for what the ADR was uneasy about.

**"Why are guardrails in types instead of prompts?"** — a prompt is a request that fails
silently and non-deterministically; a constructor that raises is a guarantee. There is no
code path that returns an uncited answer, including one written later by someone who never
read the ADR.

## Weak spots to shore up before interviewing

- [ ] Be able to whiteboard the full pipeline cold: fetch -> parse -> normalise -> chunk ->
      dedupe -> embed -> index -> retrieve -> abstain -> compose.
- [ ] Know why brute-force cosine over 754 chunks is correct and when it stops being
      correct (roughly 10^5-10^6 vectors, then HNSW/IVF).
- [ ] Be ready for "what would you do differently" — honest answer: hybrid BM25 retrieval
      for the non-duplicate remainder, and a canonical ordering rule for merged citations.
- [ ] Be able to explain why the abstention threshold is 0.62 and what moving it costs.

---

# Evaluation results and the multihop fix (2026-09-22)

## The single most valuable number in the project

| type | n | single-stage | two-stage |
|---|---|---|---|
| cross_document | 2 | **0.000** | **1.000** |
| jurisdiction | 3 | 0.667 | 1.000 |
| status_sensitive | 2 | 0.500 | 1.000 |
| single_hop | 21 | **0.952** | 0.905 |
| refusal / out_of_scope | 4 | 1.000 | 1.000 |
| **overall correct** | 32 | **0.844** | **0.938** |

**The story to tell:** "My first evaluation run scored 0.844 overall, which looks like a
working system. Broken out by question type, the cross-document category — the one the
whole corpus was chosen to test — scored zero. If I had reported a single aggregate number
I would have shipped it believing it worked."

That is the strongest thing in this repo. It is a concrete argument for a design decision
(per-type reporting) that paid off immediately and visibly.

## How the fix was found, step by step

Worth rehearsing as a debugging narrative, because it shows method rather than luck:

1. **Diagnosed before fixing.** Printed the top-5 for the failing query. The entire top-20
   was NYC documents.
2. **Checked whether the answer was even reachable.** 29 CFR 1607.4(D) was at rank 28 — in
   the index, just buried. That ruled out an ingestion problem.
3. **Tested the hypothesis before building it.** Used a retrieved NYC chunk as its own
   query: 1607.4(D) came back at cross-source rank 3. Only then wrote the code.
4. **First implementation improved the wrong things.** Excluding the seed's source fixed
   jurisdiction and status_sensitive but left cross_document at 0.000.
5. **Diagnosed that too.** `nyc_ll144_rules` and `nyc_aedt_faq` are different sources in
   the same regime, so the hop went sideways within NYC. Excluding *jurisdiction* forced a
   real crossing and fixed cross_document — but broke the other two, because withdrawn
   EEOC guidance and UGESP are both US-federal.
6. **Ran both strategies, one reserved slot each.** All three categories at 1.000.

If asked "how do you debug a retrieval problem", that sequence *is* the answer.

## The harness bug — a second false-confidence story

Both refusal questions scored 0.000 on the first run. The system was fine: refusals for
legal advice are enforced in the composer by pattern match *before* retrieval, and the
harness was calling `index.search()` directly. It was measuring the retrieval layer against
a guarantee that lives one layer up.

Lesson to state out loud: a failing metric is a claim about your measurement as much as
about your system. Know which component produced the number.

## Be ready for the cost question

They will ask what it cost, and the answer must be immediate:

> "single_hop dropped from 0.952 to 0.905. Reserving two of five slots for cross-document
> hits takes those slots from somewhere, and two questions lost their correct citation at
> rank 4 or 5. I took the trade because on this corpus the realistic questions span a local
> rule and the federal regulation underneath it, and a confidently incomplete answer to a
> cross-jurisdiction question is the worse failure. It is reversible — raise k, or drop to
> one hop strategy."

Refusing to acknowledge a cost reads as not having measured one.

## Still to shore up

- [ ] Explain why reserved slots beat score-merging. (A stage-2 hit scores lower than a
      good direct hit almost by construction, so merging by score would never surface it.)
- [ ] Explain why a diversity cap / MMR would not have worked. (Other sources sit between
      rank 5 and rank 28; capping per source still never reaches it.)
- [ ] Explain why hybrid BM25 does not bridge this gap. ("80 percent" vs "eighty percent";
      "impact ratio" appears nowhere in UGESP.)
- [ ] Two failures remain, both single_hop — know which and why.
