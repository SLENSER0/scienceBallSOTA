"""§11.11 — reconstruct EvidenceRefs (page + span) from a community report.

Проверяем, что отчёт по кластеру знаний прослеживается до реальных эвиденсов
(Evidence) с точной локацией в документе-источнике: ``doc_id`` + ``page`` +
символьный диапазон (span), с дедупликацией по ``evidence_id``.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from kg_common import make_id
from kg_retrievers.graph_store import KuzuGraphStore
from kg_retrievers.report_evidence import EvidenceRef, report_to_evidence


def _new_store() -> KuzuGraphStore:
    d = tempfile.mkdtemp()
    return KuzuGraphStore(str(Path(d) / "g"))


def _seed_backed_community(
    store: KuzuGraphStore,
    community_id: int,
    *,
    doc: str,
    page: int,
    char_start: int | None = None,
    char_end: int | None = None,
) -> tuple[str, str, str]:
    """Seed Material(community)←ABOUT_MATERIAL—Measurement—SUPPORTED_BY→Evidence.

    ``char_start``/``char_end`` are custom (non-column) props on the Evidence node.
    """
    mat = make_id("Material", "backed material")
    meas = make_id("Measurement", "backed measurement")
    ev = make_id("Evidence", "backed evidence")
    store.upsert_node(mat, "Material", name="Материал", community_id=community_id)
    store.upsert_node(meas, "Measurement", name="Измерение", property_name="conc")
    ev_props: dict[str, object] = {"text": "supporting sentence", "doc_id": doc, "page": page}
    if char_start is not None:
        ev_props["char_start"] = char_start
    if char_end is not None:
        ev_props["char_end"] = char_end
    store.upsert_node(ev, "Evidence", **ev_props)
    store.upsert_edge(meas, mat, "ABOUT_MATERIAL", confidence=0.9)
    store.upsert_edge(meas, ev, "SUPPORTED_BY", confidence=0.9)
    return mat, meas, ev


def test_backed_community_yields_ref_with_doc_and_page() -> None:
    # Acceptance: ≥1 EvidenceRef with valid doc_id AND page.
    store = _new_store()
    _seed_backed_community(store, 7, doc="report-2025.pdf", page=12, char_start=100, char_end=180)
    refs = report_to_evidence(store, 7)
    assert len(refs) >= 1
    ref = refs[0]
    assert isinstance(ref, EvidenceRef)
    assert ref.doc_id == "report-2025.pdf"
    assert ref.page == 12
    assert ref.evidence_id == make_id("Evidence", "backed evidence")
    store.close()


def test_span_offsets_read_from_props_via_get_node() -> None:
    store = _new_store()
    _seed_backed_community(store, 8, doc="span.pdf", page=2, char_start=345, char_end=402)
    refs = report_to_evidence(store, 8)
    assert len(refs) == 1
    assert refs[0].span_start == 345
    assert refs[0].span_end == 402
    store.close()


def test_evidence_missing_span_has_none_span_but_doc_present() -> None:
    store = _new_store()
    _seed_backed_community(store, 4, doc="nospan.pdf", page=3)  # no char offsets seeded
    refs = report_to_evidence(store, 4)
    assert len(refs) == 1
    assert refs[0].doc_id == "nospan.pdf"
    assert refs[0].page == 3
    assert refs[0].span_start is None
    assert refs[0].span_end is None
    store.close()


def test_unknown_community_yields_empty() -> None:
    store = _new_store()
    _seed_backed_community(store, 7, doc="x.pdf", page=1)
    assert report_to_evidence(store, 999) == []  # no member carries this community_id
    store.close()


def test_member_without_evidence_yields_empty() -> None:
    store = _new_store()
    mat = make_id("Material", "lonely")
    store.upsert_node(mat, "Material", name="Одинокий материал", community_id=2)
    assert report_to_evidence(store, 2) == []  # community exists but no Measurement/Evidence
    store.close()


def test_dedup_shared_evidence() -> None:
    # Two Measurements of the same community member cite one shared Evidence.
    store = _new_store()
    mat = make_id("Material", "shared-mat")
    ev = make_id("Evidence", "shared-ev")
    store.upsert_node(mat, "Material", name="Общий материал", community_id=3)
    store.upsert_node(ev, "Evidence", doc_id="shared.pdf", page=5, char_start=1, char_end=9)
    for key in ("m1", "m2"):
        meas = make_id("Measurement", key)
        store.upsert_node(meas, "Measurement", name=f"Изм {key}")
        store.upsert_edge(meas, mat, "ABOUT_MATERIAL", confidence=0.8)
        store.upsert_edge(meas, ev, "SUPPORTED_BY", confidence=0.8)
    refs = report_to_evidence(store, 3)
    assert len(refs) == 1  # collapsed to a single EvidenceRef
    assert refs[0].evidence_id == ev
    assert refs[0].doc_id == "shared.pdf"
    assert refs[0].page == 5
    store.close()


def test_as_dict_shape_and_values() -> None:
    store = _new_store()
    _seed_backed_community(store, 5, doc="a.pdf", page=7, char_start=20, char_end=44)
    ref = report_to_evidence(store, 5)[0]
    d = ref.as_dict()
    assert set(d) == {"evidence_id", "doc_id", "page", "span_start", "span_end"}
    assert d["doc_id"] == "a.pdf"
    assert d["page"] == 7
    assert d["span_start"] == 20
    assert d["span_end"] == 44
    assert d["evidence_id"] == ref.evidence_id
    store.close()
