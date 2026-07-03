"""§15.4 / §15 — HalluMat contradiction-graph community grouping.

Мы группируем взаимно-противоречащие утверждения (claims) в «сообщества» и
оцениваем потенциал галлюцинации через плотность противоречий. Мы строим граф,
где узлы — id утверждений, рёбра — пары противоречий, а кластеры — компоненты
связности (Louvain-lite / union-find), объединяющие транзитивно противоречащие
утверждения. Затем считаем PHCS — Potential-Hallucination-Contradiction-Score.

We group mutually-contradicting claims into communities and score potential
hallucination by contradiction density: nodes are claim ids, edges are
contradiction pairs, and clusters are the connected components (a Louvain-lite
grouping via pure-python union-find) that merge transitively-contradicting
claims. ``phcs`` = contradicted_claims / total_claims.

Paper: HalluMat / HalluMatDetector — "HalluMat: Detecting Hallucinations in
Materials-Science LLM Outputs via Contradiction Graphs" (arXiv:2512.22396).
The contradiction-graph community grouping and the Potential-Hallucination
Contradiction Score (PHCS) follow §15.4 / §15 of that work.

Pure python: no store I/O here — callers pass already-extracted contradiction
pairs, so the grouping is deterministic and hand-checkable in tests.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

# Тип пары противоречия / a contradiction pair: (claim_a_id, claim_b_id).
ClaimPair = tuple[str, str]

__all__ = ["ClaimPair", "ContradictionGraph", "build_contradiction_graph", "phcs"]


class _UnionFind:
    """Disjoint-set forest with path compression and union by size (pure python)."""

    def __init__(self) -> None:
        self._parent: dict[str, str] = {}
        self._size: dict[str, int] = {}

    def add(self, item: str) -> None:
        if item not in self._parent:
            self._parent[item] = item
            self._size[item] = 1

    def find(self, item: str) -> str:
        root = item
        while self._parent[root] != root:
            root = self._parent[root]
        # path compression / сжатие путей
        while self._parent[item] != root:
            self._parent[item], item = root, self._parent[item]
        return root

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        if self._size[ra] < self._size[rb]:
            ra, rb = rb, ra
        self._parent[rb] = ra
        self._size[ra] += self._size[rb]

    def groups(self) -> list[list[str]]:
        clusters: dict[str, list[str]] = {}
        for item in self._parent:
            clusters.setdefault(self.find(item), []).append(item)
        return list(clusters.values())


def _distinct_claims(pairs: Sequence[ClaimPair]) -> set[str]:
    """Все id утверждений, участвующие хотя бы в одной паре противоречий."""
    claims: set[str] = set()
    for a, b in pairs:
        claims.add(a)
        claims.add(b)
    return claims


@dataclass(frozen=True)
class ContradictionGraph:
    """§15.4 — контр-граф / contradiction graph of mutually-contradicting claims.

    ``nodes`` — отсортированные уникальные id утверждений / sorted unique claim ids.
    ``edges`` — нормализованные (отсортированные внутри пары) уникальные рёбра
    противоречий / normalized, de-duplicated contradiction pairs.
    ``clusters`` — компоненты связности; каждый кластер отсортирован, кластеры
    упорядочены детерминированно / connected components, each sorted, ordered
    deterministically. Взаимно-противоречащие утверждения попадают в один кластер.
    """

    nodes: tuple[str, ...]
    edges: tuple[ClaimPair, ...]
    clusters: tuple[tuple[str, ...], ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "nodes": list(self.nodes),
            "edges": [list(e) for e in self.edges],
            "clusters": [list(c) for c in self.clusters],
        }


def build_contradiction_graph(pairs: Sequence[ClaimPair]) -> ContradictionGraph:
    """Построить контр-граф и сгруппировать противоречия в кластеры (§15.4).

    Каждая пара ``(a, b)`` — взаимное противоречие двух утверждений. Узлы —
    все встречающиеся id; рёбра нормализуются (``tuple(sorted(pair))``) и
    дедуплицируются; кластеры — компоненты связности через union-find, так что
    транзитивно противоречащие утверждения (a↔b, b↔c) сливаются в один кластер.

    Self-loops ``(a, a)`` дают одиночный узел ``a`` без ребра (утверждение не
    образует пары само с собой). Пустой вход -> пустой граф.
    """
    uf = _UnionFind()
    seen_edges: set[ClaimPair] = set()
    edges: list[ClaimPair] = []
    for a, b in pairs:
        uf.add(a)
        uf.add(b)
        if a == b:
            continue  # self-loop: узел есть, ребра нет
        edge: ClaimPair = (a, b) if a <= b else (b, a)
        if edge not in seen_edges:
            seen_edges.add(edge)
            edges.append(edge)
        uf.union(a, b)

    groups = uf.groups()
    nodes = tuple(sorted(item for group in groups for item in group))
    sorted_edges = tuple(sorted(edges))
    clusters = tuple(sorted(tuple(sorted(g)) for g in groups))
    return ContradictionGraph(nodes=nodes, edges=sorted_edges, clusters=clusters)


def phcs(pairs: Sequence[ClaimPair], n_claims: int) -> float:
    """Potential-Hallucination-Contradiction-Score (§15) = contradicted / total.

    ``contradicted`` — число различных утверждений, участвующих хотя бы в одном
    противоречии; ``total`` — общее число утверждений ``n_claims``. Возвращает
    долю в ``[0, 1]``: чем выше, тем больше «взаимо-противоречивость» и риск
    галлюцинации. ``0.0`` при отсутствии противоречий или при ``n_claims <= 0``.

    ``n_claims`` — полный размер множества утверждений (>= числа противоречащих),
    поэтому результат не превышает ``1.0``.
    """
    if n_claims <= 0:
        return 0.0
    contradicted = len(_distinct_claims(pairs))
    return contradicted / n_claims
