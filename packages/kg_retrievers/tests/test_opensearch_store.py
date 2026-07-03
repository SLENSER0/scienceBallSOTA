"""Live round-trip tests for :class:`OpenSearchKeywordStore` (§4.6).

These run against the **live** OpenSearch cluster on ``localhost:9200`` (security
disabled). Each run uses its own throwaway index ``t_os_<pid>`` (PID token, no
randomness) so parallel processes never collide, and the teardown drops it. If the
cluster is genuinely unreachable the whole module skips — it never runs red offline.

The corpus is three RU chunks over two source documents; every expected ranking is
hand-derivable from the ``scientific_text`` analyzer (lowercased Cyrillic tokens):

* ``c1`` — «Обратный осмос …»   (doc ``d1``, page 1, domain ``water``)
* ``c2`` — «Коагуляция …»       (doc ``d1``, page 2, domain ``water``)
* ``c3`` — «Ультрафильтрация …» (doc ``d2``, page 1, domain ``membrane``)
"""

from __future__ import annotations

import os

import pytest
from opensearchpy.exceptions import OpenSearchException

from kg_retrievers.opensearch_store import OpenSearchKeywordStore

# Deterministic per-process index name (PID token, no `random`) (§4.6).
_INDEX = f"t_os_{os.getpid()}"

_CHUNKS = [
    {
        "id": "c1",
        "text": "Обратный осмос для глубокой очистки воды через мембрана",
        "doc_id": "d1",
        "page": 1,
        "domain": "water",
    },
    {
        "id": "c2",
        "text": "Коагуляция и осаждение взвешенных примесей воды",
        "doc_id": "d1",
        "page": 2,
        "domain": "water",
    },
    {
        "id": "c3",
        "text": "Ультрафильтрация воды через половолоконная мембрана",
        "doc_id": "d2",
        "page": 1,
        "domain": "membrane",
    },
]


@pytest.fixture(scope="module")
def store():  # type: ignore[no-untyped-def]
    """A store bound to a fresh throwaway index; skips if OpenSearch is down (§4.6)."""
    try:
        s = OpenSearchKeywordStore(index=_INDEX)
        if not s.ping():
            pytest.skip("live OpenSearch unreachable on localhost:9200")
    except OpenSearchException as exc:  # pragma: no cover - offline path
        pytest.skip(f"live OpenSearch unreachable: {exc}")
    except Exception as exc:  # pragma: no cover - connection refused etc.
        pytest.skip(f"live OpenSearch unreachable: {exc}")
    s.drop_index()  # clean slate in case a prior run crashed mid-way
    try:
        yield s
    finally:
        s.drop_index()  # always clean up our test namespace


def test_full_round_trip(store: OpenSearchKeywordStore) -> None:
    """End-to-end: create → index → search → filter → delete → count (§4.6)."""
    # 1. ensure_index creates it, and is idempotent on a second call.
    assert store.ensure_index() is True
    assert store.client.indices.exists(index=_INDEX) is True
    assert store.ensure_index() is False  # already exists → no-op
    assert store.count() == 0  # freshly created, empty

    # 2. index the three chunks with refresh; count reflects immediately.
    assert store.index_chunks(_CHUNKS) == 3
    assert store.count() == 3

    # 3. «обратный осмос» ranks the matching chunk (c1) first.
    hits = store.search("обратный осмос", top_k=5)
    assert hits, "expected at least one hit for обратный осмос"
    assert hits[0]["id"] == "c1"
    assert set(hits[0]) == {"id", "text", "score", "doc_id", "page"}
    assert hits[0]["doc_id"] == "d1" and hits[0]["page"] == 1
    assert hits[0]["score"] > 0.0

    # 4. a keyword-field filter narrows a broad query to the matching domain.
    #    The scientific_text analyzer does not stem, so query on the exact token
    #    «воды» (present verbatim in all three chunks) matches the whole corpus.
    broad = store.search("воды мембрана", top_k=5)
    assert len(broad) == 3  # all three chunks contain the token «воды»
    narrowed = store.search("воды мембрана", top_k=5, filters={"domain": "membrane"})
    assert len(narrowed) == 1
    assert narrowed[0]["id"] == "c3"

    # 5. delete_by_doc removes both chunks of document d1; count reflects.
    assert store.delete_by_doc("d1") == 2
    assert store.count() == 1
    remaining = store.search("воды мембрана", top_k=5)
    assert {h["id"] for h in remaining} == {"c3"}

    # 6. the deleted document is gone from keyword search too.
    assert store.search("обратный осмос", top_k=5) == []
