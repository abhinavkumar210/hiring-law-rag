"""Build the vector index over the full corpus.

Combines the eCFR foundation layer and the AI-specific layer, deduplicates
identical bodies across parts (ADR 0004), embeds everything locally, and writes
the index to disk so the evaluation harness can re-run without re-embedding.

RESUMABLE BY DESIGN. Embedding 754 chunks takes ~25 minutes on CPU, and the
first attempt at this build was killed partway through when the machine slept -
losing everything, with no error and no partial output, because the job printed
nothing until it finished. Two consequences, both implemented here:

  * progress is printed per batch, so a slow run is distinguishable from a hung
    one;
  * vectors are checkpointed to disk as they are produced, keyed by a
    fingerprint of the chunk set and model, so an interrupted build resumes
    instead of restarting.

The fingerprint matters: resuming onto a changed corpus would silently pair
chunk i with a vector computed for a different chunk i. If it does not match,
the checkpoint is discarded and the build starts over.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import pathlib
import sys
import time

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from index.chunkers import deduplicate, structural  # noqa: E402
from index.embed import DIM, MODEL_NAME, embed_documents  # noqa: E402
from ingest.parse_ai_layer import parse_all as parse_ai  # noqa: E402
from ingest.parse_ecfr import parse_part  # noqa: E402

ECFR = ROOT / "data" / "raw" / "ecfr"
AI = ROOT / "data" / "raw" / "ai_layer"
OUT = ROOT / "data" / "processed"
CHECKPOINT = OUT / "checkpoint.npz"

BATCH = 8
CHECKPOINT_EVERY = 5  # batches


def build_chunks():
    units = []
    for path in sorted(ECFR.glob("*.xml")):
        units.extend(parse_part(path, path.stem))
    units.extend(parse_ai(AI))
    return deduplicate(structural(units))


def fingerprint(chunks) -> str:
    h = hashlib.sha256(MODEL_NAME.encode())
    h.update(str(BATCH).encode())
    for c in chunks:
        h.update(c.chunk_id.encode())
        h.update(str(c.n_tokens).encode())
    return h.hexdigest()


def load_checkpoint(fp: str, total: int) -> np.ndarray | None:
    if not CHECKPOINT.exists():
        return None
    try:
        data = np.load(CHECKPOINT, allow_pickle=False)
    except (OSError, ValueError) as exc:
        print(f"  checkpoint unreadable ({exc}); starting over")
        return None
    if str(data["fingerprint"]) != fp:
        print("  checkpoint is for a different corpus or model; starting over")
        return None
    vecs = data["vectors"]
    if vecs.shape[0] > total or vecs.shape[1] != DIM:
        print("  checkpoint shape does not match; starting over")
        return None
    print(f"  resuming from checkpoint at {vecs.shape[0]}/{total} chunks")
    return vecs


def save_checkpoint(fp: str, vecs: np.ndarray) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    tmp = CHECKPOINT.with_suffix(".tmp.npz")
    np.savez(tmp, fingerprint=np.array(fp), vectors=vecs)
    tmp.replace(CHECKPOINT)  # atomic: never leave a half-written checkpoint


def embed_with_progress(chunks, fp: str) -> np.ndarray:
    """Embed in length-sorted order, then restore the original order.

    A batch is padded to its longest member, so mixing a 1,726-token chunk with
    seven 119-token chunks wastes most of the compute. Sorting by length groups
    similar sizes together. sentence-transformers does this internally when
    handed the whole corpus at once, but that path gives no progress output and
    no checkpoint - so the sort is done here instead, and the permutation is
    inverted before the vectors are written.
    """
    total = len(chunks)
    order = sorted(range(total), key=lambda i: chunks[i].n_tokens)
    ordered = [chunks[i] for i in order]

    done = load_checkpoint(fp, total)
    start_at = 0 if done is None else done.shape[0]
    parts: list[np.ndarray] = [] if done is None else [done]

    t0 = time.time()
    for batch_no, i in enumerate(range(start_at, total, BATCH), start=1):
        texts = [c.embed_text for c in ordered[i : i + BATCH]]
        parts.append(embed_documents(texts, batch_size=BATCH))
        n = min(i + BATCH, total)

        elapsed = time.time() - t0
        rate = (n - start_at) / elapsed if elapsed else 0
        remaining = (total - n) / rate if rate else 0
        print(
            f"  {n:>4}/{total}  {100 * n / total:5.1f}%  "
            f"{rate:4.1f} chunks/s  eta {remaining / 60:4.1f} min",
            flush=True,
        )

        if batch_no % CHECKPOINT_EVERY == 0:
            save_checkpoint(fp, np.vstack(parts))

    sorted_vecs = np.vstack(parts)
    # invert the permutation so vectors line up with the original chunk order
    restored = np.empty_like(sorted_vecs)
    restored[np.asarray(order)] = sorted_vecs
    return restored


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    chunks = build_chunks()
    fp = fingerprint(chunks)
    print(f"chunks: {len(chunks)}  fingerprint: {fp[:12]}")

    t0 = time.time()
    vecs = embed_with_progress(chunks, fp)
    elapsed = time.time() - t0

    if vecs.shape[0] != len(chunks):
        raise RuntimeError(
            f"embedded {vecs.shape[0]} vectors for {len(chunks)} chunks"
        )

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
                "fingerprint": fp,
            },
            indent=2,
        ),
        encoding="utf8",
    )
    CHECKPOINT.unlink(missing_ok=True)
    print(f"wrote {OUT / 'embeddings.npy'} {vecs.shape} in {elapsed:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
