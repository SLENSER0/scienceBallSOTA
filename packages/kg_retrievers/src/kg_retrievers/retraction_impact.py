"""Retraction evidence-collapse impact — влияние ретракций на схлопывание фактов (§25.12).

A (material, property) *cell* holds the evidence for one measured property of one
material. When observations are soft-retracted (ретракция), the cell can lose part
or all of its supporting evidence. This module rolls a flat list of measurement
dicts up per ``(material_id, property_name)`` cell and flags the two failure modes:

* **collapsed** — every observation in the cell is retracted (``active == 0`` while
  ``retracted > 0``): the fact has fully *collapsed to retracted*, no live support.
* **partial** — the cell has *both* live and retracted observations: still supported
  but weakened (частичная ретракция).

Pure Python and read-only: it reads no store and writes nothing. Per §25.12 the
``retracted`` tombstone lives in the JSON ``props`` catch-all rather than a queryable
Kuzu column, so callers pass it flattened onto the top level of each dict.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CellImpact:
    """Retraction state of one ``(material, property)`` evidence cell (§25.12).

    ``total`` is every observation in the cell; ``active`` + ``retracted`` always
    sum back to it. ``collapsed`` is ``True`` iff ``retracted > 0`` and
    ``active == 0`` — evidence fully collapsed to retracted (полное схлопывание).
    """

    material_id: str
    property_name: str
    total: int
    active: int
    retracted: int
    collapsed: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "material_id": self.material_id,
            "property_name": self.property_name,
            "total": self.total,
            "active": self.active,
            "retracted": self.retracted,
            "collapsed": self.collapsed,
        }


@dataclass(frozen=True)
class RetractionImpact:
    """Impact of retractions across all evidence cells (§25.12).

    ``cells`` is one :class:`CellImpact` per ``(material, property)`` seen, sorted
    by ``(material_id, property_name)``. ``n_collapsed`` counts fully-collapsed
    cells; ``n_partial`` counts cells with both live and retracted evidence.
    ``affected_materials`` lists materials touched by *any* retraction — deduped
    and sorted (материалы, задетые ретракцией).
    """

    cells: list[CellImpact]
    n_collapsed: int
    n_partial: int
    affected_materials: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "cells": [c.as_dict() for c in self.cells],
            "n_collapsed": self.n_collapsed,
            "n_partial": self.n_partial,
            "affected_materials": list(self.affected_materials),
        }


def analyze_retraction_impact(measurements: Iterable[dict[str, Any]]) -> RetractionImpact:
    """Group ``measurements`` per cell and flag evidence collapse (§25.12).

    Each dict carries ``{material_id, property_name, retracted: bool}``. Rows are
    grouped by ``(material_id, property_name)``; per cell we split live vs retracted
    counts and set ``collapsed`` when ``retracted > 0`` and ``active == 0``. A cell
    with both live and retracted rows is *partial*. ``affected_materials`` collects
    every material with at least one retracted row, deduped and sorted. An empty
    input yields empty ``cells``/``affected_materials`` and zero counters.
    """
    totals: dict[tuple[str, str], int] = {}
    retracted_counts: dict[tuple[str, str], int] = {}
    for row in measurements:
        material_id = str(row["material_id"])
        property_name = str(row["property_name"])
        key = (material_id, property_name)
        totals[key] = totals.get(key, 0) + 1
        if bool(row.get("retracted")):
            retracted_counts[key] = retracted_counts.get(key, 0) + 1

    cells: list[CellImpact] = []
    n_collapsed = 0
    n_partial = 0
    affected: set[str] = set()
    for key in sorted(totals):
        material_id, property_name = key
        total = totals[key]
        retracted = retracted_counts.get(key, 0)
        active = total - retracted
        collapsed = retracted > 0 and active == 0
        if collapsed:
            n_collapsed += 1
        elif retracted > 0:
            n_partial += 1
        if retracted > 0:
            affected.add(material_id)
        cells.append(
            CellImpact(
                material_id=material_id,
                property_name=property_name,
                total=total,
                active=active,
                retracted=retracted,
                collapsed=collapsed,
            )
        )

    return RetractionImpact(
        cells=cells,
        n_collapsed=n_collapsed,
        n_partial=n_partial,
        affected_materials=sorted(affected),
    )
