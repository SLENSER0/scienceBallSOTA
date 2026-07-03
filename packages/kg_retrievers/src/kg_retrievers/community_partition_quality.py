"""Partition-quality metrics — true edge-based modularity/conductance (§11.13).

Pure in-memory quality of a community partition over an *undirected simple*
graph. This is the real edge metric that :mod:`kg_retrievers.community_metrics`
explicitly punts on ("needs the graph's edges"): that module only has a
size-Herfindahl ``modularity_proxy``. Here we consume the actual edge list.

Метрики качества разбиения на сообщества по рёбрам графа: модулярность,
покрытие (доля внутренних рёбер) и проводимость (conductance) каждого сообщества.

The graph is collapsed to undirected simple form before counting: self-loops are
dropped and parallel/reversed duplicates are merged, so each unordered pair of
distinct nodes contributes at most one edge.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass


def _simple_edges(edges: Iterable[tuple[str, str]]) -> set[frozenset[str]]:
    """Collapse an edge iterable to undirected simple edges (no self-loops).

    Схлопывание рёбер: убираем петли и параллельные/обратные дубликаты.
    """
    simple: set[frozenset[str]] = set()
    for u, v in edges:
        if u == v:
            continue
        simple.add(frozenset((u, v)))
    return simple


def _degrees(simple: set[frozenset[str]]) -> dict[str, int]:
    """Undirected degree of every incident node on the simple graph."""
    deg: dict[str, int] = defaultdict(int)
    for edge in simple:
        for node in edge:
            deg[node] += 1
    return dict(deg)


def modularity(edges: Iterable[tuple[str, str]], membership: Mapping[str, int]) -> float:
    """Newman modularity ``Q = Σ_c[L_c/m - (deg_c/2m)²]`` (undirected simple).

    ``L_c`` — number of intra-community edges of community ``c``; ``deg_c`` — sum
    of node degrees in ``c``; ``m`` — total edges. Returns ``0.0`` for no edges.
    """
    simple = _simple_edges(edges)
    m = len(simple)
    if m == 0:
        return 0.0
    two_m = 2 * m
    intra: dict[int, int] = defaultdict(int)
    deg_c: dict[int, int] = defaultdict(int)
    for edge in simple:
        u, v = tuple(edge)
        cu = membership.get(u)
        cv = membership.get(v)
        if cu is not None:
            deg_c[cu] += 1
        if cv is not None:
            deg_c[cv] += 1
        if cu is not None and cu == cv:
            intra[cu] += 1
    communities = set(intra) | set(deg_c)
    return sum(intra.get(c, 0) / m - (deg_c.get(c, 0) / two_m) ** 2 for c in communities)


def coverage(edges: Iterable[tuple[str, str]], membership: Mapping[str, int]) -> float:
    """Coverage = intra-community edges / total edges (``0.0`` for no edges).

    Покрытие: доля рёбер, оба конца которых лежат в одном сообществе.
    """
    simple = _simple_edges(edges)
    m = len(simple)
    if m == 0:
        return 0.0
    intra = 0
    for edge in simple:
        u, v = tuple(edge)
        cu = membership.get(u)
        cv = membership.get(v)
        if cu is not None and cu == cv:
            intra += 1
    return intra / m


def community_conductance(
    edges: Iterable[tuple[str, str]], membership: Mapping[str, int]
) -> dict[int, float]:
    """Per-community conductance ``cut_c / min(vol_c, vol_notc)``.

    ``cut_c`` — edges with exactly one endpoint in ``c``; ``vol_c`` — sum of
    degrees of ``c``'s nodes; ``vol_notc`` — total volume minus ``vol_c``. When
    ``min(vol_c, vol_notc)`` is ``0`` the conductance is defined as ``0.0``.

    Проводимость сообщества: доля исходящих рёбер относительно объёма.
    """
    simple = _simple_edges(edges)
    deg = _degrees(simple)
    total_vol = sum(deg.values())
    communities = {membership[n] for n in deg if n in membership}
    cut: dict[int, int] = defaultdict(int)
    vol: dict[int, int] = defaultdict(int)
    for node, d in deg.items():
        c = membership.get(node)
        if c is not None:
            vol[c] += d
    for edge in simple:
        u, v = tuple(edge)
        cu = membership.get(u)
        cv = membership.get(v)
        if cu is not None and cv is not None and cu != cv:
            cut[cu] += 1
            cut[cv] += 1
    out: dict[int, float] = {}
    for c in communities:
        vol_c = vol.get(c, 0)
        vol_not = total_vol - vol_c
        denom = min(vol_c, vol_not)
        out[c] = cut.get(c, 0) / denom if denom else 0.0
    return out


@dataclass(frozen=True)
class PartitionQuality:
    """Edge-based quality of a community partition (§11.13).

    - ``n_communities`` — number of distinct communities with incident edges;
    - ``modularity`` — Newman ``Q`` (higher is better, in ``[-0.5, 1)``);
    - ``coverage`` — fraction of edges that are intra-community;
    - ``avg_conductance`` — mean per-community conductance (``0.0`` when empty);
    - ``per_community_conductance`` — community id → conductance.
    """

    n_communities: int
    modularity: float
    coverage: float
    avg_conductance: float
    per_community_conductance: dict[int, float]

    def as_dict(self) -> dict:
        return {
            "n_communities": self.n_communities,
            "modularity": self.modularity,
            "coverage": self.coverage,
            "avg_conductance": self.avg_conductance,
            "per_community_conductance": dict(self.per_community_conductance),
        }


def evaluate_partition(
    edges: Iterable[tuple[str, str]], membership: Mapping[str, int]
) -> PartitionQuality:
    """Compute all edge-based partition metrics in one pass-friendly bundle.

    Считает модулярность, покрытие и проводимость и упаковывает в dataclass.
    """
    simple = _simple_edges(edges)
    per_cond = community_conductance(simple, membership)
    avg_cond = sum(per_cond.values()) / len(per_cond) if per_cond else 0.0
    return PartitionQuality(
        n_communities=len(per_cond),
        modularity=modularity(simple, membership),
        coverage=coverage(simple, membership),
        avg_conductance=avg_cond,
        per_community_conductance=per_cond,
    )
