"""Verify every expected matcher in the golden set hits real corpus content.

A golden set that references a citation which does not exist is worse than no
golden set: the harness reports a permanent failure and the cause looks like a
retrieval bug. This runs on parsed chunks rather than the built index, so it is
fast and needs no embeddings, and it belongs in CI ahead of the harness itself.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from eval.harness import load_golden  # noqa: E402
from index.build_index import build_chunks  # noqa: E402


def main() -> int:
    chunks = build_chunks()
    all_citations = {c for ch in chunks for c in ch.citations}
    all_sources = {s for ch in chunks for s in ch.source_ids}

    problems: list[str] = []
    stats = {"citation": 0, "citation_contains": 0, "source_id": 0, "none": 0}

    for item in load_golden():
        expected = item.get("expect", [])
        if not expected:
            stats["none"] += 1
            if item["type"] not in {"refusal", "out_of_scope"}:
                problems.append(
                    f"  [{item['id']}] has no expected evidence but type is "
                    f"'{item['type']}' - only refusal/out_of_scope may be empty"
                )
            continue

        for m in expected:
            if "citation" in m:
                stats["citation"] += 1
                if m["citation"] not in all_citations:
                    problems.append(
                        f"  [{item['id']}] citation not in corpus: {m['citation']!r}"
                    )
            elif "citation_contains" in m:
                stats["citation_contains"] += 1
                if not any(m["citation_contains"] in c for c in all_citations):
                    problems.append(
                        f"  [{item['id']}] no citation contains "
                        f"{m['citation_contains']!r}"
                    )
            elif "source_id" in m:
                stats["source_id"] += 1
                if m["source_id"] not in all_sources:
                    problems.append(
                        f"  [{item['id']}] source not in corpus: {m['source_id']!r}"
                    )
            else:
                problems.append(f"  [{item['id']}] unrecognised matcher: {m}")

    print(f"corpus: {len(chunks)} chunks, {len(all_citations)} distinct citations, "
          f"{len(all_sources)} sources")
    print(f"matchers checked: {stats}")
    if problems:
        print(f"\n{len(problems)} PROBLEM(S):")
        print("\n".join(problems))
        return 1
    print("\ngolden set validates against the corpus")
    return 0


if __name__ == "__main__":
    sys.exit(main())
