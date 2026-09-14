"""Local embedding via gte-modernbert-base.

MODEL CHANGE — see ADR 0003. The original choice, nomic-embed-text-v1.5, requires
trust_remote_code=True, and that custom code targets transformers 4.x. Under
transformers 5.x it fails at forward() with a missing
`get_extended_attention_mask`. gte-modernbert-base reaches the same 8,192-token
context using ModernBERT, which transformers supports natively, so no third-party
code executes at load time.

NO TASK PREFIXES. nomic-embed requires "search_document: " / "search_query: "
prefixes; gte-modernbert is trained symmetrically and does not. Carrying the
nomic convention over would not raise an error — it would just prepend noise to
every vector and quietly degrade retrieval. Documents and queries are therefore
encoded identically here, and the two functions are kept separate only so that
swapping in an asymmetric model later is a one-file change.
"""
from __future__ import annotations

import functools

import numpy as np

MODEL_NAME = "Alibaba-NLP/gte-modernbert-base"
MAX_SEQ_LENGTH = 8192
DIM = 768


@functools.lru_cache(maxsize=1)
def _model():
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(MODEL_NAME, device="cpu")
    model.max_seq_length = MAX_SEQ_LENGTH
    return model


def _encode(texts: list[str], batch_size: int = 8) -> np.ndarray:
    if not texts:
        return np.zeros((0, DIM), dtype=np.float32)
    vecs = _model().encode(
        texts,
        batch_size=batch_size,
        convert_to_numpy=True,
        normalize_embeddings=True,  # cosine similarity becomes a dot product
        show_progress_bar=False,
    )
    return vecs.astype(np.float32)


def embed_documents(texts: list[str], batch_size: int = 8) -> np.ndarray:
    return _encode(texts, batch_size)


def embed_queries(texts: list[str], batch_size: int = 8) -> np.ndarray:
    return _encode(texts, batch_size)


def cosine(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Cosine similarity for already-normalised vectors."""
    return a @ b.T
