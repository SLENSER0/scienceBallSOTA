"""Query-embedding memoization (§4 perf) — offline, no model load.

Проверяет кэш эмбеддинга запроса: повторный запрос переиспользует вектор и не
пересчитывает эмбеддинг. Monkeypatches ``embed_one`` in the ``vector_store``
namespace so the real model is never loaded (fast + offline).
"""

from __future__ import annotations

import kg_retrievers.vector_store as vs


def test_embed_query_is_memoized(monkeypatch) -> None:
    calls: list[str] = []

    def fake_embed_one(text: str) -> list[float]:
        calls.append(text)
        return [float(len(text)), 1.0, 2.0]

    monkeypatch.setattr(vs, "embed_one", fake_embed_one)
    vs._embed_query.cache_clear()

    first = vs._embed_query("никель")
    second = vs._embed_query("никель")

    # behavior-preserving: same value as the underlying embed_one, returned as a
    # tuple (immutable cache value)
    assert first == (float(len("никель")), 1.0, 2.0)
    assert second == first
    # but embed_one was invoked only once for the repeated query
    assert calls == ["никель"]


def test_embed_query_distinct_queries_not_collapsed(monkeypatch) -> None:
    def fake_embed_one(text: str) -> list[float]:
        return [float(len(text))]

    monkeypatch.setattr(vs, "embed_one", fake_embed_one)
    vs._embed_query.cache_clear()

    assert vs._embed_query("SO2") == (3.0,)
    assert vs._embed_query("сероочистка") == (float(len("сероочистка")),)


def test_embed_query_empty_vector_is_falsy(monkeypatch) -> None:
    # search() short-circuits on an empty embedding; the cached empty tuple must
    # stay falsy after the list() round-trip.
    monkeypatch.setattr(vs, "embed_one", lambda _t: [])
    vs._embed_query.cache_clear()

    vec = list(vs._embed_query("anything"))
    assert vec == []
    assert not vec
