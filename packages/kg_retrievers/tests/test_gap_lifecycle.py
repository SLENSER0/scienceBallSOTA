"""Gap lifecycle over KuzuGraphStore — resolve / reopen / auto-resolve (§15.2).

Every assertion is hand-checkable: we seed a Gap ``ABOUT`` a Material in a temp
store, then drive the lifecycle and read the state back through
:meth:`KuzuGraphStore.get_node` (the lifecycle flags live in the JSON ``props``
catch-all, not queryable columns).
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from kg_retrievers.gap_lifecycle import (
    STATUS_OPEN,
    STATUS_RESOLVED,
    GapResolution,
    auto_resolve_if_covered,
    gap_status,
    reopen_gap,
    resolve_gap,
)
from kg_retrievers.graph_store import KuzuGraphStore


@pytest.fixture
def store():  # type: ignore[no-untyped-def]
    d = tempfile.mkdtemp()
    s = KuzuGraphStore(str(Path(d) / "g"))
    yield s
    s.close()


def _seed_gap(
    store: KuzuGraphStore,
    *,
    gap_id: str = "gap:1",
    subject_id: str = "mat:1",
    gap_type: str = "missing_property_value",
    property_name: str = "conductivity",
) -> None:
    """Seed a Material and a Gap ``ABOUT`` it (edge src=gap, per gap_analysis)."""
    store.upsert_node(subject_id, "Material", name="полимерная мембрана")
    store.upsert_node(
        gap_id,
        "Gap",
        name="нет значения свойства",
        gap_type=gap_type,
        property_name=property_name,
        review_status="pending",
        verified=False,
    )
    store.upsert_edge(gap_id, subject_id, "ABOUT")


def _add_measurement(
    store: KuzuGraphStore,
    *,
    meas_id: str = "meas:1",
    subject_id: str = "mat:1",
    property_name: str = "conductivity",
    rel_type: str = "ABOUT_MATERIAL",
) -> None:
    store.upsert_node(
        meas_id,
        "Measurement",
        property_name=property_name,
        value_normalized=12.5,
        normalized_unit="S/m",
    )
    store.upsert_edge(meas_id, subject_id, rel_type)


def test_fresh_gap_status_is_open(store: KuzuGraphStore) -> None:
    # A never-resolved Gap carries no `status` prop → defaults to "open" (§15.2).
    _seed_gap(store)
    assert gap_status(store, "gap:1") == STATUS_OPEN
    # unknown gap id → None (graceful), never a crash
    assert gap_status(store, "gap:missing") is None


def test_resolve_gap_stamps_status_and_metadata(store: KuzuGraphStore) -> None:
    _seed_gap(store)
    rec = resolve_gap(
        store, "gap:1", reason="curator confirmed", actor="alice", at="2026-07-03T00:00:00Z"
    )
    # return value is the frozen record
    assert isinstance(rec, GapResolution)
    assert rec.as_dict() == {
        "gap_id": "gap:1",
        "status": STATUS_RESOLVED,
        "reason": "curator confirmed",
        "actor": "alice",
        "resolved_at": "2026-07-03T00:00:00Z",
    }
    # frozen dataclass: attributes cannot be reassigned
    with pytest.raises(AttributeError):
        rec.status = STATUS_OPEN  # type: ignore[misc]
    # the flags are persisted in props JSON and read back via get_node
    node = store.get_node("gap:1")
    assert node is not None
    assert node["status"] == STATUS_RESOLVED
    assert node["resolved_at"] == "2026-07-03T00:00:00Z"
    assert node["resolution_reason"] == "curator confirmed"
    assert node["resolved_by"] == "alice"
    assert gap_status(store, "gap:1") == STATUS_RESOLVED


def test_resolve_generates_timestamp_when_omitted(store: KuzuGraphStore) -> None:
    # No explicit `at` → resolve_gap stamps a non-empty ISO timestamp itself.
    _seed_gap(store)
    rec = resolve_gap(store, "gap:1", reason="auto", actor="bob")
    assert rec is not None
    assert rec.resolved_at  # non-empty
    assert store.get_node("gap:1")["resolved_at"] == rec.resolved_at


def test_resolve_preserves_existing_props(store: KuzuGraphStore) -> None:
    # Closing a gap must not lose its identity fields (name / gap_type / property).
    _seed_gap(store)
    resolve_gap(store, "gap:1", reason="r", actor="a", at="t")
    node = store.get_node("gap:1")
    assert node["name"] == "нет значения свойства"
    assert node["gap_type"] == "missing_property_value"
    assert node["property_name"] == "conductivity"
    assert node["review_status"] == "pending"


def test_resolve_unknown_gap_is_noop(store: KuzuGraphStore) -> None:
    assert resolve_gap(store, "gap:nope", reason="r", actor="a") is None
    # a graceful no-op does not create the node
    assert store.get_node("gap:nope") is None


def test_reopen_clears_resolution(store: KuzuGraphStore) -> None:
    _seed_gap(store)
    resolve_gap(store, "gap:1", reason="oops", actor="a", at="t")
    assert reopen_gap(store, "gap:1") is True
    assert gap_status(store, "gap:1") == STATUS_OPEN
    node = store.get_node("gap:1")
    # the resolution stamp is gone; identity fields survive
    assert "resolved_at" not in node
    assert "resolution_reason" not in node
    assert "resolved_by" not in node
    assert node["gap_type"] == "missing_property_value"


def test_reopen_unknown_gap_returns_false(store: KuzuGraphStore) -> None:
    assert reopen_gap(store, "gap:nope") is False


def test_resolve_reopen_resolve_round_trips(store: KuzuGraphStore) -> None:
    # Full lifecycle: open → resolved → open → resolved (§15.2).
    _seed_gap(store)
    assert gap_status(store, "gap:1") == STATUS_OPEN
    resolve_gap(store, "gap:1", reason="r1", actor="a", at="t1")
    assert gap_status(store, "gap:1") == STATUS_RESOLVED
    reopen_gap(store, "gap:1")
    assert gap_status(store, "gap:1") == STATUS_OPEN
    resolve_gap(store, "gap:1", reason="r2", actor="b", at="t2")
    assert gap_status(store, "gap:1") == STATUS_RESOLVED
    # the second closure overwrote the first stamp
    assert store.get_node("gap:1")["resolved_by"] == "b"


def test_auto_resolve_only_after_measurement_added(store: KuzuGraphStore) -> None:
    # Before any Measurement the missing_property gap stays open; once a Measurement
    # of that property is attached about the subject, auto-resolve closes it (§15.2).
    _seed_gap(store)
    assert auto_resolve_if_covered(store, "gap:1") is None
    assert gap_status(store, "gap:1") == STATUS_OPEN

    _add_measurement(store, property_name="conductivity")
    rec = auto_resolve_if_covered(store, "gap:1")
    assert isinstance(rec, GapResolution)
    assert rec.actor == "auto"
    assert gap_status(store, "gap:1") == STATUS_RESOLVED


def test_auto_resolve_requires_matching_property(store: KuzuGraphStore) -> None:
    # A Measurement of a *different* property does not cover a missing-property gap.
    _seed_gap(store, property_name="conductivity")
    _add_measurement(store, property_name="density")
    assert auto_resolve_if_covered(store, "gap:1") is None
    assert gap_status(store, "gap:1") == STATUS_OPEN


def test_auto_resolve_ignores_other_gap_types(store: KuzuGraphStore) -> None:
    # Only missing_property_value gaps are auto-closed; an orphan gap is left alone
    # even though the subject has a Measurement.
    _seed_gap(store, gap_type="orphan_entity", property_name="conductivity")
    _add_measurement(store, property_name="conductivity")
    assert auto_resolve_if_covered(store, "gap:1") is None
    assert gap_status(store, "gap:1") == STATUS_OPEN


def test_auto_resolve_is_idempotent(store: KuzuGraphStore) -> None:
    # Once auto-resolved, a second call is a no-op (does not re-stamp).
    _seed_gap(store)
    _add_measurement(store, property_name="conductivity")
    first = auto_resolve_if_covered(store, "gap:1", at="t1")
    assert first is not None
    assert auto_resolve_if_covered(store, "gap:1", at="t2") is None
    # the original timestamp is untouched
    assert store.get_node("gap:1")["resolved_at"] == "t1"
