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

    def should_abstain(self, results: list[Result]) -> bool:
        return not results or results[0].score < ABSTAIN_THRESHOLD


_INDEX: Index | None = None


def get_index() -> Index:
    global _INDEX
    if _INDEX is None:
        _INDEX = Index.load()
    return _INDEX
