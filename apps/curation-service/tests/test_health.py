"""Curation service: expert edits, history, review queue, merge (§16/§24.20)."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from curation_service.curation import CurationService

from kg_retrievers.graph_store import KuzuGraphStore
from kg_retrievers.seed import build_seed_graph


@pytest.fixture
def svc():  # type: ignore[no-untyped-def]
    d = tempfile.mkdtemp()
    store = KuzuGraphStore(str(Path(d) / "g"))
    build_seed_graph(store)
    yield CurationService(store)
    store.close()


def test_health(svc: CurationService) -> None:
    assert svc.health()["status"] == "ok"


def test_edit_records_history_and_protects(svc: CurationService) -> None:
    nid = "material:nickel"
    svc.edit_node(nid, {"name": "Никель (исправлено)"}, actor="expert1", reason="уточнение")
    nd = svc.store.get_node(nid)
    assert nd["name"] == "Никель (исправлено)"
    assert nd["review_status"] == "corrected"
    # re-ingestion (guarded) must NOT overwrite a corrected node
    wrote = svc.store.upsert_node_guarded(nid, "Material", name="OVERWRITE")
    assert wrote is False
    assert svc.store.get_node(nid)["name"] == "Никель (исправлено)"
    # history captured
    hist = svc.history(nid)
    assert hist and hist[0]["actor"] == "expert1"


def test_review_queue(svc: CurationService) -> None:
    q = svc.review_queue()
    # the seed's pending Gap should surface
    assert any(item["label"] == "Gap" for item in q)


def test_merge_entities(svc: CurationService) -> None:
    svc.store.upsert_node("material:dup-nickel", "Material", name="Ni (dup)")
    svc.store.upsert_edge("material:dup-nickel", "material:nickel", "PARTITIONED_TO_PHASE")
    before = svc.store.counts()["nodes"]
    svc.merge_entities("material:nickel", "material:dup-nickel", actor="expert1")
    assert svc.store.get_node("material:dup-nickel") is None
    assert svc.store.counts()["nodes"] < before + 2  # dup removed (curation event added)
