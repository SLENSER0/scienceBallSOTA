"""Behavior-preserving cache guard for the §8.8 mention resolver.

``resolve_mention`` used to call ``AliasIndex.build_from_store`` on every
invocation — a full entity-node scan + index rebuild per call. The new
``_alias_index`` memoizes that index by ``db_path`` and invalidates it on a cheap
entity-count signature (the same pattern ``_matrix`` / the search router use).

These tests prove the memoization is behavior-preserving:

* the cached index resolves identically to a fresh ``build_from_store``;
* a second call over an unchanged graph reuses the same object and issues no
  rebuild (only the cheap count signature);
* changing the entity count rebuilds the index (correct after ingestion);
* a store that cannot answer the count query falls back to an uncached build.
"""

from __future__ import annotations

from typing import Any

import pytest
from api_gateway import mention_resolver as mr
from api_gateway.mention_resolver import _alias_index

from kg_retrievers.alias_index import AliasIndex

_NODES: list[dict[str, Any]] = [
    {"id": "mat:1", "label": "Material", "name": "AA2024", "aliases_text": "дюраль|Д16"},
    {"id": "mat:2", "label": "Material", "name": "Titanium", "aliases_text": "титан"},
]


class FakeStore:
    """Minimal graph store: answers the label-count and the entity-scan queries.

    Тестовый стор — подсчитывает вызовы ``RETURN n`` (build) и ``count(n)``
    (signature) so a rebuild vs a cache hit is observable.
    """

    def __init__(self, nodes: list[dict[str, Any]], db_path: str = "fake://db") -> None:
        self._nodes = [dict(n) for n in nodes]
        self.db_path = db_path
        self.build_calls = 0
        self.count_calls = 0

    def rows(self, cypher: str, params: dict[str, Any] | None = None) -> list[list[Any]]:
        labels = set((params or {}).get("labels", []))
        if "count(n)" in cypher:
            self.count_calls += 1
            return [[sum(1 for n in self._nodes if n.get("label") in labels)]]
        self.build_calls += 1
        return [[n] for n in self._nodes if n.get("label") in labels]

    @staticmethod
    def _node_dict(raw: dict[str, Any]) -> dict[str, Any]:
        return dict(raw)

    def get_node(self, node_id: str) -> dict[str, Any] | None:
        for n in self._nodes:
            if n.get("id") == node_id:
                return dict(n)
        return None


@pytest.fixture(autouse=True)
def _clear_alias_cache() -> Any:
    mr._ALIAS_INDEX.clear()
    yield
    mr._ALIAS_INDEX.clear()


def test_cached_index_matches_fresh_build() -> None:
    """The memoized index resolves identically to an uncached build_from_store."""
    store = FakeStore(_NODES)
    fresh = AliasIndex.build_from_store(store)
    cached = _alias_index(store)
    assert len(cached) == len(fresh)
    for surface in ("AA2024", "дюраль", "Titanium", "титан", "unknown"):
        assert cached.lookup_exact(surface) == fresh.lookup_exact(surface)
    assert cached.lookup_exact("AA2024") == "mat:1"


def test_second_call_reuses_cache_without_rebuild() -> None:
    """A repeat over an unchanged graph returns the same object and does not rebuild."""
    store = FakeStore(_NODES)
    first = _alias_index(store)
    builds_after_first = store.build_calls
    assert builds_after_first == 1  # built once

    second = _alias_index(store)
    assert second is first  # same cached object reused
    assert store.build_calls == builds_after_first  # no second scan/rebuild
    assert store.count_calls == 2  # cheap signature checked on each call


def test_index_rebuilds_when_entity_count_changes() -> None:
    """Ingestion (new entity → new count) invalidates the cache and rebuilds."""
    store = FakeStore(_NODES)
    first = _alias_index(store)
    assert first.lookup_exact("Steel") is None

    store._nodes.append(
        {"id": "mat:3", "label": "Material", "name": "Steel", "aliases_text": "сталь"}
    )
    second = _alias_index(store)
    assert second is not first
    assert second.lookup_exact("Steel") == "mat:3"
    assert store.build_calls == 2  # exactly one rebuild after the count changed


def test_falls_back_to_uncached_build_when_count_unavailable() -> None:
    """If the count signature query raises, resolve still works and nothing is cached."""

    class RaisingCountStore(FakeStore):
        def rows(self, cypher: str, params: dict[str, Any] | None = None) -> list[list[Any]]:
            if "count(n)" in cypher:
                raise RuntimeError("store cannot count")
            return super().rows(cypher, params)

    store = RaisingCountStore(_NODES)
    idx = _alias_index(store)
    assert idx.lookup_exact("AA2024") == "mat:1"  # behavior preserved
    assert str(store.db_path) not in mr._ALIAS_INDEX  # not cached on the fallback path
