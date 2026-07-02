"""Vector + keyword + hybrid search (§4/§12). Loads the fastembed model."""

from __future__ import annotations

import tempfile

import pytest

from kg_retrievers.hybrid import HybridRetriever
from kg_retrievers.keyword_store import KeywordStore
from kg_retrievers.vector_store import VectorStore

PASSAGES = [
    {
        "id": "c1",
        "text": "Электроэкстракция никеля из сульфатного электролита при 60 °C.",
        "payload": {"doc_id": "d1"},
    },
    {
        "id": "c2",
        "text": "Мокрая сероочистка удаляет SO2 из отходящих газов на 95%.",
        "payload": {"doc_id": "d2"},
    },
    {
        "id": "c3",
        "text": "Reverse osmosis reduces total dissolved solids in mine water.",
        "payload": {"doc_id": "d3"},
    },
]


def test_keyword_search() -> None:
    d = tempfile.mkdtemp()
    ks = KeywordStore(path=d)
    ks.index(PASSAGES)
    hits = ks.search("сероочистка SO2", limit=2)
    assert hits and hits[0].id == "c2"


@pytest.mark.slow
def test_vector_crosslingual() -> None:
    vs = VectorStore(collection="test_x", on_disk=False)
    vs.index(PASSAGES)
    # English query should retrieve the Russian nickel-electrowinning passage
    hits = vs.search("nickel electrowinning sulfate electrolyte", limit=1)
    assert hits and hits[0].id == "c1"


@pytest.mark.slow
def test_hybrid_fusion() -> None:
    d = tempfile.mkdtemp()
    ks = KeywordStore(path=d)
    ks.index(PASSAGES)
    vs = VectorStore(collection="test_h", on_disk=False)
    vs.index(PASSAGES)
    hr = HybridRetriever(vector=vs, keyword=ks)
    assert hr.available()
    hits = hr.search("удаление SO2 сероочистка", limit=2)
    assert hits and hits[0].id == "c2"
