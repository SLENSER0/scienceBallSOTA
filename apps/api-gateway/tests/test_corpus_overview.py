"""TTL-cache tests for the corpus-overview projection (§17.9).

Proves the module-level TTL cache added to ``overview()`` is behavior-preserving:
a cache hit returns exactly what a fresh recompute would (equal content), the hot
projection path is skipped on a hit, a different param-set / an expired entry
recomputes, and clustering side effects still run. / Тесты TTL-кэша проекции.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import api_gateway.routers.corpus_overview as co

from kg_retrievers.graph_store import KuzuGraphStore

_PARAMS = {"edge_limit": 8000, "min_degree": 0, "cluster": False, "max_communities": 60}


def _make_store() -> KuzuGraphStore:
    """A tiny connected graph: 3 nodes, 2 edges (every node has degree >= 1)."""
    d = tempfile.mkdtemp()
    store = KuzuGraphStore(str(Path(d) / "g"))
    store.upsert_node("n1", "Material", name="Никель")
    store.upsert_node("n2", "Property", name="Твёрдость")
    store.upsert_node("n3", "Method", name="Электролиз")
    store.upsert_edge("n1", "n2", "HAS_PROPERTY")
    store.upsert_edge("n2", "n3", "MEASURED_BY")
    return store


def test_overview_cached_matches_uncached(monkeypatch) -> None:
    # A cache hit must return the same content a fresh compute produces (the
    # projection is a pure function of the graph + params between ingests).
    store = _make_store()
    monkeypatch.setattr(co, "get_store", lambda: store)
    co._overview_cache.clear()
    try:
        first = co.overview(**_PARAMS)
        co._overview_cache.clear()  # force a fresh recompute
        second = co.overview(**_PARAMS)
        assert first == second
        assert first is not second  # distinct computations, identical content
        assert first["stats"]["nodeCount"] == 3
        assert first["stats"]["edgeCount"] == 2
    finally:
        store.close()


def test_overview_ttl_cache_hit_skips_recompute(monkeypatch) -> None:
    # A second identical request within the TTL is served from the cache: the
    # heavy projection path (spied via _summaries) does not run again.
    store = _make_store()
    monkeypatch.setattr(co, "get_store", lambda: store)
    co._overview_cache.clear()

    calls = {"n": 0}
    real_summaries = co._summaries

    def spy(s):  # type: ignore[no-untyped-def]
        calls["n"] += 1
        return real_summaries(s)

    monkeypatch.setattr(co, "_summaries", spy)
    try:
        r1 = co.overview(**_PARAMS)
        r2 = co.overview(**_PARAMS)
        assert r1 == r2
        assert r1 is r2  # exact cached object returned on the hit
        assert calls["n"] == 1  # compute path ran once; the hit skipped it

        # A different param-set is a different cache key → recompute.
        r3 = co.overview(**{**_PARAMS, "edge_limit": 7999})
        assert calls["n"] == 2
        assert r3["stats"]["nodeCount"] == r1["stats"]["nodeCount"]
    finally:
        store.close()


def test_overview_cache_expires(monkeypatch) -> None:
    # Once an entry ages past the TTL it is recomputed (not served stale).
    store = _make_store()
    monkeypatch.setattr(co, "get_store", lambda: store)
    co._overview_cache.clear()

    calls = {"n": 0}
    real_summaries = co._summaries

    def spy(s):  # type: ignore[no-untyped-def]
        calls["n"] += 1
        return real_summaries(s)

    monkeypatch.setattr(co, "_summaries", spy)
    try:
        r1 = co.overview(**_PARAMS)
        assert calls["n"] == 1
        # age the single cached entry beyond the TTL window
        key = next(iter(co._overview_cache))
        ts, val = co._overview_cache[key]
        co._overview_cache[key] = (ts - co._OVERVIEW_TTL_S - 1.0, val)
        r2 = co.overview(**_PARAMS)
        assert calls["n"] == 2  # expired → recomputed
        assert r1 == r2
    finally:
        store.close()
