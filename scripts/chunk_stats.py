"""Compare chunking strategies across the whole corpus. Numbers only, no claims."""
import json
import pathlib
import statistics
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from index.chunkers import TOKENIZER, fixed_window, structural  # noqa: E402
from ingest.parse_ecfr import parse_part  # noqa: E402

RAW = ROOT / "data" / "raw" / "ecfr"


def main() -> None:
    manifest = json.loads((ROOT / "src" / "ingest" / "sources.json").read_text("utf8"))
    names = {s["id"]: s["name"] for s in manifest["sources"]}

    all_units = {}
    for path in sorted(RAW.glob("*.xml")):
        sid = path.stem
        all_units[sid] = parse_part(path, sid)

    print(f"tokenizer: {TOKENIZER}\n")
    print(f"{'source':<20}{'units':>7}{'A chunks':>10}{'C chunks':>10}"
          f"{'C med tok':>11}{'C max tok':>11}")
    print("-" * 69)

    tot_a = tot_c = 0
    for sid, units in all_units.items():
        a = fixed_window(units)
        c = structural(units)
        tot_a += len(a)
        tot_c += len(c)
        med = statistics.median([x.n_tokens for x in c]) if c else 0
        mx = max([x.n_tokens for x in c]) if c else 0
        print(f"{sid:<20}{len(units):>7}{len(a):>10}{len(c):>10}{med:>11.0f}{mx:>11}")

    print("-" * 69)
    print(f"{'TOTAL':<20}{sum(len(u) for u in all_units.values()):>7}"
          f"{tot_a:>10}{tot_c:>10}")

    # The near-duplicate pair, measured at chunk level.
    ug, of = all_units["ugesp"], all_units["ofccp_60_3"]
    a_ug = {x.embed_text for x in fixed_window(ug)}
    a_of = {x.embed_text for x in fixed_window(of)}
    c_ug = {x.embed_text for x in structural(ug)}
    c_of = {x.embed_text for x in structural(of)}
    b_ug = {x.body for x in structural(ug)}
    b_of = {x.body for x in structural(of)}

    print("\n29 CFR 1607 vs 41 CFR 60-3 — identical embedded chunks")
    print(f"  raw bodies identical across parts : {len(b_ug & b_of)}")
    print(f"  strategy A collisions             : {len(a_ug & a_of)}")
    print(f"  strategy C collisions             : {len(c_ug & c_of)}")


if __name__ == "__main__":
    main()
