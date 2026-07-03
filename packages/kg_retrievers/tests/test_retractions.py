"""Soft-retraction of observations over a hand-built graph (§25.12).

Builds the minimal fixture the spec describes — one Material with two
Measurements attached via ``ABOUT_MATERIAL`` — then retracts one:

    Measurement(m_hi) -ABOUT_MATERIAL-> Material(nickel)   (retracted)
    Measurement(m_lo) -ABOUT_MATERIAL-> Material(nickel)   (active)

Hand-checked expectations:
- retract() flags the node retracted=True + valid_to/reason/actor in props;
- is_retracted() is True for the withdrawn node, False for the active one;
- active_measurements() hides the retracted one by default, shows both when
  include_retracted=True;
- unretract() restores the node to active;
- unknown ids are graceful no-ops, not errors.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from kg_common import make_id
from kg_retrievers.graph_store import KuzuGraphStore
from kg_retrievers.retractions import (
    Retraction,
    active_measurements,
    is_retracted,
    retract,
    unretract,
)

NICKEL = make_id("Material", "nickel")
M_HI = make_id("Measurement", "nickel recovery high")
M_LO = make_id("Measurement", "nickel recovery low")


@pytest.fixture
def store():  # type: ignore[no-untyped-def]
    d = tempfile.mkdtemp()
    s = KuzuGraphStore(str(Path(d) / "g"))
    _build(s)
    yield s
    s.close()


def _build(s: KuzuGraphStore) -> None:
    """One material + two 'recovery' measurements attached via ABOUT_MATERIAL."""
    s.upsert_node(NICKEL, "Material", name="nickel", domain="hydrometallurgy")
    s.upsert_node(M_HI, "Measurement", property_name="recovery", value_normalized=92.0)
    s.upsert_node(M_LO, "Measurement", property_name="recovery", value_normalized=88.0)
    s.upsert_edge(M_HI, NICKEL, "ABOUT_MATERIAL", confidence=0.9)
    s.upsert_edge(M_LO, NICKEL, "ABOUT_MATERIAL", confidence=0.8)


# -- retract writes flags via props (read back through get_node) -----------
def test_retract_sets_flags(store: KuzuGraphStore) -> None:
    rec = retract(store, M_HI, reason="superseded by re-analysis", actor="alice", at="2026-07-03")
    assert isinstance(rec, Retraction)
    assert rec.as_dict() == {
        "node_id": M_HI,
        "reason": "superseded by re-analysis",
        "actor": "alice",
        "at": "2026-07-03",
    }
    nd = store.get_node(M_HI)
    assert nd is not None
    assert nd["retracted"] is True
    assert nd["valid_to"] == "2026-07-03"
    assert nd["retraction_reason"] == "superseded by re-analysis"
    assert nd["retracted_by"] == "alice"
    # untouched fields survive the re-upsert (no data loss).
    assert nd["property_name"] == "recovery"
    assert nd["value_normalized"] == 92.0


# -- is_retracted True/False ------------------------------------------------
def test_is_retracted_true_and_false(store: KuzuGraphStore) -> None:
    assert is_retracted(store, M_HI) is False  # nothing retracted yet
    retract(store, M_HI, reason="bad calibration", actor="bob", at="2026-07-01")
    assert is_retracted(store, M_HI) is True
    assert is_retracted(store, M_LO) is False  # the other observation is untouched


# -- active_measurements hides retracted by default ------------------------
def test_active_excludes_retracted_by_default(store: KuzuGraphStore) -> None:
    before = {m["id"] for m in active_measurements(store, NICKEL)}
    assert before == {M_HI, M_LO}  # both active to start

    retract(store, M_HI, reason="withdrawn", actor="carol", at="2026-06-30")
    after = active_measurements(store, NICKEL)
    assert [m["id"] for m in after] == [M_LO]  # retracted one excluded, sorted


# -- include_retracted=True returns both -----------------------------------
def test_include_retracted_returns_both(store: KuzuGraphStore) -> None:
    retract(store, M_HI, reason="withdrawn", actor="carol", at="2026-06-30")
    both = active_measurements(store, NICKEL, include_retracted=True)
    assert sorted(m["id"] for m in both) == sorted([M_HI, M_LO])
    # the retracted one still carries its tombstone when surfaced to absence-layer.
    hi = next(m for m in both if m["id"] == M_HI)
    assert hi["retracted"] is True


# -- unretract restores -----------------------------------------------------
def test_unretract_restores(store: KuzuGraphStore) -> None:
    retract(store, M_HI, reason="withdrawn", actor="carol", at="2026-06-30")
    assert is_retracted(store, M_HI) is True

    assert unretract(store, M_HI) is True
    assert is_retracted(store, M_HI) is False
    # restored observation is active again and the reason tombstone is cleared.
    nd = store.get_node(M_HI)
    assert nd is not None
    assert "retraction_reason" not in nd
    assert "valid_to" not in nd
    assert {m["id"] for m in active_measurements(store, NICKEL)} == {M_HI, M_LO}


# -- graceful on unknown ids ------------------------------------------------
def test_unknown_ids_graceful(store: KuzuGraphStore) -> None:
    assert is_retracted(store, "measurement:ghost") is False
    assert retract(store, "measurement:ghost", reason="x", actor="y", at="z") is None
    assert unretract(store, "measurement:ghost") is False
    assert active_measurements(store, "material:ghost") == []
