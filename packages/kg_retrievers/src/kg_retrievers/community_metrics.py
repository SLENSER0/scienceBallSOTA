"""Community metrics over the Kuzu graph store (§11.13).

Structural summary of the ``community_id`` partition written by
:mod:`kg_retrievers.community`: how many communities exist, their per-community
sizes, the largest one, the count of singletons, and a size-concentration
*modularity proxy*.

Метрики сообществ: сколько кластеров, их размеры, крупнейший, одиночки и
прокси модулярности по распределению размеров кластеров.

Strictly read-only. ``community_id`` is a real, typed Kuzu column (``INT64``),
so it is returned directly. The ``Finding`` community-summary nodes also carry a
``community_id`` but are *summaries*, not members, so they are excluded from the
counts — matching :mod:`kg_retrievers.community_labels`.
"""

from __future__ import annotations

from dataclasses import dataclass

from kg_common import get_logger
from kg_retrievers.graph_store import KuzuGraphStore
from kg_schema.labels import NodeLabel

_log = get_logger("community_metrics")

# Summary nodes carry a community_id but are not members — exclude them (§11.13).
_FINDING: str = str(NodeLabel.FINDING)


@dataclass(frozen=True)
class CommunityMetrics:
    """Structural metrics of a ``community_id`` partition (§11.13).

    - ``n_communities`` — number of distinct community ids present;
    - ``sizes`` — community id → member count (entity nodes only), ordered by id;
    - ``modularity_proxy`` — Σ(nᵢ/N)² Herfindahl concentration of the size
      distribution: ``1.0`` when one community holds every node, ``→ 1/k`` for
      ``k`` equal communities, ``0.0`` when empty. A partition-only stand-in for
      edge-based modularity (which needs the graph's edges);
    - ``largest`` — member count of the biggest community (``0`` when empty);
    - ``singletons`` — number of communities of size exactly one.
    """

    n_communities: int
    sizes: dict[int, int]
    modularity_proxy: float
    largest: int
    singletons: int

    @classmethod
    def from_counts(cls, counts: dict[int, int]) -> CommunityMetrics:
        """Build metrics from a ``community_id → member count`` mapping."""
        sizes = {cid: counts[cid] for cid in sorted(counts)}
        total = sum(sizes.values())
        proxy = sum((n / total) ** 2 for n in sizes.values()) if total else 0.0
        return cls(
            n_communities=len(sizes),
            sizes=sizes,
            modularity_proxy=proxy,
            largest=max(sizes.values(), default=0),
            singletons=sum(1 for n in sizes.values() if n == 1),
        )

    def as_dict(self) -> dict:
        return {
            "n_communities": self.n_communities,
            "sizes": dict(self.sizes),
            "modularity_proxy": self.modularity_proxy,
            "largest": self.largest,
            "singletons": self.singletons,
        }


def community_metrics(store: KuzuGraphStore) -> CommunityMetrics:
    """Compute :class:`CommunityMetrics` from ``community_id`` on member nodes.

    Counts every non-``Finding`` node that carries a ``community_id``, grouping
    by that id. An empty store (or one with no assignments) yields all-zeros.
    """
    rows = store.rows(
        "MATCH (n:Node) WHERE n.community_id IS NOT NULL AND n.label <> $f RETURN n.community_id",
        {"f": _FINDING},
    )
    counts: dict[int, int] = {}
    for row in rows:
        cid = row[0]
        counts[cid] = counts.get(cid, 0) + 1
    metrics = CommunityMetrics.from_counts(counts)
    _log.info(
        "community.metrics",
        n_communities=metrics.n_communities,
        largest=metrics.largest,
        singletons=metrics.singletons,
    )
    return metrics
