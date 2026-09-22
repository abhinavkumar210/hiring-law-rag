"""Evaluation harness.

This is the centrepiece of the project. It answers the question most retrieval
demos cannot: how do you know it works, and how would you notice if a change
made it worse?

What it measures
----------------
hit@k      did any chunk satisfying an expected matcher appear in the top k
recall@k   what fraction of a question's expected matchers were satisfied
MRR        1/rank of the first satisfying chunk, averaged
abstention for refusal and out-of-scope questions, whether the system correctly
           declined instead of returning its nearest paragraph

Scores are reported per question type, not just in aggregate. An overall number
hides the only interesting failures: a system can score well on single-hop
lookups while failing every cross-document question, which is precisely the case
this corpus was chosen to expose.

Regression detection
--------------------
Results are written to eval/results/latest.json. If a baseline exists, the run
compares against it and exits non-zero when any metric drops by more than
REGRESSION_TOLERANCE, so CI fails on a retrieval regression the same way it
fails on a broken test.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from retrieve.search import Index, Result  # noqa: E402

GOLDEN = ROOT / "eval" / "golden" / "questions.jsonl"
RESULTS = ROOT / "eval" / "results"
REGRESSION_TOLERANCE = 0.02

ABSTAIN_TYPES = {"refusal", "out_of_scope"}


def load_golden(path: pathlib.Path = GOLDEN) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf8").splitlines()
        if line.strip()
    ]


def matches(matcher: dict, result: Result) -> bool:
    """Does one retrieved chunk satisfy one expected-evidence matcher?"""
    if "citation" in matcher:
        return matcher["citation"] in result.citations
    if "citation_contains" in matcher:
        needle = matcher["citation_contains"]
        return any(needle in c for c in result.citations)
    if "source_id" in matcher:
        return matcher["source_id"] in result.source_ids
    raise ValueError(f"unrecognised matcher: {matcher}")


@dataclasses.dataclass
class QuestionScore:
    id: str
    type: str
    question: str
    hit: bool
    recall: float
    reciprocal_rank: float
    abstained: bool
    correct: bool
    top_score: float
    top_citations: list[str]
    withdrawn_in_top: bool


def score_question(item: dict, index: Index, k: int) -> QuestionScore:
    results = index.search(item["question"], k=k)
    abstained = index.should_abstain(results)
    expected = item.get("expect", [])

    if item["type"] in ABSTAIN_TYPES:
        # Correct behaviour is to decline. No evidence is expected.
        return QuestionScore(
            id=item["id"],
            type=item["type"],
            question=item["question"],
            hit=False,
            recall=0.0,
            reciprocal_rank=0.0,
            abstained=abstained,
            correct=abstained,
            top_score=results[0].score if results else 0.0,
            top_citations=results[0].citations if results else [],
            withdrawn_in_top=any(r.status != "in_force" for r in results),
        )

    satisfied = 0
    first_rank = 0
    for matcher in expected:
        for r in results:
            if matches(matcher, r):
                satisfied += 1
                if first_rank == 0 or r.rank < first_rank:
                    first_rank = r.rank
                break

    recall = satisfied / len(expected) if expected else 0.0
    return QuestionScore(
        id=item["id"],
        type=item["type"],
        question=item["question"],
        hit=satisfied > 0,
        recall=recall,
        reciprocal_rank=1.0 / first_rank if first_rank else 0.0,
        abstained=abstained,
        # An answerable question answered by abstaining is not correct.
        correct=(recall == 1.0) and not abstained,
        top_score=results[0].score if results else 0.0,
        top_citations=results[0].citations if results else [],
        withdrawn_in_top=any(r.status != "in_force" for r in results),
    )


def aggregate(scores: list[QuestionScore]) -> dict:
    def agg(rows: list[QuestionScore]) -> dict:
        n = len(rows)
        if n == 0:
            return {}
        answerable = [r for r in rows if r.type not in ABSTAIN_TYPES]
        out = {
            "n": n,
            "correct": round(sum(r.correct for r in rows) / n, 4),
        }
        if answerable:
            out |= {
                "hit@k": round(sum(r.hit for r in answerable) / len(answerable), 4),
                "recall@k": round(
                    sum(r.recall for r in answerable) / len(answerable), 4
                ),
                "mrr": round(
                    sum(r.reciprocal_rank for r in answerable) / len(answerable), 4
                ),
            }
        abstainers = [r for r in rows if r.type in ABSTAIN_TYPES]
        if abstainers:
            out["abstain_rate"] = round(
                sum(r.abstained for r in abstainers) / len(abstainers), 4
            )
        return out

    by_type: dict[str, dict] = {}
    for t in sorted({s.type for s in scores}):
        by_type[t] = agg([s for s in scores if s.type == t])
    return {"overall": agg(scores), "by_type": by_type}


def compare(current: dict, baseline: dict) -> list[str]:
    """Return human-readable regression lines, empty if none."""
    problems = []
    for scope, cur in [("overall", current["overall"])] + [
        (f"by_type.{t}", v) for t, v in current["by_type"].items()
    ]:
        base = (
            baseline["overall"]
            if scope == "overall"
            else baseline.get("by_type", {}).get(scope.split(".", 1)[1], {})
        )
        for metric, value in cur.items():
            if metric == "n" or metric not in base:
                continue
            delta = value - base[metric]
            if delta < -REGRESSION_TOLERANCE:
                problems.append(
                    f"  REGRESSION {scope}.{metric}: "
                    f"{base[metric]:.4f} -> {value:.4f} ({delta:+.4f})"
                )
    return problems


def render(scores: list[QuestionScore], summary: dict, k: int) -> str:
    lines = [f"Evaluation over {len(scores)} golden questions (k={k})", ""]
    o = summary["overall"]
    lines.append(
        f"OVERALL  correct {o['correct']:.3f}   hit@k {o.get('hit@k', 0):.3f}   "
        f"recall@k {o.get('recall@k', 0):.3f}   MRR {o.get('mrr', 0):.3f}"
    )
    lines.append("")
    lines.append(f"{'type':<18}{'n':>4}{'correct':>9}{'hit@k':>8}{'recall':>8}{'MRR':>8}{'abstain':>9}")
    lines.append("-" * 64)
    for t, m in summary["by_type"].items():
        lines.append(
            f"{t:<18}{m['n']:>4}{m['correct']:>9.3f}"
            f"{m.get('hit@k', float('nan')):>8.3f}{m.get('recall@k', float('nan')):>8.3f}"
            f"{m.get('mrr', float('nan')):>8.3f}{m.get('abstain_rate', float('nan')):>9.3f}"
        )
    failures = [s for s in scores if not s.correct]
    if failures:
        lines += ["", f"FAILURES ({len(failures)})", "-" * 64]
        for s in failures:
            detail = (
                "abstained when an answer exists"
                if s.abstained and s.type not in ABSTAIN_TYPES
                else (
                    "answered instead of declining"
                    if s.type in ABSTAIN_TYPES
                    else f"recall {s.recall:.2f}"
                )
            )
            lines.append(f"  [{s.id}] {s.type}: {detail}")
            lines.append(f"      q: {s.question[:78]}")
            lines.append(
                f"      top: {s.top_citations[:2]} score {s.top_score:.3f}"
            )
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("-k", type=int, default=5, help="retrieval depth")
    ap.add_argument("--set-baseline", action="store_true",
                    help="write this run as the regression baseline")
    args = ap.parse_args()

    index = Index.load()
    golden = load_golden()
    scores = [score_question(item, index, args.k) for item in golden]
    summary = aggregate(scores)

    RESULTS.mkdir(parents=True, exist_ok=True)
    payload = {
        "k": args.k,
        "model": index.meta.get("model"),
        "n_chunks": index.meta.get("n_chunks"),
        "summary": summary,
        "questions": [dataclasses.asdict(s) for s in scores],
    }
    (RESULTS / "latest.json").write_text(
        json.dumps(payload, indent=2), encoding="utf8"
    )

    print(render(scores, summary, args.k))

    baseline_path = RESULTS / "baseline.json"
    if args.set_baseline:
        baseline_path.write_text(json.dumps(payload, indent=2), encoding="utf8")
        print("\nbaseline written")
        return 0

    if baseline_path.exists():
        baseline = json.loads(baseline_path.read_text(encoding="utf8"))
        problems = compare(summary, baseline["summary"])
        if problems:
            print("\nREGRESSIONS vs baseline:")
            print("\n".join(problems))
            return 1
        print("\nno regression vs baseline")
    else:
        print("\nno baseline yet - run with --set-baseline to create one")
    return 0


if __name__ == "__main__":
    sys.exit(main())
