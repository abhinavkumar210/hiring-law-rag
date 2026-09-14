"""Two chunking strategies, built to be compared.

Strategy A (fixed_window) is the baseline. It is deliberately naive: uniform
token windows with overlap, ignoring document structure. It exists so that
Strategy C's improvement can be stated as a number rather than an opinion.

Strategy C (structural) chunks on regulatory subsection boundaries and prepends
each chunk's own citation to the embedded text. That header is the fix for the
near-duplicate problem: 29 CFR 1607 and 41 CFR 60-3 share 562 identical
sentences, so without a header their chunks embed identically. With it, every
chunk carries its jurisdiction inside the vector.

Token counting uses tiktoken when available and falls back to a word-count
estimate. The fallback is an approximation, so chunk sizes are approximate — but
both strategies are measured with the same counter, so the comparison is fair.
"""
from __future__ import annotations

import dataclasses
import re

from ingest.parse_ecfr import Unit

try:  # pragma: no cover - depends on environment
    import tiktoken

    _ENC = tiktoken.get_encoding("cl100k_base")

    def count_tokens(text: str) -> int:
        return len(_ENC.encode(text))

    TOKENIZER = "tiktoken/cl100k_base"
except ImportError:  # pragma: no cover
    _WORD = re.compile(r"\S+")
    # Empirically ~1.3 tokens per whitespace word for English legal prose.
    _TOKENS_PER_WORD = 1.3

    def count_tokens(text: str) -> int:
        return int(len(_WORD.findall(text)) * _TOKENS_PER_WORD)

    TOKENIZER = "word-estimate/1.3"


@dataclasses.dataclass
class Chunk:
    chunk_id: str
    strategy: str
    embed_text: str          # what actually gets embedded
    body: str                # the regulatory text alone, without any header
    source_id: str
    citations: list[str]     # every citation this chunk's text covers
    n_tokens: int


def structural(units: list[Unit]) -> list[Chunk]:
    """Strategy C — one chunk per subsection, citation header embedded."""
    chunks = []
    for i, u in enumerate(units):
        header = f"{u.part_title} | {u.section_heading} | {u.full_citation}"
        header = re.sub(r"\s+", " ", header).strip()
        embed_text = f"{header}\n\n{u.text}"
        chunks.append(
            Chunk(
                chunk_id=f"{u.source_id}:C:{i}",
                strategy="structural",
                embed_text=embed_text,
                body=u.text,
                source_id=u.source_id,
                citations=[u.full_citation],
                n_tokens=count_tokens(embed_text),
            )
        )
    return chunks


def fixed_window(
    units: list[Unit], size: int = 512, overlap: int = 64
) -> list[Chunk]:
    """Strategy A — uniform windows over the flattened part text.

    Each window records every citation it overlaps. A window that straddles a
    section boundary genuinely covers both, and scoring it as covering both is
    the fair comparison: it does not penalise the baseline for the structure it
    was never given.
    """
    if overlap >= size:
        raise ValueError("overlap must be smaller than size")

    words: list[str] = []
    provenance: list[str] = []
    for u in units:
        for w in u.text.split():
            words.append(w)
            provenance.append(u.full_citation)

    if not words:
        return []

    # Window sizes are expressed in tokens; convert to words with the same ratio
    # the fallback counter uses so both strategies share one notion of size.
    step_words = max(1, int((size - overlap) / 1.3))
    win_words = max(1, int(size / 1.3))

    source_id = units[0].source_id
    chunks = []
    for start in range(0, len(words), step_words):
        window = words[start : start + win_words]
        if not window:
            break
        text = " ".join(window)
        seen = list(dict.fromkeys(provenance[start : start + win_words]))
        chunks.append(
            Chunk(
                chunk_id=f"{source_id}:A:{start}",
                strategy="fixed_window",
                embed_text=text,
                body=text,
                source_id=source_id,
                citations=seen,
                n_tokens=count_tokens(text),
            )
        )
        if start + win_words >= len(words):
            break
    return chunks
