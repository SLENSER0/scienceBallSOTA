"""Tests for the cross-snapshot recall regression tracker (§25.17)."""

from __future__ import annotations

from kg_retrievers.recall_regression_tracker import (
    RecallChange,
    RegressionReport,
    track_regression,
)


def test_spec_example_before_after() -> None:
    """Hand-checked example from the spec (§25.17)."""
    before = {"a": 0.9, "b": 0.5}
    after = {"a": 0.6, "b": 0.7}
    report = track_regression(before, after, epsilon=0.05)

    by_key = {c.context_key: c for c in report.changes}

    # a: 0.6 - 0.9 = -0.3, a real drop -> regressed.
    assert round(by_key["a"].delta, 6) == -0.3
    assert by_key["a"].regressed is True

    # b: 0.7 - 0.5 = +0.2, an improvement -> not regressed.
    assert round(by_key["b"].delta, 6) == 0.2
    assert by_key["b"].regressed is False

    assert report.n_regressed == 1
    assert report.worst_context == "a"  # most-negative delta
    assert report.mean_delta == round((-0.3 + 0.2) / 2, 6) == -0.05


def test_epsilon_threshold_small_drop_not_regressed() -> None:
    """A 0.04 drop is below epsilon=0.05 and must not be flagged (§25.17)."""
    before = {"a": 0.90}
    after = {"a": 0.86}  # delta = -0.04
    report = track_regression(before, after, epsilon=0.05)

    assert round(report.changes[0].delta, 6) == -0.04
    assert report.changes[0].regressed is False
    assert report.n_regressed == 0


def test_epsilon_exact_boundary_regressed() -> None:
    """delta == -epsilon counts as a regression (delta <= -epsilon) (§25.17)."""
    before = {"a": 0.90}
    after = {"a": 0.85}  # delta = -0.05 exactly
    report = track_regression(before, after, epsilon=0.05)

    assert report.changes[0].regressed is True
    assert report.n_regressed == 1


def test_keys_in_only_one_snapshot_are_skipped() -> None:
    """Unmatched context keys are ignored — join on shared keys (§25.17)."""
    before = {"a": 0.9, "only_before": 0.4}
    after = {"a": 0.6, "only_after": 0.8}
    report = track_regression(before, after)

    keys = {c.context_key for c in report.changes}
    assert keys == {"a"}


def test_empty_inputs() -> None:
    """Empty snapshots give n_regressed 0 and worst_context None (§25.17)."""
    report = track_regression({}, {})

    assert report.changes == []
    assert report.n_regressed == 0
    assert report.worst_context is None
    assert report.mean_delta == 0.0


def test_worst_context_is_most_negative() -> None:
    """worst_context is the key with the most-negative delta (§25.17)."""
    before = {"x": 0.9, "y": 0.8, "z": 0.7}
    after = {"x": 0.7, "y": 0.2, "z": 0.7}  # deltas: -0.2, -0.6, 0.0
    report = track_regression(before, after, epsilon=0.05)

    assert report.worst_context == "y"
    # changes sorted most-negative first.
    assert [c.context_key for c in report.changes] == ["y", "x", "z"]
    assert report.n_regressed == 2


def test_changes_are_frozen_dataclasses() -> None:
    """RecallChange / RegressionReport are frozen with as_dict() (§25.17)."""
    report = track_regression({"a": 0.9}, {"a": 0.6}, epsilon=0.05)
    assert isinstance(report, RegressionReport)

    change = report.changes[0]
    assert isinstance(change, RecallChange)

    for exc in (AttributeError, Exception):
        try:
            change.delta = 0.0  # type: ignore[misc]
        except exc:
            break
    else:  # pragma: no cover - defensive
        raise AssertionError("RecallChange should be frozen")


def test_as_dict_shapes() -> None:
    """as_dict() round-trips all fields for JSON transport (§25.17)."""
    report = track_regression({"a": 0.9, "b": 0.5}, {"a": 0.6, "b": 0.7}, epsilon=0.05)
    d = report.as_dict()

    assert set(d) == {"changes", "n_regressed", "worst_context", "mean_delta"}
    assert d["n_regressed"] == 1
    assert d["worst_context"] == "a"
    assert d["mean_delta"] == -0.05

    first = d["changes"][0]
    assert set(first) == {"context_key", "before", "after", "delta", "regressed"}
    # sorted most-negative first -> context "a".
    assert first["context_key"] == "a"
    assert first["regressed"] is True
