"""Node degree distribution and hub detection over a KuzuGraphStore (§8.13).

Computes the total (in + out) degree of every ``Node`` and summarises the
distribution: the maximum and mean degree, a degree → count histogram and the
top-``k`` highest-degree hubs. Isolated nodes (no incident edge) are taken from
the full id set and contribute a degree of ``0``.

Распределение степеней узлов и выявление хабов: суммарная (входящая +
исходящая) степень каждого узла, гистограмма степеней и топ-``k`` хабов.

Degrees are derived from the queryable base columns ``a.id`` / ``b.id`` of the
``Rel`` table (``MATCH (a:Node)-[r:Rel]->(b:Node)``); the full node id set comes
from ``MATCH (n:Node) RETURN n.id``. Custom node props are not Kuzu columns and
are never touched here. An empty store yields ``max_degree 0``, ``mean_degree
0.0`` and an empty histogram.
"""

from __future__ import annotations

from dataclasses import dataclass

from kg_common import get_logger
from kg_retrievers.graph_store import KuzuGraphStore

_log = get_logger("degree_distribution")


@dataclass(frozen=True)
class DegreeEntry:
    """A single node and its total (in + out) degree (§8.13)."""

    node_id: str
    degree: int

    def as_dict(self) -> dict:
        return {"node_id": self.node_id, "degree": self.degree}


@dataclass(frozen=True)
class DegreeDistribution:
    """Summary of the node degree distribution of a graph store (§8.13).

    - ``n_nodes`` — total number of ``Node`` rows (including isolated ones);
    - ``max_degree`` — the largest total degree; ``0`` for an empty store;
    - ``mean_degree`` — mean total degree ``2·E / N``; ``0.0`` when ``N == 0``;
    - ``histogram`` — degree → number of nodes with exactly that degree;
    - ``top_hubs`` — the ``top_k`` highest-degree nodes, sorted by degree
      descending then ``node_id`` ascending.
    """

    n_nodes: int
    max_degree: int
    mean_degree: float
    histogram: dict[int, int]
    top_hubs: tuple[DegreeEntry, ...]

    def as_dict(self) -> dict:
        return {
            "n_nodes": self.n_nodes,
            "max_degree": self.max_degree,
            "mean_degree": self.mean_degree,
            "histogram": {int(k): v for k, v in self.histogram.items()},
            "top_hubs": [h.as_dict() for h in self.top_hubs],
        }


def _degrees(store: KuzuGraphStore) -> dict[str, int]:
    """Total (in + out) degree per node id; isolated nodes get ``0`` (§8.13).

    Reads only base columns: every directed ``Rel`` edge adds ``+1`` to the
    source (out) and ``+1`` to the target (in); the full id set seeds isolated
    nodes at ``0``.
    """
    degrees: dict[str, int] = {r[0]: 0 for r in store.rows("MATCH (n:Node) RETURN n.id")}
    for src, dst in store.rows("MATCH (a:Node)-[r:Rel]->(b:Node) RETURN a.id, b.id"):
        degrees[src] = degrees.get(src, 0) + 1
        degrees[dst] = degrees.get(dst, 0) + 1
    return degrees


def degree_distribution(store: KuzuGraphStore, *, top_k: int = 10) -> DegreeDistribution:
    """Compute the :class:`DegreeDistribution` over ``store`` (§8.13).

    Isolated nodes are counted with degree ``0``. ``top_hubs`` is limited to
    ``top_k`` entries, sorted by degree descending then ``node_id`` ascending.
    An empty store gives ``max_degree 0``, ``mean_degree 0.0`` and an empty
    histogram.
    """
    degrees = _degrees(store)
    n_nodes = len(degrees)

    histogram: dict[int, int] = {}
    for deg in degrees.values():
        histogram[deg] = histogram.get(deg, 0) + 1

    max_degree = max(degrees.values(), default=0)
    total_degree = sum(degrees.values())
    mean_degree = (total_degree / n_nodes) if n_nodes else 0.0

    ranked = sorted(degrees.items(), key=lambda kv: (-kv[1], kv[0]))
    top_hubs = tuple(DegreeEntry(node_id=nid, degree=deg) for nid, deg in ranked[:top_k])

    dist = DegreeDistribution(
        n_nodes=n_nodes,
        max_degree=max_degree,
        mean_degree=mean_degree,
        histogram=histogram,
        top_hubs=top_hubs,
    )
    _log.info(
        "degree.distribution",
        n_nodes=n_nodes,
        max_degree=max_degree,
        mean_degree=mean_degree,
        n_hubs=len(top_hubs),
    )
    return dist
