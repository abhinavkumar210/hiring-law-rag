"""FastAPI service over the retrieval index.

Thin by design. All guardrails live in the composer (src/answer/compose.py) so
they hold regardless of entry point - HTTP, CLI, or tests. An API layer that
enforced its own rules would be a second place for them to drift.
"""
from __future__ import annotations

import pathlib
import sys

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from answer.compose import compose  # noqa: E402
from retrieve.search import Index  # noqa: E402

app = FastAPI(
    title="hiring-law-rag",
    description=(
        "Citation-grounded retrieval over US employment-discrimination "
        "regulations and AI-hiring rules. Reports what published regulations "
        "say. Does not give legal advice."
    ),
    version="0.1.0",
)

_index: Index | None = None


def get_index() -> Index:
    global _index
    if _index is None:
        try:
            _index = Index.load()
        except FileNotFoundError as exc:
            raise HTTPException(
                status_code=503,
                detail=f"{exc} (the index must be built before serving)",
            ) from exc
    return _index


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=2000)
    k: int = Field(default=5, ge=1, le=20)


@app.get("/health")
def health() -> dict:
    try:
        idx = Index.load()
    except FileNotFoundError as exc:
        return {"status": "degraded", "index": "missing", "detail": str(exc)}
    return {
        "status": "ok",
        "index": "loaded",
        "chunks": idx.meta.get("n_chunks"),
        "model": idx.meta.get("model"),
    }


@app.post("/ask")
def ask(req: AskRequest) -> dict:
    return compose(req.question, get_index(), k=req.k).to_dict()


@app.post("/search")
def search(req: AskRequest) -> dict:
    """Raw retrieval without composition. For debugging relevance."""
    results = get_index().search(req.question, k=req.k)
    return {
        "question": req.question,
        "abstain": get_index().should_abstain(results),
        "results": [
            {
                "rank": r.rank,
                "score": round(r.score, 4),
                "citations": r.citations,
                "jurisdiction": r.jurisdiction,
                "status": r.status,
                "excerpt": r.body[:300],
            }
            for r in results
        ],
    }
