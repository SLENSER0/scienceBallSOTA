"""Hand-checked tests for coverage-delta between two snapshots (§15.16)."""

from __future__ import annotations

from kg_retrievers.coverage_delta import CoverageDelta, coverage_delta


def test_newly_covered_materials() -> None:
    # b flips False->True, c is new-and-covered; a stays covered.
    before = {"a": True, "b": False}
    after = {"a": True, "b": True, "c": True}
    delta = coverage_delta(before, after)
    assert delta.added_covered == ("b", "c")
    assert delta.lost_covered == ()
    assert delta.net == 2
    # before covered count = 1 → +2 covered = +200%
    assert delta.pct_change == 200.0


def test_lost_coverage() -> None:
    # b flips True->False, c dropped from the snapshot entirely.
    before = {"a": True, "b": True, "c": True}
    after = {"a": True, "b": False}
    delta = coverage_delta(before, after)
    assert delta.added_covered == ()
    assert delta.lost_covered == ("b", "c")
    assert delta.net == -2
    # before covered = 3 → -2/3*100 = -66.67
    assert delta.pct_change == -66.67


def test_net_balances_gains_and_losses() -> None:
    # a lost, b gained → equal count → net zero, pct zero.
    before = {"a": True, "b": False, "c": True}
    after = {"a": False, "b": True, "c": True}
    delta = coverage_delta(before, after)
    assert delta.added_covered == ("b",)
    assert delta.lost_covered == ("a",)
    assert delta.net == 0
    assert delta.pct_change == 0.0


def test_pct_change_from_zero_before() -> None:
    # before has no covered material → first coverage reads as +100%.
    before = {"a": False, "b": False}
    after = {"a": True, "b": False}
    delta = coverage_delta(before, after)
    assert delta.added_covered == ("a",)
    assert delta.lost_covered == ()
    assert delta.net == 1
    assert delta.pct_change == 100.0


def test_no_change() -> None:
    snap = {"a": True, "b": False, "c": True}
    delta = coverage_delta(snap, dict(snap))
    assert delta.added_covered == ()
    assert delta.lost_covered == ()
    assert delta.net == 0
    assert delta.pct_change == 0.0


def test_empty_snapshots() -> None:
    delta = coverage_delta({}, {})
    assert delta.added_covered == ()
    assert delta.lost_covered == ()
    assert delta.net == 0
    assert delta.pct_change == 0.0


def test_as_dict_shape_and_values() -> None:
    before = {"m1": True, "m2": False}
    after = {"m1": False, "m2": True}
    delta = coverage_delta(before, after)
    d = delta.as_dict()
    assert set(d) == {"added_covered", "lost_covered", "net", "pct_change"}
    assert d["added_covered"] == ["m2"]
    assert d["lost_covered"] == ["m1"]
    assert d["net"] == 0
    assert d["pct_change"] == 0.0
    # net == |added| - |lost| invariant holds
    assert d["net"] == len(d["added_covered"]) - len(d["lost_covered"])


def test_is_frozen_dataclass() -> None:
    delta = coverage_delta({"a": True}, {"a": True})
    assert isinstance(delta, CoverageDelta)
    try:
        delta.net = 5  # type: ignore[misc]
    except Exception as exc:  # frozen → FrozenInstanceError
        assert exc.__class__.__name__ == "FrozenInstanceError"
    else:  # pragma: no cover
        raise AssertionError("CoverageDelta must be frozen")
