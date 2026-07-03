"""Eccentricity, radius & diameter analytics over the entity graph (§8.13).

Эксцентриситет, радиус и диаметр / eccentricity, radius & diameter — classic
distance metrics on an undirected graph:

- эксцентриситет узла / a node's eccentricity is the greatest shortest-path
  distance from it to any other node;
- радиус / radius is the minimum eccentricity over all nodes;
- диаметр / diameter is the maximum eccentricity over all nodes;
- центр / center — nodes whose eccentricity equals the radius;
- периферия / periphery — nodes whose eccentricity equals the diameter.

This module reads a :class:`KuzuGraphStore` (never writes). It projects the
``:Entity`` subgraph into an undirected NetworkX graph (the same projection used
by community detection, §11, and GDS-lite, §12.8), then computes the metrics over
the **largest connected component** — NetworkX requires a connected graph for
``radius``/``diameter``, so on a disconnected graph we restrict to the biggest
component. An empty graph yields empty/zero metrics.

Kuzu note: custom node props are not queryable columns, so we RETURN only the
base ``id`` columns here; anything else would be read via ``store.get_node``.
"""

from __future__ import annotations

from dataclasses import dataclass

import networkx as nx

from kg_retrievers.graph_store import KuzuGraphStore
from kg_schema.labels import ENTITY_LABELS

# Same projection as community detection (§11): undirected entity–entity edges,
# self-loops dropped downstream.
_PROJECTION = (
    "MATCH (a:Node)-[:Rel]-(b:Node) WHERE a.label IN $l AND b.label IN $l RETURN a.id, b.id"
)


@dataclass(frozen=True)
class EccentricityReport:
    """Eccentricity, radius & diameter of the largest component (§8.13).

    ``eccentricity`` — id→эксцентриситет / id→eccentricity over the largest
    connected component; ``radius`` / ``diameter`` — its min / max eccentricity;
    ``center`` / ``periphery`` — отсортированные id / sorted node ids at the
    radius / diameter respectively. Empty graph → ``{}``, ``0``, ``0``, ``()``.
    """

    eccentricity: dict[str, int]
    radius: int
    diameter: int
    center: tuple[str, ...]
    periphery: tuple[str, ...]

    def as_dict(self) -> dict:
        return {
            "eccentricity": dict(self.eccentricity),
            "radius": self.radius,
            "diameter": self.diameter,
            "center": list(self.center),
            "periphery": list(self.periphery),
        }


def _project(store: KuzuGraphStore) -> nx.Graph:
    """Project the ``:Entity`` subgraph into an undirected NetworkX graph (§8.13).

    Self-loops are dropped; only nodes on at least one entity–entity edge appear.
    """
    rows = store.rows(_PROJECTION, {"l": list(ENTITY_LABELS)})
    graph = nx.Graph()
    graph.add_edges_from((a, b) for a, b in rows if a != b)
    return graph


def eccentricity_report(store: KuzuGraphStore) -> EccentricityReport:
    """Compute eccentricity, radius & diameter over the largest component (§8.13).

    Every ``Rel`` edge is treated as undirected. NetworkX needs a connected graph
    for ``radius``/``diameter``, so metrics are computed on the largest connected
    component; ``center``/``periphery`` are sorted for determinism. An empty graph
    returns empty eccentricity, zero radius/diameter and empty center/periphery.
    """
    graph = _project(store)
    if graph.number_of_nodes() == 0:
        return EccentricityReport(
            eccentricity={},
            radius=0,
            diameter=0,
            center=(),
            periphery=(),
        )

    # Restrict to the largest connected component (ties broken by smallest id).
    components = sorted(
        nx.connected_components(graph),
        key=lambda c: (-len(c), min(c)),
    )
    largest = graph.subgraph(components[0])

    ecc = {nid: int(d) for nid, d in nx.eccentricity(largest).items()}
    radius = min(ecc.values())
    diameter = max(ecc.values())
    center = tuple(sorted(nid for nid, d in ecc.items() if d == radius))
    periphery = tuple(sorted(nid for nid, d in ecc.items() if d == diameter))
    return EccentricityReport(
        eccentricity=dict(sorted(ecc.items())),
        radius=radius,
        diameter=diameter,
        center=center,
        periphery=periphery,
    )
