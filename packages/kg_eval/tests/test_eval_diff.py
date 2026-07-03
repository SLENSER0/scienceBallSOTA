"""Eval run-to-run diff: improved / regressed / unchanged (§18.13)."""

from __future__ import annotations

from kg_eval.eval_diff import EvalDiff, MetricDelta, eval_diff


def test_improvement_above_tol() -> None:
    # +0.05 > tol=0.02 → improved; nothing regressed → verdict "pass".
    d = eval_diff({"mrr": 0.50}, {"mrr": 0.55})
    assert len(d.improved) == 1
    item = d.improved[0]
    assert item.metric == "mrr"
    assert item.baseline == 0.50
    assert item.current == 0.55
    assert item.delta == 0.05
    assert d.regressed == ()
    assert d.unchanged == ()
    assert d.verdict == "pass"


def test_regression_beyond_tol() -> None:
    # -0.10 < -tol → regressed → verdict "fail".
    d = eval_diff({"recall_at_5": 0.70}, {"recall_at_5": 0.60})
    assert d.improved == ()
    assert len(d.regressed) == 1
    item = d.regressed[0]
    assert item.metric == "recall_at_5"
    assert item.delta == -0.10
    assert d.verdict == "fail"


def test_within_tol_is_unchanged() -> None:
    # +0.01 (< tol) and exactly +0.02 / -0.02 (boundary) all count as unchanged.
    d = eval_diff(
        {"a": 0.50, "b": 0.50, "c": 0.50},
        {"a": 0.51, "b": 0.52, "c": 0.48},
    )
    assert d.improved == ()
    assert d.regressed == ()
    assert [u.metric for u in d.unchanged] == ["a", "b", "c"]
    assert d.verdict == "pass"


def test_verdict_pass_and_fail_mixed() -> None:
    d = eval_diff(
        {"up": 0.50, "down": 0.90, "flat": 0.50},
        {"up": 0.60, "down": 0.70, "flat": 0.50},
    )
    assert [i.metric for i in d.improved] == ["up"]
    assert [r.metric for r in d.regressed] == ["down"]
    assert [u.metric for u in d.unchanged] == ["flat"]
    # any regression → fail, even with an improvement present.
    assert d.verdict == "fail"


def test_missing_metric_is_skipped() -> None:
    # "only_base" absent from current, "only_cur" absent from baseline → both skipped.
    d = eval_diff(
        {"shared": 0.50, "only_base": 0.90},
        {"shared": 0.60, "only_cur": 0.10},
    )
    assert [i.metric for i in d.improved] == ["shared"]
    assert d.regressed == ()
    assert d.unchanged == ()
    assert d.verdict == "pass"


def test_empty_inputs() -> None:
    d = eval_diff({}, {})
    assert d.improved == ()
    assert d.regressed == ()
    assert d.unchanged == ()
    assert d.verdict == "pass"


def test_custom_tol() -> None:
    # +0.05 with tol=0.10 stays unchanged; -0.05 with default tol regresses.
    lenient = eval_diff({"m": 0.50}, {"m": 0.55}, tol=0.10)
    assert lenient.unchanged[0].metric == "m"
    assert lenient.verdict == "pass"
    strict = eval_diff({"m": 0.50}, {"m": 0.45})
    assert strict.regressed[0].metric == "m"
    assert strict.verdict == "fail"


def test_as_dict_roundtrip() -> None:
    d = eval_diff(
        {"up": 0.50, "down": 0.80, "flat": 0.50},
        {"up": 0.60, "down": 0.60, "flat": 0.505},
    )
    assert d.as_dict() == {
        "improved": [
            {"metric": "up", "baseline": 0.50, "current": 0.60, "delta": 0.10},
        ],
        "regressed": [
            {"metric": "down", "baseline": 0.80, "current": 0.60, "delta": -0.20},
        ],
        "unchanged": [
            {"metric": "flat", "baseline": 0.50, "current": 0.505, "delta": 0.005},
        ],
        "verdict": "fail",
    }


def test_metricdelta_as_dict() -> None:
    md = MetricDelta("mrr", 0.5, 0.6, 0.1)
    assert md.as_dict() == {
        "metric": "mrr",
        "baseline": 0.5,
        "current": 0.6,
        "delta": 0.1,
    }


def test_evaldiff_frozen() -> None:
    d = eval_diff({"m": 0.5}, {"m": 0.5})
    assert isinstance(d, EvalDiff)
    try:
        d.verdict = "pass"  # type: ignore[misc]
    except AttributeError:
        pass
    else:  # pragma: no cover - frozen dataclass must reject assignment
        raise AssertionError("EvalDiff must be frozen")
