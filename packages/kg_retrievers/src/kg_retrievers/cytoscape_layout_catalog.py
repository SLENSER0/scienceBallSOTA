"""Cytoscape.js layout-algorithm catalog + topology recommender (§17.10).

The advanced-layout mode (§17) lets the operator pick *how* a Cytoscape.js graph is
arranged. This module is the pure-python source of truth for that picker: a frozen
catalog of layout algorithms — each with a display label, a "best for" hint, whether it
respects edge *direction* and its default parameter dict — plus a small topology-driven
:func:`recommend_layout` heuristic that suggests a sensible default from node / edge
counts. Rendering itself is client-side Cytoscape.js; :mod:`graph_cytoscape_export`
handles the element / style export, this module handles *layout choice* only.

No graph/store access, no LLM, no clock: the catalog is a frozen constant and the
recommender is a pure function of its arguments, so both are fully deterministic.
Каждый вариант раскладки (layout) — это :class:`LayoutOption`; рекомендатель выбирает
подходящий по размеру и плотности графа (graph density).

Entry points:

- :func:`list_layouts` — the full frozen catalog as a tuple;
- :func:`get_layout` — one :class:`LayoutOption` by name (or ``None``);
- :func:`recommend_layout` — топология → рекомендованный :class:`LayoutOption`.

Kuzu note: custom node props are *not* queryable columns — a caller that derives node /
edge counts from the store must ``RETURN`` base columns and hydrate the rest via
``get_node`` before calling :func:`recommend_layout`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class LayoutOption:
    """One Cytoscape.js layout algorithm and its defaults (§17.10).

    ``name`` is the Cytoscape.js layout id (e.g. ``"dagre"``); ``label`` is the
    human-facing picker text; ``best_for`` is a short RU/EN hint; ``directed`` marks
    layouts that honour edge direction (иерархические — hierarchical); ``params`` holds
    the default algorithm parameters passed straight to Cytoscape.js.
    """

    name: str
    label: str
    best_for: str
    directed: bool
    params: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        """Return a plain dict of this option; ``params`` is copied so it round-trips."""
        return {
            "name": self.name,
            "label": self.label,
            "best_for": self.best_for,
            "directed": self.directed,
            "params": dict(self.params),
        }


# Frozen catalog. Names must stay unique — :func:`get_layout` and the recommender key on
# them. Order is picker-display order (force-directed → hierarchical → geometric).
_LAYOUTS: tuple[LayoutOption, ...] = (
    LayoutOption(
        name="cose-bilkent",
        label="CoSE-Bilkent (force-directed)",
        best_for="dense / clustered graphs — плотные графы со скоплениями",
        directed=False,
        params={"animate": "end", "nodeRepulsion": 4500, "idealEdgeLength": 50},
    ),
    LayoutOption(
        name="cola",
        label="Cola (constraint force-directed)",
        best_for="general medium graphs — общий случай средних графов",
        directed=False,
        params={"animate": True, "maxSimulationTime": 4000, "edgeLength": 45},
    ),
    LayoutOption(
        name="dagre",
        label="Dagre (layered hierarchy)",
        best_for="DAGs / flows — направленные ациклические графы",
        directed=True,
        params={"rankDir": "TB", "nodeSep": 50, "rankSep": 60},
    ),
    LayoutOption(
        name="breadthfirst",
        label="Breadth-first (tree)",
        best_for="trees / rooted hierarchies — деревья от корня",
        directed=True,
        params={"directed": True, "spacingFactor": 1.2},
    ),
    LayoutOption(
        name="circle",
        label="Circle",
        best_for="small graphs — небольшие графы, обзор целиком",
        directed=False,
        params={"spacingFactor": 1.0},
    ),
    LayoutOption(
        name="concentric",
        label="Concentric (rings by degree)",
        best_for="hub-and-spoke — центры и периферия по степени",
        directed=False,
        params={"minNodeSpacing": 30, "spacingFactor": 1.0},
    ),
)


def list_layouts() -> tuple[LayoutOption, ...]:
    """Return the full frozen layout catalog (§17.10)."""
    return _LAYOUTS


def get_layout(name: str) -> LayoutOption | None:
    """Return the :class:`LayoutOption` named ``name``, or ``None`` if absent (§17.10)."""
    for option in _LAYOUTS:
        if option.name == name:
            return option
    return None


def _require(name: str) -> LayoutOption:
    """Return the catalog entry for ``name`` or raise — internal recommender guard."""
    option = get_layout(name)
    if option is None:  # pragma: no cover - catalog names are static constants
        raise KeyError(f"layout {name!r} missing from catalog")
    return option


# Thresholds for :func:`recommend_layout`. Kept as named constants so the heuristic reads
# like the spec: маленький граф (small), плотный граф (dense).
_SMALL_NODE_MAX = 12
_DENSE_EDGE_FACTOR = 2


def recommend_layout(node_count: int, edge_count: int, *, is_dag: bool = False) -> LayoutOption:
    """Recommend a :class:`LayoutOption` from graph topology (§17.10).

    Rules, in priority order:

    - ``is_dag`` → ``"dagre"`` (layered hierarchy for directed acyclic graphs);
    - small graph (``node_count <= 12``) → ``"circle"`` (whole-graph overview);
    - dense graph (``edge_count > 2 * node_count``) → ``"cose-bilkent"`` (force-directed
      clustering);
    - otherwise → ``"cola"`` (general-purpose middle ground).
    """
    if is_dag:
        return _require("dagre")
    if node_count <= _SMALL_NODE_MAX:
        return _require("circle")
    if edge_count > _DENSE_EDGE_FACTOR * node_count:
        return _require("cose-bilkent")
    return _require("cola")
