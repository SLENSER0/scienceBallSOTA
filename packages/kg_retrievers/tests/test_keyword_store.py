"""KeywordStore top-k select is behaviour-preserving (§4 / ADR-0005).

Проверяет, что переход с полной сортировки ``sorted(..., reverse=True)[:limit]`` на
частичный отбор ``heapq.nlargest`` возвращает *побайтово те же* хиты — тот же порядок,
те же оценки, тот же стабильный tie-break (меньший исходный индекс идёт первым) — this
guards the agent hero path where KeywordStore.search() runs once per query.
"""

from __future__ import annotations

import tempfile

from kg_retrievers.keyword_store import KeywordHit, KeywordStore, tokenize

# 8-doc corpus. c1/c2/c5 are byte-identical so they collide on the *same* BM25 score,
# exercising the stable tie-break. Their term "рений" appears in only 3 of 8 docs
# (< N/2) → BM25 IDF stays positive, so the ``score > 0`` filter keeps them.
PASSAGES = [
    {"id": "c1", "text": "рений редкий металл", "payload": {"doc": "d1"}},
    {"id": "c2", "text": "рений редкий металл", "payload": {"doc": "d2"}},  # dup of c1
    {"id": "c3", "text": "сероочистка удаляет SO2 из газов", "payload": {"doc": "d3"}},
    {"id": "c4", "text": "reverse osmosis mine water", "payload": {"doc": "d4"}},
    {"id": "c5", "text": "рений редкий металл", "payload": {"doc": "d5"}},  # dup again
    {"id": "c6", "text": "флотация медь концентрат", "payload": {"doc": "d6"}},
    {"id": "c7", "text": "электролит ток напряжение ячейка", "payload": {"doc": "d7"}},
    {"id": "c8", "text": "температура давление реактор синтез", "payload": {"doc": "d8"}},
]


def _reference_search(ks: KeywordStore, query: str, limit: int) -> list[KeywordHit]:
    """Pre-optimisation oracle: the original full-sort ranking, verbatim."""
    scores = ks._bm25.get_scores(tokenize(query))
    ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:limit]
    return [
        KeywordHit(id=ks.ids[i], score=float(scores[i]), payload=ks.payloads[i])
        for i in ranked
        if scores[i] > 0
    ]


def _fresh_store() -> KeywordStore:
    ks = KeywordStore(path=tempfile.mkdtemp())
    ks.index(PASSAGES)
    return ks


def test_search_matches_full_sort_oracle() -> None:
    """search() == the old sorted-then-slice implementation, across queries/limits."""
    ks = _fresh_store()
    for query in ("рений редкий металл", "сероочистка SO2", "reverse osmosis", "медь"):
        for limit in (1, 2, 3, 6, 100):
            assert ks.search(query, limit=limit) == _reference_search(ks, query, limit)


def test_tie_break_prefers_lower_index() -> None:
    """Duplicate docs tie on score → the lower original index wins (insertion order)."""
    ks = _fresh_store()
    # c1/c2/c5 are identical texts → identical positive BM25 score for this query.
    hits = ks.search("рений редкий металл", limit=3)
    assert [h.id for h in hits] == ["c1", "c2", "c5"]  # stable: ascending original index
    # all three share the exact same float score
    assert hits[0].score == hits[1].score == hits[2].score > 0.0


def test_zero_score_docs_filtered_out() -> None:
    """Docs the query never touches (score 0) stay excluded even under a large limit."""
    ks = _fresh_store()
    hits = ks.search("медь", limit=100)  # only c6 mentions "медь"
    assert [h.id for h in hits] == ["c6"]


def test_empty_store_returns_empty() -> None:
    """No corpus → no BM25 index → empty result (unchanged guard)."""
    ks = KeywordStore(path=tempfile.mkdtemp())
    assert ks.search("anything", limit=8) == []
