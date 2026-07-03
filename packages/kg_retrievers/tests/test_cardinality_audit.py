"""Functional-cardinality invariants over a temp Kuzu store (§8 / §3.16).

Hand-built graphs exercise the default rules (Measurement: exactly one
``OF_PROPERTY`` and one ``HAS_UNIT``; Composition: >= one ``CONTAINS_ELEMENT``)
plus a custom single-rule restriction. Each measurement/composition points at
plain ``Entity`` targets (properties, units, elements) so the outgoing edge
counts are hand-checkable.
"""

from __future__ import annotations

import tempfile
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from kg_retrievers.cardinality_audit import (
    CARDINALITY_RULES,
    CardinalityAudit,
    CardinalityRule,
    CardinalityViolation,
    audit_cardinality,
)
from kg_retrievers.graph_store import KuzuGraphStore


@pytest.fixture
def store():  # type: ignore[no-untyped-def]
    d = tempfile.mkdtemp()
    s = KuzuGraphStore(str(Path(d) / "g"))
    yield s
    s.close()


def _measurement(store: KuzuGraphStore, mid: str, *, props: int, units: int) -> None:
    """Create a Measurement ``mid`` with ``props`` OF_PROPERTY and ``units`` HAS_UNIT."""
    store.upsert_node(mid, "Measurement", name=mid)
    for i in range(props):
        pid = f"{mid}_p{i}"
        store.upsert_node(pid, "Property", name=pid)
        store.upsert_edge(mid, pid, "OF_PROPERTY")
    for i in range(units):
        uid = f"{mid}_u{i}"
        store.upsert_node(uid, "Unit", name=uid)
        store.upsert_edge(mid, uid, "HAS_UNIT")


def _composition(store: KuzuGraphStore, cid: str, *, elements: int) -> None:
    store.upsert_node(cid, "Composition", name=cid)
    for i in range(elements):
        eid = f"{cid}_e{i}"
        store.upsert_node(eid, "Element", name=eid)
        store.upsert_edge(cid, eid, "CONTAINS_ELEMENT")


def test_well_formed_measurement_ok(store: KuzuGraphStore) -> None:
    _measurement(store, "m1", props=1, units=1)
    audit = audit_cardinality(store)
    assert audit.ok is True
    assert audit.violations == ()
    assert audit.checked_nodes == 1


def test_missing_of_property_violation(store: KuzuGraphStore) -> None:
    _measurement(store, "m1", props=0, units=1)
    audit = audit_cardinality(store)
    assert audit.ok is False
    assert len(audit.violations) == 1
    v = audit.violations[0]
    assert v.node_id == "m1"
    assert v.observed == 0
    assert v.rule.rel_type == "OF_PROPERTY"


def test_too_many_units_violates_max(store: KuzuGraphStore) -> None:
    _measurement(store, "m1", props=1, units=2)
    audit = audit_cardinality(store)
    assert audit.ok is False
    unit_viols = [v for v in audit.violations if v.rule.rel_type == "HAS_UNIT"]
    assert len(unit_viols) == 1
    v = unit_viols[0]
    assert v.observed == 2
    assert v.rule.max == 1


def test_composition_needs_at_least_one_element(store: KuzuGraphStore) -> None:
    _composition(store, "c1", elements=0)
    audit = audit_cardinality(store)
    assert audit.ok is False
    viols = [v for v in audit.violations if v.rule.label == "Composition"]
    assert len(viols) == 1
    v = viols[0]
    assert v.node_id == "c1"
    assert v.observed == 0
    assert v.rule.min == 1
    assert v.rule.max is None


def test_composition_with_elements_ok(store: KuzuGraphStore) -> None:
    _composition(store, "c1", elements=3)
    audit = audit_cardinality(store)
    assert audit.ok is True
    assert audit.checked_nodes == 1


def test_checked_nodes_counts_rule_labels_only(store: KuzuGraphStore) -> None:
    _measurement(store, "m1", props=1, units=1)
    _composition(store, "c1", elements=1)
    # A node whose label is in no rule must not be counted.
    store.upsert_node("d1", "Document", name="d1")
    audit = audit_cardinality(store)
    assert audit.checked_nodes == 2
    assert audit.ok is True


def test_ok_iff_no_violations(store: KuzuGraphStore) -> None:
    _measurement(store, "m1", props=1, units=1)
    good = audit_cardinality(store)
    assert good.ok is True and good.violations == ()
    _measurement(store, "m2", props=0, units=1)
    bad = audit_cardinality(store)
    assert bad.ok is False and len(bad.violations) >= 1


def test_custom_single_rule_restricts_checked_nodes(store: KuzuGraphStore) -> None:
    _measurement(store, "m1", props=1, units=0)  # would fail HAS_UNIT under defaults
    _composition(store, "c1", elements=0)  # would fail CONTAINS_ELEMENT under defaults
    rule = CardinalityRule(label="Measurement", rel_type="OF_PROPERTY", min=1, max=1)
    audit = audit_cardinality(store, rules=(rule,))
    # Only Measurement nodes are checked; Composition is out of scope.
    assert audit.checked_nodes == 1
    assert audit.ok is True


def test_empty_store(store: KuzuGraphStore) -> None:
    audit = audit_cardinality(store)
    assert audit.ok is True
    assert audit.checked_nodes == 0
    assert audit.violations == ()


def test_as_dict_roundtrip(store: KuzuGraphStore) -> None:
    _measurement(store, "m1", props=0, units=1)
    audit = audit_cardinality(store)
    d = audit.as_dict()
    assert d["checked_nodes"] == 1
    assert d["ok"] is False
    assert d["violations"][0]["node_id"] == "m1"
    assert d["violations"][0]["observed"] == 0
    assert d["violations"][0]["rule"] == {
        "label": "Measurement",
        "rel_type": "OF_PROPERTY",
        "min": 1,
        "max": 1,
    }


def test_default_rules_present() -> None:
    pairs = {(r.label, r.rel_type) for r in CARDINALITY_RULES}
    assert ("Measurement", "OF_PROPERTY") in pairs
    assert ("Measurement", "HAS_UNIT") in pairs
    assert ("Composition", "CONTAINS_ELEMENT") in pairs


def test_frozen_dataclasses() -> None:
    rule = CardinalityRule(label="Measurement", rel_type="HAS_UNIT", min=1, max=1)
    with pytest.raises(FrozenInstanceError):
        rule.min = 0  # type: ignore[misc]
    audit = CardinalityAudit(checked_nodes=0, violations=())
    with pytest.raises(FrozenInstanceError):
        audit.checked_nodes = 5  # type: ignore[misc]
    viol = CardinalityViolation(node_id="m1", rule=rule, observed=0)
    with pytest.raises(FrozenInstanceError):
        viol.observed = 1  # type: ignore[misc]
