"""Tests for the regression gate.

The gate is the part of the harness that fails CI, so its logic needs a test
that runs in seconds rather than requiring a full ~8 minute evaluation.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from eval.harness import REGRESSION_TOLERANCE, compare


def _summary(correct: float, cross: float = 1.0) -> dict:
    return {
        "overall": {"n": 32, "correct": correct, "hit@k": 0.93, "recall@k": 0.93},
        "by_type": {"cross_document": {"n": 2, "correct": cross, "recall@k": cross}},
    }


def test_identical_runs_report_no_regression():
    assert compare(_summary(0.9375), _summary(0.9375)) == []


def test_improvement_is_not_a_regression():
    assert compare(_summary(0.96), _summary(0.9375)) == []


def test_drop_beyond_tolerance_is_reported():
    problems = compare(_summary(0.80), _summary(0.9375))
    assert problems
    assert any("overall.correct" in p for p in problems)


def test_drop_within_tolerance_is_allowed():
    """Float noise across hardware must not fail CI."""
    small = 0.9375 - (REGRESSION_TOLERANCE / 2)
    assert compare(_summary(small), _summary(0.9375)) == []


def test_per_type_regression_is_caught_even_when_overall_holds():
    """The failure mode this project exists to prevent.

    A change can leave the aggregate untouched while destroying one capability.
    cross_document going 1.0 -> 0.0 must fail even with overall unchanged.
    """
    current = _summary(0.9375, cross=0.0)
    baseline = _summary(0.9375, cross=1.0)
    problems = compare(current, baseline)
    assert problems
    assert any("cross_document" in p for p in problems)


def test_missing_metric_in_baseline_is_skipped_not_crashed():
    baseline = {"overall": {"n": 32, "correct": 0.9}, "by_type": {}}
    assert compare(_summary(0.9375), baseline) == []
