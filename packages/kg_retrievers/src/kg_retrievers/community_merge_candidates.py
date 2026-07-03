"""Over-partition merge recommendation via edge coupling (§11.6).

Flags community *pairs* that are more tightly coupled to each other than to
their own interiors — the classic symptom of an over-partitioned clustering.
For each unordered pair of communities we count the edges that cross between
them (``cross_edges``) and each side's internal edge count, then score the
coupling as ``cross / (cross + internal_a + internal_b)``. A high coupling
means the boundary between the two communities carries more structure than
the communities themselves, so merging them is likely warranted.

This is genuinely distinct from ``community_similarity.py`` (§11.16), which
compares disjoint member *sets* by Jaccard — always ``0`` for a partition —
and never looks at edges. Here the signal lives entirely in the edges.

Pure in-memory computation over an edge iterable and a membership map; it does
not touch the Kuzu store.

Рекомендация к слиянию сообществ при переразбиении по связности рёбер (§11.6).
Помечает пары сообществ, у которых межгрупповых рёбер больше, чем внутренних:
coupling = cross / (cross + internal_a + internal_b). Чистая функция, без
обращения к хранилищу.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class MergeCandidate:
    """A community pair recommended for merging by edge coupling (§11.6).

    - ``community_a`` / ``community_b`` — the two community ids, with
      ``community_a < community_b`` for a stable, order-free identity;
    - ``cross_edges`` — number of edges running between the two communities;
    - ``internal_a`` / ``internal_b`` — internal edge counts of each side;
    - ``coupling`` — ``cross_edges / (cross_edges + internal_a + internal_b)``,
      in ``[0, 1]``; higher means the pair is more tightly bound to each other
      than internally (a merge signal).
    """

    community_a: int
    community_b: int
    cross_edges: int
    internal_a: int
    internal_b: int
    coupling: float

    def as_dict(self) -> dict:
        return {
            "community_a": self.community_a,
            "community_b": self.community_b,
            "cross_edges": self.cross_edges,
            "internal_a": self.internal_a,
            "internal_b": self.internal_b,
            "coupling": self.coupling,
        }


def merge_candidates(
    edges: Iterable[tuple[str, str]],
    membership: Mapping[str, int],
    *,
    min_cross: int = 1,
    min_coupling: float = 0.5,
) -> list[MergeCandidate]:
    """Recommend community pairs to merge from inter-community edges (§11.6).

    ``edges`` is an iterable of ``(u, v)`` node-id pairs; ``membership`` maps
    node id → community id. Edges touching a node absent from ``membership``,
    and self-loops, are ignored. For every unordered pair of *distinct*
    communities we tally cross edges plus each side's internal edges, then keep
    the pair when ``cross_edges >= min_cross`` and ``coupling >= min_coupling``.

    Returns candidates with ``community_a < community_b``, sorted by ``coupling``
    descending and then by ``(community_a, community_b)`` ascending for a stable
    order. Direction of each ``(u, v)`` is irrelevant — the graph is treated as
    undirected.
    """
    internal: dict[int, int] = {}
    cross: dict[tuple[int, int], int] = {}

    for u, v in edges:
        cu = membership.get(u)
        cv = membership.get(v)
        if cu is None or cv is None:
            continue
        if cu == cv:
            internal[cu] = internal.get(cu, 0) + 1
        else:
            key = (cu, cv) if cu < cv else (cv, cu)
            cross[key] = cross.get(key, 0) + 1

    candidates: list[MergeCandidate] = []
    for (a, b), cross_edges in cross.items():
        if cross_edges < min_cross:
            continue
        internal_a = internal.get(a, 0)
        internal_b = internal.get(b, 0)
        denom = cross_edges + internal_a + internal_b
        coupling = cross_edges / denom if denom else 0.0
        if coupling < min_coupling:
            continue
        candidates.append(
            MergeCandidate(
                community_a=a,
                community_b=b,
                cross_edges=cross_edges,
                internal_a=internal_a,
                internal_b=internal_b,
                coupling=coupling,
            )
        )

    candidates.sort(key=lambda c: (-c.coupling, c.community_a, c.community_b))
    return candidates
