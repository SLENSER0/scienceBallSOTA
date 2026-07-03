"""Entity Detail view-model over a seeded temp KuzuGraphStore (§5.2.4 / §17.11).

Seed graph (edges stored directed as written):

    Experiment(exp:1) -MEASURED_PROPERTY-> Material(mat:al) -IMPROVES-> Property(prop:str)
    Material(mat:al) -SUPPORTED_BY-> Evidence(ev:1)
    Material(mat:al) -SUPPORTED_BY-> Evidence(ev:2)

Center under test is ``mat:al`` (Material 'Al-2024', review_status=accepted,
aliases ['AA2024']). All expectations below are hand-computed against this shape.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from kg_retrievers.entity_detail_view import (
    EntityDetailView,
    build_entity_detail,
)
from kg_retrievers.graph_store import KuzuGraphStore

MATERIAL_ID = "mat:al"


@pytest.fixture
def store():  # type: ignore[no-untyped-def]
    d = tempfile.mkdtemp()
    s = KuzuGraphStore(str(Path(d) / "g"))
    _seed(s)
    yield s
    s.close()


def _seed(s: KuzuGraphStore) -> None:
    s.upsert_node(
        MATERIAL_ID,
        "Material",
        name="Al-2024",
        canonical_name="Al-2024",
        review_status="accepted",
        aliases=["AA2024"],
        confidence=0.95,
    )
    s.upsert_node("prop:str", "Property", name="tensile strength", property_name="strength")
    s.upsert_node("exp:1", "Experiment", name="tensile test")
    s.upsert_node("ev:1", "Evidence", text="прочность выросла", doc_id="doc:a", page=2)
    s.upsert_node("ev:2", "Evidence", text="second span", doc_id="doc:a", page=5)
    s.upsert_edge(MATERIAL_ID, "prop:str", "IMPROVES", confidence=0.9)
    s.upsert_edge("exp:1", MATERIAL_ID, "MEASURED_PROPERTY", confidence=0.8)
    s.upsert_edge(MATERIAL_ID, "ev:1", "SUPPORTED_BY", evidence_ids=["ev:1"])
    s.upsert_edge(MATERIAL_ID, "ev:2", "SUPPORTED_BY", evidence_ids=["ev:2"])


def test_unknown_id_returns_none(store: KuzuGraphStore) -> None:
    assert build_entity_detail(store, "does-not-exist") is None


def test_header_fields(store: KuzuGraphStore) -> None:
    view = build_entity_detail(store, MATERIAL_ID)
    assert isinstance(view, EntityDetailView)
    assert view.entity_id == MATERIAL_ID
    assert view.canonical_name == "Al-2024"
    assert view.entity_type == "Material"
    assert view.confidence == pytest.approx(0.95)


def test_verified_and_review_status(store: KuzuGraphStore) -> None:
    view = build_entity_detail(store, MATERIAL_ID)
    assert view is not None
    assert view.review_status == "accepted"
    assert view.verified is True


def test_aliases_tuple(store: KuzuGraphStore) -> None:
    view = build_entity_detail(store, MATERIAL_ID)
    assert view is not None
    assert view.aliases == ("AA2024",)


def test_outgoing_groups_property_under_improves(store: KuzuGraphStore) -> None:
    view = build_entity_detail(store, MATERIAL_ID)
    assert view is not None
    assert "IMPROVES" in view.outgoing
    targets = view.outgoing["IMPROVES"]
    assert len(targets) == 1
    assert targets[0]["id"] == "prop:str"
    assert targets[0].get("name") == "tensile strength"


def test_incoming_groups_experiment_under_measured_property(store: KuzuGraphStore) -> None:
    view = build_entity_detail(store, MATERIAL_ID)
    assert view is not None
    assert "MEASURED_PROPERTY" in view.incoming
    sources = view.incoming["MEASURED_PROPERTY"]
    assert len(sources) == 1
    assert sources[0]["id"] == "exp:1"


def test_evidence_count_matches_supported_by_edges(store: KuzuGraphStore) -> None:
    view = build_entity_detail(store, MATERIAL_ID)
    assert view is not None
    assert view.evidence_count == 2


def test_as_dict_is_json_serialisable_camel_case(store: KuzuGraphStore) -> None:
    view = build_entity_detail(store, MATERIAL_ID)
    assert view is not None
    payload = view.as_dict()
    assert payload["canonicalName"] == "Al-2024"
    assert payload["verified"] is True
    assert payload["evidenceCount"] == 2
    outgoing = payload["outgoingByType"]
    incoming = payload["incomingByType"]
    assert isinstance(outgoing, dict)
    assert isinstance(outgoing["IMPROVES"], list)
    assert isinstance(incoming["MEASURED_PROPERTY"], list)
    # round-trips through json without error (plain dicts / lists only)
    reloaded = json.loads(json.dumps(payload))
    assert reloaded["outgoingByType"]["IMPROVES"][0]["id"] == "prop:str"
