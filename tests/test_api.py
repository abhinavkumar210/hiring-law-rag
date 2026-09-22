"""API tests.

These need the built vector index, so they skip when it is absent rather than
failing. CI runs unit tests without the index (fast) and the evaluation job
builds it (slow); this keeps both honest about what they cover.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

import pytest

PROCESSED = pathlib.Path(__file__).resolve().parents[1] / "data" / "processed"

pytestmark = pytest.mark.skipif(
    not (PROCESSED / "embeddings.npy").exists(),
    reason="vector index not built - run src/index/build_index.py",
)


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    from api.app import app

    return TestClient(app)


def test_health_reports_a_loaded_index(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["chunks"] > 0


def test_ask_returns_citations_for_an_answerable_question(client):
    r = client.post("/ask", json={"question": "What selection rate is evidence of adverse impact?"})
    assert r.status_code == 200
    body = r.json()
    assert not body["refused"]
    assert body["citations"], "an answer must carry citations"
    flat = [c for cit in body["citations"] for c in cit["citations"]]
    assert any("1607.4(D)" in c for c in flat), flat


def test_ask_refuses_legal_advice(client):
    r = client.post("/ask", json={"question": "Should I settle the lawsuit against my company?"})
    body = r.json()
    assert body["refused"]
    assert body["citations"] == []


def test_ask_refuses_out_of_scope(client):
    r = client.post("/ask", json={"question": "What is the minimum wage in New Jersey?"})
    assert r.json()["refused"]


def test_withdrawn_source_carries_a_disclosure(client):
    r = client.post(
        "/ask",
        json={"question": "What does the EEOC say about adverse impact in AI hiring tools?"},
    )
    body = r.json()
    if body["refused"]:
        pytest.skip("question abstained; covered by the harness instead")
    statuses = [c["status"] for c in body["citations"]]
    if any(s != "in_force" for s in statuses):
        assert body["disclosures"], "withdrawn sources must be disclosed"


def test_rejects_malformed_input(client):
    assert client.post("/ask", json={"question": "hi", "k": 5}).status_code == 422
    assert client.post("/ask", json={"question": "a valid question here", "k": 99}).status_code == 422
