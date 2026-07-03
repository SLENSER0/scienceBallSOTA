"""Asset dependency graph + topological order — граф зависимостей ассетов (§9.4).

Pure-python re-implementation of the *software-defined asset* dependency graph
that orchestrators such as Dagster expose, **without taking a dependency on
Dagster** (§9.4). Each :class:`Asset` names an output («ассет») and the keys of
the assets it consumes as ``deps``. The :class:`AssetGraph` then answers the
questions a scheduler needs before a run:

* :meth:`AssetGraph.topo_order`   — a deterministic build order where every
  dependency precedes its dependents; a cycle raises :class:`CycleError`.
* :meth:`AssetGraph.upstream_of`  — transitive dependencies of a key.
* :meth:`AssetGraph.downstream_of` — transitive dependents of a key.
* :meth:`AssetGraph.roots`        — assets with no upstream assets («истоки»).
* :meth:`AssetGraph.leaves`       — assets nobody depends on («листья»).

Everything here is deterministic and side-effect free:

* Ties in the topological order are broken by sorting keys, so the order is a
  pure function of the graph — no ``random`` and no insertion-order leakage
  (§9.4 «детерминизм»).
* ``deps`` pointing at keys that were never registered are treated as *external*
  inputs (e.g. a raw source) and simply ignored by the graph algorithms; only
  edges between registered assets participate.

Public API:

* :class:`Asset`      — frozen ``(key, deps)`` record with :meth:`Asset.as_dict`.
* :class:`AssetGraph` — mutable builder + read-only queries listed above.
* :class:`CycleError` — raised by :meth:`AssetGraph.topo_order` on a cycle.
"""

from __future__ import annotations

import heapq
from collections.abc import Iterable
from dataclasses import dataclass

__all__ = [
    "Asset",
    "AssetGraph",
    "CycleError",
]


class CycleError(Exception):
    """Raised when the asset graph contains a cycle — граф содержит цикл (§9.4).

    A cycle means no topological order exists; :attr:`nodes` holds the keys that
    could not be ordered (i.e. those still tangled in the cycle) for diagnostics.
    """

    def __init__(self, nodes: Iterable[str]) -> None:
        self.nodes: tuple[str, ...] = tuple(sorted(nodes))
        joined = ", ".join(self.nodes)
        super().__init__(f"asset graph contains a cycle involving: {joined}")


def _dedup(keys: Iterable[str]) -> tuple[str, ...]:
    """Order-preserving de-duplication — уникальные ключи в порядке появления (§9.4)."""
    seen: set[str] = set()
    out: list[str] = []
    for key in keys:
        if key not in seen:
            seen.add(key)
            out.append(key)
    return tuple(out)


@dataclass(frozen=True, slots=True)
class Asset:
    """Immutable asset node — узел ассета с его зависимостями (§9.4).

    ``key`` uniquely names the asset; ``deps`` are the keys of the assets it
    consumes, de-duplicated in first-seen order. The record is a plain frozen
    value so it can be hashed, compared and serialized.
    """

    key: str
    deps: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, object]:
        """JSON-friendly view — таблица «ключ + список зависимостей» (§9.4)."""
        return {"key": self.key, "deps": list(self.deps)}


class AssetGraph:
    """Dependency graph over :class:`Asset` nodes — граф зависимостей (§9.4).

    Assets are registered with :meth:`add_asset`; a ``dep`` naming a key that is
    never registered is treated as an *external* input and ignored by every graph
    algorithm (only edges between registered assets count). All query methods are
    deterministic: results are returned in sorted order and ties in the
    topological order are broken by key.
    """

    def __init__(self) -> None:
        # Insertion-ordered registry of assets keyed by asset key.
        self._assets: dict[str, Asset] = {}

    def add_asset(self, key: str, deps: Iterable[str] = ()) -> Asset:
        """Register an asset and its dependencies — добавить ассет (§9.4).

        ``deps`` are de-duplicated in first-seen order. Registering the same
        ``key`` twice is a programming error and raises :class:`ValueError`.
        """
        if key in self._assets:
            raise ValueError(f"asset already registered: {key!r}")
        asset = Asset(key=key, deps=_dedup(deps))
        self._assets[key] = asset
        return asset

    def __contains__(self, key: object) -> bool:
        return key in self._assets

    def __len__(self) -> int:
        return len(self._assets)

    def get_asset(self, key: str) -> Asset | None:
        """Return the registered :class:`Asset` for ``key`` or ``None`` (§9.4)."""
        return self._assets.get(key)

    def _upstream(self, key: str) -> tuple[str, ...]:
        """Direct, *registered* dependencies of ``key`` — прямые зависимости (§9.4)."""
        asset = self._assets.get(key)
        if asset is None:
            return ()
        return tuple(d for d in asset.deps if d in self._assets)

    def _dependents(self) -> dict[str, list[str]]:
        """Map each key to the keys that directly depend on it — прямые потомки (§9.4)."""
        dependents: dict[str, list[str]] = {k: [] for k in self._assets}
        for key in self._assets:
            for dep in self._upstream(key):
                dependents[dep].append(key)
        return dependents

    def topo_order(self) -> list[str]:
        """Deterministic topological order — топологический порядок сборки (§9.4).

        Every registered dependency precedes each asset that consumes it. Ties
        (assets whose dependencies are already satisfied) are emitted in sorted
        key order, so the result is a pure function of the graph. Raises
        :class:`CycleError` if the graph contains a cycle.
        """
        indegree: dict[str, int] = {k: len(self._upstream(k)) for k in self._assets}
        dependents = self._dependents()
        ready: list[str] = [k for k, d in indegree.items() if d == 0]
        heapq.heapify(ready)
        order: list[str] = []
        while ready:
            node = heapq.heappop(ready)
            order.append(node)
            for child in sorted(dependents[node]):
                indegree[child] -= 1
                if indegree[child] == 0:
                    heapq.heappush(ready, child)
        if len(order) != len(self._assets):
            unresolved = [k for k, d in indegree.items() if d > 0]
            raise CycleError(unresolved)
        return order

    def _reachable(self, key: str, adjacency: dict[str, tuple[str, ...]]) -> list[str]:
        """Transitive closure from ``key`` over ``adjacency`` (excludes self) (§9.4)."""
        if key not in self._assets:
            return []
        seen: set[str] = set()
        stack: list[str] = list(adjacency.get(key, ()))
        while stack:
            node = stack.pop()
            if node in seen:
                continue
            seen.add(node)
            stack.extend(adjacency.get(node, ()))
        seen.discard(key)
        return sorted(seen)

    def upstream_of(self, key: str) -> list[str]:
        """Transitive dependencies of ``key`` — все предки (§9.4).

        Sorted, excludes ``key`` itself. An unknown key yields ``[]``.
        """
        adjacency = {k: self._upstream(k) for k in self._assets}
        return self._reachable(key, adjacency)

    def downstream_of(self, key: str) -> list[str]:
        """Transitive dependents of ``key`` — все потомки (§9.4).

        Sorted, excludes ``key`` itself. An unknown key yields ``[]``.
        """
        dependents = self._dependents()
        adjacency = {k: tuple(v) for k, v in dependents.items()}
        return self._reachable(key, adjacency)

    def roots(self) -> list[str]:
        """Assets with no upstream assets — истоки графа (§9.4, sorted)."""
        return sorted(k for k in self._assets if not self._upstream(k))

    def leaves(self) -> list[str]:
        """Assets nobody depends on — листья графа (§9.4, sorted)."""
        dependents = self._dependents()
        return sorted(k for k in self._assets if not dependents[k])
