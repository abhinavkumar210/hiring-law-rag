"""Fetch the AI-specific layer: HTML and PDF sources outside eCFR.

Unlike the eCFR tier these are heterogeneous, and two behaviours need handling:

  * EUR-Lex answers 202 Accepted while it renders a document, and returns an
    empty body. It must be retried rather than treated as a failure.
  * Some sources are archived copies of withdrawn guidance. Those carry a status
    of WITHDRAWN in the manifest, and that status must survive into the index —
    quoting rescinded guidance as if current would be a serious error in a
    compliance tool.

Failures are reported, not raised. A missing source should not block the corpus.
"""
from __future__ import annotations

import io
import json
import pathlib
import sys
import time

import requests

ROOT = pathlib.Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw" / "ai_layer"
MANIFEST = ROOT / "src" / "ingest" / "ai_layer_sources.json"
UA = "Mozilla/5.0 (compatible; hiring-law-rag/0.1; research project)"


def _get(url: str, session: requests.Session, attempts: int = 5) -> requests.Response:
    """GET with retry for 202 Accepted (EUR-Lex renders asynchronously)."""
    last = None
    for i in range(attempts):
        r = session.get(url, timeout=90, headers={"User-Agent": UA}, allow_redirects=True)
        last = r
        if r.status_code == 200 and r.content:
            return r
        if r.status_code == 202:
            time.sleep(3 * (i + 1))
            continue
        break
    return last


def pdf_to_text(data: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    return "\n\n".join((page.extract_text() or "") for page in reader.pages)


def html_to_text(data: bytes) -> str:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(data, "lxml")
    for tag in soup(["script", "style", "nav", "header", "footer"]):
        tag.decompose()
    return soup.get_text("\n")


def main() -> int:
    manifest = json.loads(MANIFEST.read_text(encoding="utf8"))
    RAW.mkdir(parents=True, exist_ok=True)
    results = []

    with requests.Session() as session:
        for src in manifest["sources"]:
            try:
                r = _get(src["url"], session)
            except requests.RequestException as exc:
                results.append((src["id"], False, f"{type(exc).__name__}: {exc}"))
                print(f"  FAIL  {src['id']:<22} {type(exc).__name__}")
                continue

            if r is None or r.status_code != 200 or not r.content:
                code = "no response" if r is None else r.status_code
                results.append((src["id"], False, f"HTTP {code}"))
                print(f"  FAIL  {src['id']:<22} HTTP {code}")
                continue

            try:
                text = (
                    pdf_to_text(r.content)
                    if src["kind"] == "pdf"
                    else html_to_text(r.content)
                )
            except Exception as exc:  # noqa: BLE001 - extraction libs raise broadly
                results.append((src["id"], False, f"extract: {type(exc).__name__}"))
                print(f"  FAIL  {src['id']:<22} extract {type(exc).__name__}")
                continue

            (RAW / f"{src['id']}.txt").write_text(text, encoding="utf8")
            (RAW / f"{src['id']}.meta.json").write_text(
                json.dumps(src, indent=2), encoding="utf8"
            )
            flag = "" if src["status"] == "in_force" else f"  [{src['status']}]"
            print(f"  ok    {src['id']:<22} {len(text):>9,} chars{flag}")
            results.append((src["id"], True, len(text)))
            time.sleep(0.5)

    ok = sum(1 for _, good, _ in results if good)
    print(f"\n{ok}/{len(results)} fetched")
    for sid, good, info in results:
        if not good:
            print(f"  unresolved: {sid} ({info})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
