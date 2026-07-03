"""Whole-store edge-signature audit tests (§8.2 / §3.16).

Hand-checkable graphs built per test over a fresh temp Kuzu store:

- a valid ``Evidence-[:SUPPORTS]->Claim`` edge -> ``ok`` True, ``violation_count`` 0;
- an injected ``Material-[:MEASURED]->Person`` edge shows up as a violation;
- ``total_edges`` equals the number of ``Rel`` rows;
- an empty store audits ``ok`` with ``total_edges`` 0;
- ``as_dict()['violations']`` is a list of dicts each carrying ``rel_type``;
- a ``Chunk-[:MENTIONS]->Material`` (Entity-target) edge is accepted;
- ``ok`` is False exactly when ``violation_count > 0``.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from kg_retrievers.edge_signature_audit import (
    EdgeSignatureAudit,
    EdgeViolation,
    audit_edge_signatures,
)
from kg_retrievers.graph_store import KuzuGraphStore


def _store() -> KuzuGraphStore:
    d = tempfile.mkdtemp()
    return KuzuGraphStore(str(Path(d) / "g"))


def test_valid_edge_is_ok() -> None:
    store = _store()
    store.upsert_node("ev1", "Evidence", name="e")
    store.upsert_node("cl1", "Claim", name="c")
    store.upsert_edge("ev1", "cl1", "SUPPORTS")
    audit = audit_edge_signatures(store)
    assert audit.ok is True
    assert audit.violation_count == 0
    assert audit.violations == ()


def test_injected_bad_edge_is_a_violation() -> None:
    store = _store()
    store.upsert_node("m1", "Material", name="m")
    store.upsert_node("p1", "Person", name="p")
    store.upsert_edge("m1", "p1", "MEASURED")
    audit = audit_edge_signatures(store)
    assert audit.ok is False
    assert audit.violation_count == 1
    v = audit.violations[0]
    assert v == EdgeViolation(
        src_id="m1",
        dst_id="p1",
        rel_type="MEASURED",
        from_label="Material",
        to_label="Person",
    )
    assert v.from_label == "Material"
    assert v.to_label == "Person"


def test_total_edges_counts_rel_rows() -> None:
    store = _store()
    store.upsert_node("ev1", "Evidence", name="e")
    store.upsert_node("cl1", "Claim", name="c")
    store.upsert_node("m1", "Material", name="m")
    store.upsert_node("p1", "Person", name="p")
    store.upsert_edge("ev1", "cl1", "SUPPORTS")  # valid
    store.upsert_edge("m1", "p1", "MEASURED")  # invalid
    audit = audit_edge_signatures(store)
    assert audit.total_edges == 2
    assert audit.violation_count == 1


def test_empty_store_is_ok() -> None:
    store = _store()
    audit = audit_edge_signatures(store)
    assert audit.ok is True
    assert audit.total_edges == 0
    assert audit.violation_count == 0


def test_as_dict_violations_is_list_of_dicts_with_rel_type() -> None:
    store = _store()
    store.upsert_node("m1", "Material", name="m")
    store.upsert_node("p1", "Person", name="p")
    store.upsert_edge("m1", "p1", "MEASURED")
    audit = audit_edge_signatures(store)
    d = audit.as_dict()
    assert isinstance(d["violations"], list)
    assert all(isinstance(item, dict) for item in d["violations"])
    assert d["violations"][0]["rel_type"] == "MEASURED"
    assert d["total_edges"] == 1
    assert d["violation_count"] == 1
    assert d["ok"] is False


def test_entity_target_expansion_accepts_mentions_material() -> None:
    # Chunk-[:MENTIONS]->Entity is declared; Material is a concrete Entity label.
    store = _store()
    store.upsert_node("ch1", "Chunk", text="a chunk")
    store.upsert_node("m1", "Material", name="m")
    store.upsert_edge("ch1", "m1", "MENTIONS")
    audit = audit_edge_signatures(store)
    assert audit.ok is True
    assert audit.violation_count == 0


def test_ok_is_false_exactly_when_violations_present() -> None:
    store = _store()
    store.upsert_node("ev1", "Evidence", name="e")
    store.upsert_node("cl1", "Claim", name="c")
    store.upsert_edge("ev1", "cl1", "SUPPORTS")
    good = audit_edge_signatures(store)
    assert good.ok is (good.violation_count == 0)
    assert good.ok is True

    store.upsert_node("m1", "Material", name="m")
    store.upsert_node("p1", "Person", name="p")
    store.upsert_edge("m1", "p1", "MEASURED")
    bad = audit_edge_signatures(store)
    assert bad.ok is (bad.violation_count == 0)
    assert bad.ok is False


def test_result_type_is_frozen_audit() -> None:
    store = _store()
    audit = audit_edge_signatures(store)
    assert isinstance(audit, EdgeSignatureAudit)
