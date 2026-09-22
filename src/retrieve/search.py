"""Retrieval over the built index.

Loads the persisted chunks and embeddings, embeds a query, and returns the
top-k nearest chunks. Vectors are L2-normalised at build time, so cosine
similarity is a dot product and the whole index is one matrix multiply — at 754
chunks there is no case for an approximate index, and a brute-force search that
is exact and obvious beats one that is fast and wrong.

Abstention is part of retrieval, not an afterthought. If the best match scores
below ABSTAIN_THRESHOLD the corpus does not contain an answer, and the honest
response is to say so. A compliance tool that always returns its nearest
paragraph is worse than one that admits the question is out of scope.
"""
from __future__ import annotations

import dataclasses
import json
import pathlib
import sys

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from index.embed import embed_queries  # noqa: E402

PROCESSED = ROOT / "data" / "processed"

# Calibrated against the out-of-scope and refusal items in the golden set; see
# ADR 0006. Raising it trades recall for fewer confident wrong answers.
ABSTAIN_THRESHOLD = 0.62

# Cross-document retrieval. Measured on this corpus: the query "where does the
# 80 percent benchmark in NYC bias audits come from?" puts 29 CFR 1607.4(D) at
# rank 28, because the whole top-20 is NYC documents - the query speaks 2023 NYC
# vocabulary and the answer is written in 1978 federal vocabulary.
#
# Using a retrieved chunk as its own query crosses that gap: from the NYC bias
# audit rule, 1607.4(D) is at cross-source rank 3. So the second hop asks "what
# else in the corpus, from a different source, is about this?" - which is the
# cross-reference relationship the embedding space does not encode.
#
# Slots are reserved rather than merged by score, so hop-2 results cannot crowd
# out direct answers to single-hop questions. See ADR 0008.
MULTIHOP_SEEDS = 2      # how many stage-1 results to expand from
MULTIHOP_RESERVE = 2    # slots in the final k reserved for cross-source hits


@dataclasses.dataclass
class Result:
    rank: int
    score: float
    chunk_id: str
    citations: list[str]
    source_ids: list[str]
    jurisdiction: str
    status: str
    body: str


class Index:
    def __init__(self, chunks: list[dict], vectors: np.ndarray, meta: dict):
        if len(chunks) != vectors.shape[0]:
            raise ValueError(
                f"index corrupt: {len(chunks)} chunks but {vectors.shape[0]} vectors"
            )
        self.chunks = chunks
        self.vectors = vectors
        self.meta = meta

    @classmethod
    def load(cls, processed: pathlib.Path = PROCESSED) -> "Index":
        chunks_path = processed / "chunks.jsonl"
        vecs_path = processed / "embeddings.npy"
        if not chunks_path.exists() or not vecs_path.exists():
            raise FileNotFoundError(
                "index not built - run: python src/index/build_index.py"
            )
        chunks = [
            json.loads(line)
            for line in chunks_path.read_text(encoding="utf8").splitlines()
            if line.strip()
        ]
        vectors = np.load(vecs_path)
        meta = json.loads((processed / "index_meta.json").read_text(encoding="utf8"))
        return cls(chunks, vectors, meta)

    def search(
        self,
        query: str,
        k: int = 5,
        jurisdiction: str | None = None,
        include_withdrawn: bool = True,
    ) -> list[Result]:
        qv = embed_queries([query])[0]
        scores = self.vectors @ qv

        mask = np.ones(len(self.chunks), dtype=bool)
        if jurisdiction is not None:
            mask &= np.array(
                [c.get("jurisdiction") == jurisdiction for c in self.chunks]
            )
        if not include_withdrawn:
            mask &= np.array([c.get("status") == "in_force" for c in self.chunks])
        scores = np.where(mask, scores, -np.inf)

        top = np.argsort(-scores)[:k]
        out = []
        for rank, i in enumerate(top, start=1):
            if not np.isfinite(scores[i]):
                break
            c = self.chunks[i]
            out.append(
                Result(
                    rank=rank,
                    score=float(scores[i]),
                    chunk_id=c["chunk_id"],
                    citations=c["citations"],
                    source_ids=c.get("source_ids", [c["source_id"]]),
                    jurisdiction=c.get("jurisdiction", "unknown"),
                    status=c.get("status", "in_force"),
                    body=c["body"],
                )
            )
        return out

    def search_multihop(
        self,
        query: str,
        k: int = 5,
        seeds: int = MULTIHOP_SEEDS,
        reserve: int = MULTIHOP_RESERVE,
    ) -> list[Result]:
        """Retrieve, then expand from the top results into other sources.

        Stage 1 answers the question as asked. Stage 2 takes the best stage-1
        chunks and asks what else, in a *different* source, is about the same
        thing. The reserved slots are filled from stage 2 only by chunks not
        already present, so a question fully answered by stage 1 loses at most
        `reserve` of its lower-ranked direct hits.
        """
        reserve = max(0, min(reserve, k - 1))
        direct = self.search(query, k=k)
        if reserve == 0 or not direct:
            return direct

        seen = {r.chunk_id for r in direct}
        expanded: list[Result] = []

        # Two different gaps need two different hops, and measurement showed
        # each one fixes what the other misses:
        #
        #   cross-JURISDICTION  NYC's bias-audit rule depends on a federal
        #                       threshold. Excluding only the seed's source sent
        #                       the hop sideways from nyc_ll144_rules into
        #                       nyc_aedt_faq - same regime, no new information.
        #                       Excluding the jurisdiction forces the crossing.
        #
        #   cross-SOURCE        withdrawn EEOC guidance and UGESP are both
        #                       US-federal, so a jurisdiction hop can never link
        #                       them. Excluding the source does.
        #
        # Using only the first lost cross_document; only the second lost
        # jurisdiction and status_sensitive. See ADR 0008.
        strategies = (
            lambda hit, seed: hit.jurisdiction != seed.jurisdiction,
            lambda hit, seed: not (set(hit.source_ids) & set(seed.source_ids)),
        )

        for strategy in strategies[:reserve]:
            for seed in direct[:seeds]:
                picked = False
                for hit in self.search(seed.body, k=k + 40):
                    if hit.chunk_id in seen or not strategy(hit, seed):
                        continue
                    seen.add(hit.chunk_id)
                    expanded.append(hit)
                    picked = True
                    break
                if picked:
                    break

        if not expanded:
            return direct

        kept = direct[: k - len(expanded)]
        merged = kept + expanded[: k - len(kept)]
        for rank, r in enumerate(merged, start=1):
            r.rank = rank
        return merged

    def should_abstain(self, results: list[Result]) -> bool:
        return not results or results[0].score < ABSTAIN_THRESHOLD


_INDEX: Index | None = None


def get_index() -> Index:
    global _INDEX
    if _INDEX is None:
        _INDEX = Index.load()
    return _INDEX
