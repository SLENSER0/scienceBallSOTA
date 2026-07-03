"""Eval quality gates + regression thresholds (§18.8)."""

from __future__ import annotations

from kg_eval.quality_gates import (
    DEFAULT_GATES,
    GateFailure,
    check_gates,
    is_regression,
)

# A metrics dict that clears every default gate with room to spare.
_ALL_PASS = {
    "recall_at_5": 0.7,
    "mrr": 0.6,
    "extraction_f1": 0.8,
    "answer_grounding": 0.95,
}


def test_default_gates_values() -> None:
    assert DEFAULT_GATES == {
        "recall_at_5": 0.6,
        "mrr": 0.5,
        "extraction_f1": 0.7,
        "answer_grounding": 0.9,
    }


def test_all_pass() -> None:
    r = check_gates(_ALL_PASS)
    assert r.passed is True
    assert r.failures == ()
    assert r.checked == {
        "recall_at_5": True,
        "mrr": True,
        "extraction_f1": True,
        "answer_grounding": True,
    }


def test_one_below_threshold() -> None:
    metrics = {**_ALL_PASS, "extraction_f1": 0.5}  # 0.5 < 0.7 → fails
    r = check_gates(metrics)
    assert r.passed is False
    assert len(r.failures) == 1
    f = r.failures[0]
    assert f.metric == "extraction_f1"
    assert f.actual == 0.5
    assert f.threshold == 0.7
    assert f.reason == "below_threshold"
    assert r.checked["extraction_f1"] is False
    assert r.checked["mrr"] is True


def test_boundary_exact_threshold_passes() -> None:
    # actual == threshold clears the gate (comparison is ``>=``).
    metrics = {"recall_at_5": 0.6, "mrr": 0.5, "extraction_f1": 0.7, "answer_grounding": 0.9}
    r = check_gates(metrics)
    assert r.passed is True
    assert r.failures == ()


def test_missing_metric_handled() -> None:
    metrics = {"recall_at_5": 0.7, "mrr": 0.6, "extraction_f1": 0.8}  # no answer_grounding
    r = check_gates(metrics)
    assert r.passed is False
    assert len(r.failures) == 1
    f = r.failures[0]
    assert f.metric == "answer_grounding"
    assert f.actual is None
    assert f.threshold == 0.9
    assert f.reason == "missing"
    assert r.checked["answer_grounding"] is False


def test_custom_gates_fail() -> None:
    gates = {"recall_at_5": 0.9}
    metrics = {"recall_at_5": 0.8, "mrr": 0.1}  # mrr not a gate → ignored
    r = check_gates(metrics, gates=gates)
    assert r.passed is False
    assert r.checked == {"recall_at_5": False}
    assert [f.metric for f in r.failures] == ["recall_at_5"]


def test_custom_gates_pass() -> None:
    gates = {"recall_at_5": 0.5}
    r = check_gates({"recall_at_5": 0.8}, gates=gates)
    assert r.passed is True
    assert r.checked == {"recall_at_5": True}
    assert r.failures == ()


def test_as_dict() -> None:
    metrics = {**_ALL_PASS, "recall_at_5": 0.5}  # only recall_at_5 fails
    d = check_gates(metrics).as_dict()
    assert d["passed"] is False
    assert d["checked"]["recall_at_5"] is False
    assert isinstance(d["failures"], list)
    assert d["failures"] == [
        {"metric": "recall_at_5", "actual": 0.5, "threshold": 0.6, "reason": "below_threshold"}
    ]
    # GateFailure renders the same shape on its own.
    assert GateFailure("mrr", None, 0.5, "missing").as_dict() == {
        "metric": "mrr",
        "actual": None,
        "threshold": 0.5,
        "reason": "missing",
    }


def test_is_regression_flags_drop() -> None:
    baseline = {"recall_at_5": 0.8, "mrr": 0.6}
    current = {"recall_at_5": 0.8, "mrr": 0.5}  # mrr drops 0.1 > 0.02
    assert is_regression(current, baseline) == ["mrr"]


def test_is_regression_within_tol() -> None:
    baseline = {"mrr": 0.60}
    current = {"mrr": 0.59}  # drop 0.01 <= 0.02
    assert is_regression(current, baseline) == []


def test_is_regression_improvement() -> None:
    baseline = {"mrr": 0.5}
    current = {"mrr": 0.7}  # went up → not a regression
    assert is_regression(current, baseline) == []


def test_is_regression_multiple_sorted() -> None:
    baseline = {"a": 0.9, "b": 0.9, "c": 0.9}
    current = {"a": 0.5, "b": 0.89, "c": 0.5}  # a,c drop 0.4; b drops 0.01 (in tol)
    assert is_regression(current, baseline) == ["a", "c"]


def test_is_regression_custom_tol() -> None:
    baseline = {"mrr": 0.6}
    current = {"mrr": 0.55}  # drop 0.05
    assert is_regression(current, baseline, tol=0.1) == []  # within a looser tol
    assert is_regression(current, baseline) == ["mrr"]  # but > default 0.02


def test_is_regression_missing_current_skipped() -> None:
    baseline = {"mrr": 0.6, "recall_at_5": 0.9}
    current = {"mrr": 0.6}  # recall_at_5 absent → skipped, not flagged
    assert is_regression(current, baseline) == []
