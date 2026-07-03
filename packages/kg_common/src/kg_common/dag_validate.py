"""Asset DAG validation — валидация графа зависимостей ассетов (§9.4).

A thin *validation* layer over :mod:`kg_common.asset_graph`. Where
:class:`~kg_common.asset_graph.AssetGraph` answers scheduling questions
(topological order, upstream/downstream), :func:`validate_dag` answers a single
gate question a scheduler asks *before* a run: **is this set of assets a usable
DAG?** It bundles the three failure modes plus the two structural anchors into
one frozen, JSON-serialisable verdict:

* ``ok``          — ``True`` iff there are no cycles and no missing deps.
* ``cycles``      — sorted keys still tangled in a cycle («циклы»), or ``[]``.
* ``missing_deps`` — sorted ``dep`` keys referenced but never registered
  («висячие зависимости»); the graph itself treats these as external inputs
  and ignores them, so we surface them explicitly here.
* ``roots``       — assets with no (registered) upstream — истоки.
* ``leaves``      — assets nobody depends on — листья.

This module only *reads* :mod:`kg_common.asset_graph`; it re-uses
:class:`~kg_common.asset_graph.AssetGraph` and
:class:`~kg_common.asset_graph.CycleError` without modifying them. Everything is
deterministic and side-effect free: all list fields are sorted.

Public API:

* :class:`DagValidation` — frozen verdict with :meth:`DagValidation.as_dict`.
* :func:`validate_dag`   — build a graph from assets and return the verdict.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from kg_common.asset_graph import Asset, AssetGraph, CycleError

__all__ = [
    "DagValidation",
    "validate_dag",
]


@dataclass(frozen=True, slots=True)
class DagValidation:
    """Immutable DAG verdict — результат проверки графа (§9.4).

    ``ok`` is ``True`` exactly when both ``cycles`` and ``missing_deps`` are
    empty. All list fields are sorted so the record is a pure function of the
    input asset set.
    """

    ok: bool
    cycles: tuple[str, ...]
    missing_deps: tuple[str, ...]
    roots: tuple[str, ...]
    leaves: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        """JSON-friendly view — сводка проверки как словарь (§9.4)."""
        return {
            "ok": self.ok,
            "cycles": list(self.cycles),
            "missing_deps": list(self.missing_deps),
            "roots": list(self.roots),
            "leaves": list(self.leaves),
        }


def validate_dag(assets: Iterable[Asset]) -> DagValidation:
    """Validate an asset DAG — проверить граф ассетов (§9.4).

    Builds an :class:`~kg_common.asset_graph.AssetGraph` from ``assets`` and
    reports cycles, dangling (missing) dependencies, roots and leaves. Assets
    are registered in iteration order; a duplicate ``key`` propagates the
    :class:`ValueError` raised by
    :meth:`~kg_common.asset_graph.AssetGraph.add_asset`.
    """
    graph = AssetGraph()
    registered: set[str] = set()
    missing: set[str] = set()
    for asset in assets:
        graph.add_asset(asset.key, asset.deps)
        registered.add(asset.key)
    # A dep pointing at a key that was never registered is a dangling edge.
    for asset in (graph.get_asset(k) for k in registered):
        if asset is None:  # pragma: no cover - registered keys always resolve
            continue
        for dep in asset.deps:
            if dep not in registered:
                missing.add(dep)

    cycles: tuple[str, ...] = ()
    try:
        graph.topo_order()
    except CycleError as exc:
        cycles = exc.nodes

    ok = not cycles and not missing
    return DagValidation(
        ok=ok,
        cycles=cycles,
        missing_deps=tuple(sorted(missing)),
        roots=tuple(graph.roots()),
        leaves=tuple(graph.leaves()),
    )
