"""Local embedding via nomic-embed-text-v1.5.

TASK PREFIXES ARE NOT OPTIONAL. This model was trained with instruction prefixes
and expects:

    documents -> "search_document: <text>"
    queries   -> "search_query: <text>"

Using the wrong prefix, or the same prefix for both, does not raise an error. It
just makes retrieval quietly worse, which is the hardest class of bug to notice.
Both directions are therefore funnelled through explicit functions here rather
than left to callers to remember.
"""
from __future__ import annotations

import functools

import numpy as np

MODEL_NAME = "nomic-ai/nomic-embed-text-v1.5"
DOC_PREFIX = "search_document: "
QUERY_PREFIX = "search_query: "
DIM = 768


@functools.lru_cache(maxsize=1)
def _model():
    from sentence_transformers import SentenceTransformer

    # trust_remote_code executes code from the model repo. Acceptable for a
    # public research project; see ADR 0003 for why it would not be acceptable
    # unreviewed in a federal deployment.
    return SentenceTransformer(MODEL_NAME, trust_remote_code=True, device="cpu")


def _encode(texts: list[str], prefix: str, batch_size: int = 16) -> np.ndarray:
    if not texts:
        return np.zeros((0, DIM), dtype=np.float32)
    vecs = _model().encode(
        [prefix + t for t in texts],
        batch_size=batch_size,
        convert_to_numpy=True,
        normalize_embeddings=True,  # cosine similarity becomes a dot product
        show_progress_bar=False,
    )
    return vecs.astype(np.float32)


def embed_documents(texts: list[str], batch_size: int = 16) -> np.ndarray:
    return _encode(texts, DOC_PREFIX, batch_size)


def embed_queries(texts: list[str], batch_size: int = 16) -> np.ndarray:
    return _encode(texts, QUERY_PREFIX, batch_size)


def cosine(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Cosine similarity for already-normalised vectors."""
    return a @ b.T
