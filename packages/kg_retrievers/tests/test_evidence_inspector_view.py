"""§17.13 — hand-checked tests for the single-evidence inspector view-model.

Builds a tiny temp Kuzu store and checks every trust-field projection and the
prev/next navigation by hand:

    e_full  doc_id=D1 page=7 table_id=T3 confidence=0.82 extractor=llm-x
            edge_ref="a|MENTIONS|b"  (figureId / paragraphId absent)
    e_bare  no review_status  -> defaults to "pending"

Sibling ring ["e1","e2","e3"]: for "e2" prev="e1" next="e3"; ends are open.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from kg_common import make_id
from kg_retrievers.evidence_inspector_view import (
    EvidenceInspectorView,
    build_evidence_inspector,
)
from kg_retrievers.graph_store import KuzuGraphStore

E_FULL = make_id("Evidence", "full trust fields")
E_BARE = make_id("Evidence", "bare no review status")


@pytest.fixture
def store():  # type: ignore[no-untyped-def]
    d = tempfile.mkdtemp()
    s = KuzuGraphStore(str(Path(d) / "g"))
    yield s
    s.close()


def _seed_full(s: KuzuGraphStore) -> None:
    """One richly-populated Evidence node carrying every §5.2.6 trust field."""
    s.upsert_node(
        E_FULL,
        "Evidence",
        doc_id="D1",
        page=7,
        table_id="T3",
        extracted_statement="Tensile strength was 420 MPa.",
        snippet="... measured tensile strength of 420 MPa at RT ...",
        parsed_object={"property": "tensile_strength", "value": 420, "unit": "MPa"},
        extractor="llm-x",
        model_version="v1.2.3",
        confidence=0.82,
        review_status="accepted",
        reviewer="curator@lab",
        edge_ref="a|MENTIONS|b",
    )


def test_absent_id_returns_none(store: KuzuGraphStore) -> None:
    assert build_evidence_inspector(store, "does-not-exist") is None


def test_full_trust_fields_surface(store: KuzuGraphStore) -> None:
    _seed_full(store)
    view = build_evidence_inspector(store, E_FULL)
    assert isinstance(view, EvidenceInspectorView)
    assert view.evidence_id == E_FULL
    assert view.doc_id == "D1"
    # page surfaces as an int, confidence as a float.
    assert view.page == 7 and isinstance(view.page, int)
    assert view.confidence == pytest.approx(0.82)
    assert isinstance(view.confidence, float)
    # locator: tableId set, figureId / paragraphId absent -> None.
    assert view.locator["tableId"] == "T3"
    assert view.locator["figureId"] is None
    assert view.locator["paragraphId"] is None
    # remaining trust fields round-trip through props.
    assert view.extracted_statement == "Tensile strength was 420 MPa."
    assert view.snippet.startswith("... measured tensile strength")
    assert view.parsed_object == {"property": "tensile_strength", "value": 420, "unit": "MPa"}
    assert view.extractor == "llm-x"
    assert view.model_version == "v1.2.3"
    assert view.review_status == "accepted"
    assert view.reviewer == "curator@lab"
    assert view.edge_ref == "a|MENTIONS|b"


def test_review_status_defaults_to_pending_when_unset(store: KuzuGraphStore) -> None:
    store.upsert_node(E_BARE, "Evidence", doc_id="D2")
    view = build_evidence_inspector(store, E_BARE)
    assert view is not None
    assert view.review_status == "pending"
    # Unset optionals collapse to None; locator is all-None.
    assert view.page is None
    assert view.confidence is None
    assert view.reviewer is None
    assert view.edge_ref is None
    assert view.locator == {"tableId": None, "figureId": None, "paragraphId": None}


def test_prev_next_middle_sibling(store: KuzuGraphStore) -> None:
    _seed_full(store)
    view = build_evidence_inspector(store, "e2", sibling_ids=["e1", "e2", "e3"])
    # Node e2 is absent from the store, so the view is None regardless of siblings.
    assert view is None
    # Seed e2 itself and re-check navigation.
    store.upsert_node("e2", "Evidence")
    view = build_evidence_inspector(store, "e2", sibling_ids=["e1", "e2", "e3"])
    assert view is not None
    assert view.prev_id == "e1"
    assert view.next_id == "e3"


def test_first_sibling_has_no_prev(store: KuzuGraphStore) -> None:
    store.upsert_node("e1", "Evidence")
    view = build_evidence_inspector(store, "e1", sibling_ids=["e1", "e2", "e3"])
    assert view is not None
    assert view.prev_id is None
    assert view.next_id == "e2"


def test_last_sibling_has_no_next(store: KuzuGraphStore) -> None:
    store.upsert_node("e3", "Evidence")
    view = build_evidence_inspector(store, "e3", sibling_ids=["e1", "e2", "e3"])
    assert view is not None
    assert view.prev_id == "e2"
    assert view.next_id is None


def test_no_sibling_ids_gives_no_navigation(store: KuzuGraphStore) -> None:
    _seed_full(store)
    view = build_evidence_inspector(store, E_FULL)
    assert view is not None
    assert view.prev_id is None
    assert view.next_id is None
    # Empty sibling list behaves the same as None.
    view2 = build_evidence_inspector(store, E_FULL, sibling_ids=[])
    assert view2 is not None
    assert view2.prev_id is None and view2.next_id is None


def test_as_dict_camelcase_and_json_serialisable(store: KuzuGraphStore) -> None:
    _seed_full(store)
    view = build_evidence_inspector(store, E_FULL, sibling_ids=[E_FULL, "e-next"])
    assert view is not None
    d = view.as_dict()
    # edgeRef present when the node carries a generated edge id.
    assert d["edgeRef"] == "a|MENTIONS|b"
    # camelCase keys throughout.
    assert d["evidenceId"] == E_FULL
    assert d["docId"] == "D1"
    assert d["extractedStatement"] == "Tensile strength was 420 MPa."
    assert d["modelVersion"] == "v1.2.3"
    assert d["reviewStatus"] == "accepted"
    assert d["nextId"] == "e-next"
    assert d["prevId"] is None
    assert d["locator"]["tableId"] == "T3"
    # Fully JSON-serialisable.
    encoded = json.dumps(d)
    assert '"edgeRef"' in encoded

    # as_dict returns copies: mutating them must not touch the frozen view.
    d["locator"]["tableId"] = "MUT"
    d["parsedObject"]["value"] = 0
    assert view.locator["tableId"] == "T3"
    assert view.parsed_object == {"property": "tensile_strength", "value": 420, "unit": "MPa"}
