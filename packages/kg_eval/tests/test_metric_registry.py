"""Eval-metric registry — canonical defs + direction helpers (§18.10)."""

from __future__ import annotations

import pytest

from kg_eval.metric_registry import METRICS, MetricDef, is_better, metric_for

EXPECTED = {"recall_at_k", "mrr", "ndcg", "extraction_f1", "answer_grounding"}


def test_registry_has_all_metrics() -> None:
    assert set(METRICS) == EXPECTED
    assert len(METRICS) == 5
    # Registry is keyed by the metric's own name.
    for name, mdef in METRICS.items():
        assert mdef.name == name
        assert isinstance(mdef, MetricDef)


def test_higher_is_better_flags() -> None:
    # All current metrics improve as the score rises (§15.2).
    for name in EXPECTED:
        assert metric_for(name).higher_is_better is True


def test_is_better_respects_direction() -> None:
    # higher_is_better -> larger wins.
    assert is_better("mrr", 0.9, 0.4) is True
    assert is_better("mrr", 0.4, 0.9) is False
    assert is_better("recall_at_k", 1.0, 0.0) is True


def test_is_better_equal_is_not_better() -> None:
    assert is_better("ndcg", 0.5, 0.5) is False


def test_metric_for_lookup() -> None:
    mdef = metric_for("extraction_f1")
    assert mdef is not None
    assert mdef.name == "extraction_f1"
    assert mdef is METRICS["extraction_f1"]


def test_metric_for_unknown_returns_none() -> None:
    assert metric_for("does_not_exist") is None
    assert metric_for("") is None


def test_is_better_unknown_raises() -> None:
    with pytest.raises(KeyError):
        is_better("does_not_exist", 0.9, 0.1)


def test_range_present() -> None:
    for name in EXPECTED:
        mdef = metric_for(name)
        assert mdef.range == (0.0, 1.0)
        low, high = mdef.range
        assert low == 0.0 and high == 1.0


def test_as_dict() -> None:
    d = metric_for("recall_at_k").as_dict()
    assert d == {
        "name": "recall_at_k",
        "higher_is_better": True,
        "range": [0.0, 1.0],
        "description": d["description"],
    }
    assert set(d) == {"name", "higher_is_better", "range", "description"}
    assert d["range"] == [0.0, 1.0]
    assert isinstance(d["description"], str) and d["description"]
