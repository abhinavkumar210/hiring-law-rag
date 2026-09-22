"""Build the vector index over the full corpus.

Combines the eCFR foundation layer and the AI-specific layer, deduplicates
identical bodies across parts (ADR 0004), embeds everything locally, and writes
the index to disk so the evaluation harness can re-run without re-embedding.

Embedding is the slow step — roughly 2 seconds per chunk on CPU — so the index
is cached and only rebuilt when the chunk set changes.
"""
from __future__ import annotations

import dataclasses
import json
import pathlib
import sys
import time

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from index.chunkers import deduplicate, structural  # noqa: E402
from index.embed import MODEL_NAME, embed_documents  # noqa: E402
from ingest.parse_ai_layer import parse_all as parse_ai  # noqa: E402
from ingest.parse_ecfr import parse_part  # noqa: E402

ECFR = ROOT / "data" / "raw" / "ecfr"
AI = ROOT / "data" / "raw" / "ai_layer"
OUT = ROOT / "data" / "processed"


def build_chunks():
    units = []
    for path in sorted(ECFR.glob("*.xml")):
        units.extend(parse_part(path, path.stem))
    units.extend(parse_ai(AI))
    return deduplicate(structural(units))


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    chunks = build_chunks()
    print(f"chunks: {len(chunks)}")

    t0 = time.time()
    vecs = embed_documents([c.embed_text for c in chunks], batch_size=8)
    elapsed = time.time() - t0
    print(f"embedded {len(chunks)} chunks in {elapsed:.0f}s "
          f"({elapsed / max(1, len(chunks)):.2f}s/chunk)")

    np.save(OUT / "embeddings.npy", vecs)
    with (OUT / "chunks.jsonl").open("w", encoding="utf8") as fh:
        for c in chunks:
            fh.write(json.dumps(dataclasses.asdict(c), ensure_ascii=False) + "\n")
    (OUT / "index_meta.json").write_text(
        json.dumps(
            {
                "model": MODEL_NAME,
                "n_chunks": len(chunks),
                "dim": int(vecs.shape[1]),
                "build_seconds": round(elapsed, 1),
            },
            indent=2,
        ),
        encoding="utf8",
    )
    print(f"wrote {OUT / 'embeddings.npy'} {vecs.shape}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
