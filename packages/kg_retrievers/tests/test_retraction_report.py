"""Hand-checked retraction summary over flattened observation dicts (§25.16).

The report is pure Python over ``Measurement`` node dicts shaped like
:meth:`KuzuGraphStore.get_node` output — the ``retracted`` tombstone and its
``retraction_reason`` live flattened at the top level (§25.12). Fixtures are built
by hand so every expected count / ratio is directly checkable:

- active observations may carry ``retracted=False`` OR no ``retracted`` key at all;
  both must count as active (they mirror a never-retracted and an unretracted node).
- retracted observations carry ``retracted=True`` plus, usually, a reason.
"""

from __future__ import annotations

from typing import Any

from kg_retrievers.retraction_report import (
    UNSPECIFIED_REASON,
    RetractionReport,
    retraction_report,
)


def _meas(mid: str, *, retracted: bool = False, reason: str | None = None) -> dict[str, Any]:
    """A flattened Measurement dict; retracted ones carry the §25.12 tombstone."""
    node: dict[str, Any] = {
        "id": mid,
        "label": "Measurement",
        "property_name": "recovery",
        "value_normalized": 90.0,
    }
    if retracted:
        node["retracted"] = True
        node["valid_to"] = "2026-07-03"
        node["retracted_by"] = "alice"
        if reason is not None:
            node["retraction_reason"] = reason
    return node


def _active(mid: str) -> dict[str, Any]:
    """An active observation that carries an explicit ``retracted=False`` (post-unretract)."""
    node = _meas(mid)
    node["retracted"] = False
    return node


# -- retracted / active counts (missing-key and explicit-False both active) --
def test_counts_retracted_and_active() -> None:
    ms = [
        _meas("m:1"),  # active, no retracted key
        _meas("m:2", retracted=True, reason="superseded"),
        _meas("m:3", retracted=True, reason="bad calibration"),
        _active("m:4"),  # active, explicit retracted=False
    ]
    rep = retraction_report(ms)
    assert rep.total == 4
    assert rep.retracted == 2
    assert rep.active == 2
    assert rep.retracted + rep.active == rep.total


# -- by_reason histogram (key-sorted, sums to retracted) --------------------
def test_by_reason_histogram() -> None:
    ms = [
        _meas("m:1", retracted=True, reason="superseded"),
        _meas("m:2", retracted=True, reason="superseded"),
        _meas("m:3", retracted=True, reason="bad calibration"),
        _meas("m:4"),  # active -> not in the histogram
    ]
    rep = retraction_report(ms)
    assert rep.by_reason == {"bad calibration": 1, "superseded": 2}
    # histogram counts sum back to the retracted total.
    assert sum(rep.by_reason.values()) == rep.retracted == 3
    # key-sorted output: 'bad calibration' before 'superseded'.
    assert list(rep.by_reason.keys()) == ["bad calibration", "superseded"]


# -- retracted_ratio is a plain fraction ------------------------------------
def test_retracted_ratio_fraction() -> None:
    ms = [
        _meas("m:1", retracted=True, reason="x"),
        _meas("m:2"),
        _meas("m:3"),
        _meas("m:4"),
    ]
    rep = retraction_report(ms)
    assert rep.total == 4
    assert rep.retracted == 1
    assert rep.retracted_ratio == 0.25


# -- none retracted -> ratio 0.0, empty histogram ---------------------------
def test_none_retracted_ratio_zero() -> None:
    ms = [_meas("m:1"), _active("m:2"), _meas("m:3")]
    rep = retraction_report(ms)
    assert rep.total == 3
    assert rep.retracted == 0
    assert rep.active == 3
    assert rep.retracted_ratio == 0.0
    assert rep.by_reason == {}


# -- all retracted -> ratio 1.0 ---------------------------------------------
def test_all_retracted_ratio_one() -> None:
    ms = [
        _meas("m:1", retracted=True, reason="a"),
        _meas("m:2", retracted=True, reason="b"),
    ]
    rep = retraction_report(ms)
    assert rep.total == 2
    assert rep.retracted == 2
    assert rep.active == 0
    assert rep.retracted_ratio == 1.0
    assert rep.by_reason == {"a": 1, "b": 1}


# -- empty input -> all zeros -----------------------------------------------
def test_empty_zeros() -> None:
    rep = retraction_report([])
    assert isinstance(rep, RetractionReport)
    assert rep.total == 0
    assert rep.retracted == 0
    assert rep.active == 0
    assert rep.by_reason == {}
    assert rep.retracted_ratio == 0.0


# -- retracted with no reason falls under the sentinel bucket ---------------
def test_retracted_without_reason_bucketed() -> None:
    ms = [
        _meas("m:1", retracted=True, reason=None),
        _meas("m:2", retracted=True, reason="superseded"),
    ]
    rep = retraction_report(ms)
    assert rep.retracted == 2
    assert rep.by_reason == {UNSPECIFIED_REASON: 1, "superseded": 1}
    assert sum(rep.by_reason.values()) == rep.retracted


# -- as_dict mirrors the fields and defensively copies by_reason ------------
def test_as_dict_roundtrip() -> None:
    ms = [
        _meas("m:1", retracted=True, reason="superseded"),
        _meas("m:2"),
    ]
    rep = retraction_report(ms)
    assert rep.as_dict() == {
        "total": 2,
        "retracted": 1,
        "active": 1,
        "by_reason": {"superseded": 1},
        "retracted_ratio": 0.5,
    }
    # as_dict hands back a copy — mutating it must not corrupt the frozen report.
    dumped = rep.as_dict()
    dumped["by_reason"]["injected"] = 99
    assert rep.by_reason == {"superseded": 1}
