"""Does header injection separate 29 CFR 1607 from 41 CFR 60-3?

ADR 0002 chose strategy C on the reasoning that prepending each chunk's citation
puts jurisdiction inside the vector. That was never validated — exact-match
collision, the only metric available at the time, returned zero for every
strategy and so could not discriminate between them.

This measures the thing that actually matters: cosine similarity between chunk
pairs whose regulatory text is byte-identical across the two parts.

  without header : identical strings, so cosine is 1.000 by construction.
                   The two documents are perfectly confusable.
  with header    : the open question.

A header that moves similarity from 1.000 to 0.999 is decoration. One that moves
it far enough for a jurisdiction filter to separate the pair is a fix.
"""
import pathlib
import sys

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from index.chunkers import structural  # noqa: E402
from index.embed import MODEL_NAME, cosine, embed_documents  # noqa: E402
from ingest.parse_ecfr import parse_part  # noqa: E402

RAW = ROOT / "data" / "raw" / "ecfr"


def main() -> None:
    ug = structural(parse_part(RAW / "ugesp.xml", "ugesp"))
    of = structural(parse_part(RAW / "ofccp_60_3.xml", "ofccp_60_3"))

    by_body_of = {c.body: c for c in of}
    pairs = [(a, by_body_of[a.body]) for a in ug if a.body in by_body_of]
    print(f"model: {MODEL_NAME}")
    print(f"byte-identical bodies shared across the two parts: {len(pairs)}\n")
    if not pairs:
        return

    a_hdr = embed_documents([p[0].embed_text for p in pairs])
    b_hdr = embed_documents([p[1].embed_text for p in pairs])
    sims_hdr = np.sum(a_hdr * b_hdr, axis=1)

    # Control: same bodies with no header at all (strategy B).
    a_raw = embed_documents([p[0].body for p in pairs])
    b_raw = embed_documents([p[1].body for p in pairs])
    sims_raw = np.sum(a_raw * b_raw, axis=1)

    def row(label, s):
        print(f"  {label:<16} mean {s.mean():.4f}   min {s.min():.4f}   "
              f"max {s.max():.4f}   >0.99: {int((s > 0.99).sum())}/{len(s)}")

    print("cosine similarity between the 1607 and 60-3 copies of the same text")
    row("no header", sims_raw)
    row("with header", sims_hdr)
    print(f"\n  mean separation gained by header: {sims_raw.mean() - sims_hdr.mean():+.4f}")

    # Does the header survive contact with a real query? Retrieve across the
    # combined pool and see which part wins.
    pool = [p[0] for p in pairs] + [p[1] for p in pairs]
    pool_vecs = np.vstack([a_hdr, b_hdr])
    from index.embed import embed_queries

    queries = [
        "federal contractor obligations for employee selection procedures",
        "what does the EEOC require for adverse impact records",
    ]
    qv = embed_queries(queries)
    print("\n  top-3 retrieval across the combined pool:")
    for q, v in zip(queries, qv):
        order = np.argsort(-(cosine(v[None, :], pool_vecs)[0]))[:3]
        tops = [pool[i].source_id for i in order]
        print(f"    {q[:52]:<54} -> {tops}")


if __name__ == "__main__":
    main()
