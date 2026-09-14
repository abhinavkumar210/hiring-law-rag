"""Fetch eCFR parts listed in sources.json.

The eCFR API requires gzip: it returns HTTP 406 with an explanatory body if the
request does not permit compression. requests sends Accept-Encoding by default,
so this works, but the constraint is documented here because it is non-obvious
and cost an hour to discover.
"""
import json
import pathlib
import sys
import time

import requests

ROOT = pathlib.Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw" / "ecfr"
MANIFEST = ROOT / "src" / "ingest" / "sources.json"
UA = "hiring-law-rag/0.1 (portfolio research project)"


def ecfr_url(date: str, title: int, part: str) -> str:
    return (
        f"https://www.ecfr.gov/api/versioner/v1/full/{date}/title-{title}.xml"
        f"?part={part}"
    )


def fetch_one(src: dict, date: str, session: requests.Session) -> dict:
    url = ecfr_url(date, src["title"], src["part"])
    dest = RAW / f"{src['id']}.xml"
    try:
        r = session.get(url, timeout=90, headers={"User-Agent": UA})
    except requests.RequestException as exc:
        return {"id": src["id"], "ok": False, "error": f"{type(exc).__name__}: {exc}"}

    if r.status_code != 200:
        return {
            "id": src["id"],
            "ok": False,
            "error": f"HTTP {r.status_code}: {r.text[:200].strip()}",
        }

    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(r.content)
    return {"id": src["id"], "ok": True, "bytes": len(r.content), "path": str(dest)}


def main() -> int:
    manifest = json.loads(MANIFEST.read_text(encoding="utf8"))
    date = manifest["ecfr_date"]
    targets = [s for s in manifest["sources"] if s["kind"] == "ecfr"]

    results = []
    with requests.Session() as session:
        for src in targets:
            res = fetch_one(src, date, session)
            results.append(res)
            if res["ok"]:
                print(f"  ok    {res['id']:<20} {res['bytes']:>9,} bytes")
            else:
                print(f"  FAIL  {res['id']:<20} {res['error']}")
            time.sleep(0.5)  # be polite to a government API

    failed = [r for r in results if not r["ok"]]
    print(f"\n{len(results) - len(failed)}/{len(results)} fetched")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
