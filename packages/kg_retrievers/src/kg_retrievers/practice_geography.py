"""Practice-geography analysis over technology solutions (§24.23).

География практики — где и в каких условиях применяется ``TechnologySolution``:
в каких странах (``Country``), регионах и климатических зонах (``Geography``), и с
какой практикой (``practice_type``: russia / foreign / global). Модуль собирает эти
характеристики с самого узла-решения и со связанных с ним узлов ``Country`` /
``Geography`` и возвращает их четырьмя отсортированными списками без дубликатов.

English: :func:`geography_for` gathers a solution's geographic footprint —
``countries``, ``regions``, ``climate_zones`` and ``practice_types`` — from two
sources: the solution node's own geography columns and every linked ``Country`` /
``Geography`` node. A ``Country`` contributes its name to *countries*; a
``Geography`` contributes its region name to *regions*; either may also carry a
climate zone or practice type. Values are de-duplicated and sorted for a
deterministic, hand-checkable result. The module is read-only: it never writes.

Kuzu note: custom node properties are not queryable ``Node`` columns, so the
neighbour walk RETURNs only base columns (``id`` / ``label``) and each linked node's
fields are read back through :meth:`KuzuGraphStore.get_node`. The solution's own
geography columns (``country`` / ``region`` / ``climate_zone`` / ``practice_type``)
are likewise read via ``get_node``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from kg_retrievers.graph_store import KuzuGraphStore

# Node label of the solution whose geography is analysed (§24.2 / §24.23).
SOLUTION_LABEL = "TechnologySolution"

# Node label carrying a country (страна применения практики).
COUNTRY_LABEL = "Country"

# Node label carrying a region / climate description (регион, климатическая зона).
GEOGRAPHY_LABEL = "Geography"

# Linked-node labels whose properties feed the geography footprint (§24.23).
GEO_LABELS: frozenset[str] = frozenset({COUNTRY_LABEL, GEOGRAPHY_LABEL})


@dataclass(frozen=True)
class PracticeGeography:
    """Geographic footprint of one solution (§24.23).

    Each field is a de-duplicated, ascending-sorted list of the string values found on
    the solution node and its linked ``Country`` / ``Geography`` nodes: ``countries``
    (страны), ``regions`` (регионы), ``climate_zones`` (климатические зоны) and
    ``practice_types`` (тип практики). Any list is empty when nothing was stated.
    """

    solution_id: str
    countries: list[str]
    regions: list[str]
    climate_zones: list[str]
    practice_types: list[str]

    def as_dict(self) -> dict[str, Any]:
        """JSON shape ``{solution_id, countries, regions, climate_zones, practice_types}``."""
        return {
            "solution_id": self.solution_id,
            "countries": list(self.countries),
            "regions": list(self.regions),
            "climate_zones": list(self.climate_zones),
            "practice_types": list(self.practice_types),
        }


def _clean(value: object) -> str | None:
    """Coerce a node property to a non-empty, stripped ``str`` (else ``None``)."""
    if isinstance(value, str):
        stripped = value.strip()
        if stripped:
            return stripped
    return None


def _country_name(node: dict[str, Any]) -> str | None:
    """A ``Country`` node's country name: ``name`` -> ``canonical_name`` -> ``country``."""
    return (
        _clean(node.get("name"))
        or _clean(node.get("canonical_name"))
        or _clean(node.get("country"))
    )


def _region_name(node: dict[str, Any]) -> str | None:
    """A ``Geography`` node's region name: ``region`` -> ``name`` -> ``canonical_name``."""
    return (
        _clean(node.get("region")) or _clean(node.get("name")) or _clean(node.get("canonical_name"))
    )


def _linked_geo_ids(store: KuzuGraphStore, solution_id: str) -> list[tuple[str, str]]:
    """Distinct ``(id, label)`` of ``Country`` / ``Geography`` nodes linked either way.

    Only base ``Node`` columns are RETURNed; labels are filtered to :data:`GEO_LABELS`
    in Python and de-duplicated on ``id`` so a node reachable through several relations
    is visited once.
    """
    rows = store.rows(
        "MATCH (s:Node {id:$sid})-[:Rel]-(m:Node) RETURN DISTINCT m.id, m.label ORDER BY m.id",
        {"sid": solution_id},
    )
    seen: dict[str, str] = {}
    for mid, label in rows:
        if mid in seen or label not in GEO_LABELS:
            continue
        seen[mid] = label
    return list(seen.items())


def geography_for(store: KuzuGraphStore, solution_id: str) -> PracticeGeography:
    """Collect a solution's practice-geography footprint (§24.23).

    Reads the solution node's own geography columns and every linked ``Country`` /
    ``Geography`` node: a ``Country`` adds its name to ``countries``; a ``Geography``
    adds its region name to ``regions``; either (and the solution itself) may add a
    ``climate_zone`` or ``practice_type``. Every list comes back de-duplicated and
    ascending-sorted. An unknown ``solution_id`` yields an all-empty result (graceful,
    never raises).
    """
    node = store.get_node(solution_id)
    if node is None:
        return PracticeGeography(solution_id, [], [], [], [])

    countries: set[str] = set()
    regions: set[str] = set()
    climate_zones: set[str] = set()
    practice_types: set[str] = set()

    def _absorb_shared(props: dict[str, Any]) -> None:
        for value in (_clean(props.get("country")),):
            if value:
                countries.add(value)
        for value in (_clean(props.get("region")),):
            if value:
                regions.add(value)
        for value in (_clean(props.get("climate_zone")),):
            if value:
                climate_zones.add(value)
        for value in (_clean(props.get("practice_type")),):
            if value:
                practice_types.add(value)

    # 1) The solution node's own geography columns.
    _absorb_shared(node)

    # 2) Linked Country / Geography nodes (custom fields read via get_node).
    for linked_id, label in _linked_geo_ids(store, solution_id):
        linked = store.get_node(linked_id)
        if linked is None:
            continue
        _absorb_shared(linked)
        if label == COUNTRY_LABEL:
            name = _country_name(linked)
            if name:
                countries.add(name)
        elif label == GEOGRAPHY_LABEL:
            name = _region_name(linked)
            if name:
                regions.add(name)

    return PracticeGeography(
        solution_id=solution_id,
        countries=sorted(countries),
        regions=sorted(regions),
        climate_zones=sorted(climate_zones),
        practice_types=sorted(practice_types),
    )
