"""Map of the unknown — absence-confidence aggregate (§25.11).

Builds a structured *(material × property)* coverage grid where every cell carries
a confidence-of-absence, then rolls the grid up into status counts, a per-property
breakdown, a per-domain breakdown and a compact summary. This is the «карта
неизвестного» (map of the unknown): it turns the scattered ``CoverageCell``s
produced by :class:`AbsenceAnalyzer` (§25.3–25.5) into one serialisable picture of
*what the corpus does and does not cover*, ready for a dashboard or an agent tool.

The module never recomputes confidence itself — it is built entirely on top of
``AbsenceAnalyzer.coverage_matrix`` and only groups and summarises (§25.11).

Cell status vocabulary (from ``confidence_of_absence``):
- ``COVERED`` — evidence exists, ``confidence_of_absence == 0.0``;
- ``CONFIDENT_ABSENCE`` — empty cell, posterior ≥ threshold → a real gap;
- ``POSSIBLE_ABSENCE`` — empty cell, posterior below the confident band;
- ``UNKNOWN`` — recall too low to conclude anything (``confidence_of_absence`` is
  the string ``"unknown"``, so it never contributes to ``mean_confidence``).
"""

from __future__ import annotations

from dataclasses import dataclass

from kg_common import get_logger
from kg_retrievers.confidence_of_absence import (
    CONFIDENT_ABSENCE,
    COVERED,
    DEFAULT_PROPERTIES,
    POSSIBLE_ABSENCE,
    UNKNOWN,
    AbsenceAnalyzer,
    CoverageCell,
    ExtractorRecall,
)
from kg_retrievers.graph_store import KuzuGraphStore

_log = get_logger("absence_map")

# Ordered status vocabulary so counts and serialisation stay deterministic (§25.11).
STATUSES: tuple[str, ...] = (COVERED, CONFIDENT_ABSENCE, POSSIBLE_ABSENCE, UNKNOWN)

# Placeholder domain for materials that carry no ``domain`` field.
NO_DOMAIN = "—"


def _is_numeric(conf: float | str) -> bool:
    """True for a real confidence float, False for the ``"unknown"`` sentinel."""
    return isinstance(conf, (int, float)) and not isinstance(conf, bool)


def _mean_confidence(cells: list[CoverageCell]) -> float:
    """Mean ``confidence_of_absence`` over cells that carry a numeric value.

    ``UNKNOWN`` cells (string sentinel) are excluded; the result is always in
    ``[0, 1]`` and is ``0.0`` when no cell carries a numeric confidence (§25.11).
    """
    vals = [float(c.confidence_of_absence) for c in cells if _is_numeric(c.confidence_of_absence)]
    if not vals:
        return 0.0
    return round(sum(vals) / len(vals), 4)


def _count_by_status(cells: list[CoverageCell]) -> dict[str, int]:
    """Count cells per status; keys always cover the full ``STATUSES`` vocabulary."""
    counts = dict.fromkeys(STATUSES, 0)
    for c in cells:
        counts[c.status] = counts.get(c.status, 0) + 1
    return counts


@dataclass
class AbsenceSummary:
    """One-line rollup of a coverage grid (§25.11 Критерий приёмки)."""

    n_cells: int
    n_covered: int
    n_confident_absence: int
    n_possible_absence: int
    n_unknown: int
    mean_confidence: float

    def as_dict(self) -> dict:
        return {
            "n_cells": self.n_cells,
            "n_covered": self.n_covered,
            "n_confident_absence": self.n_confident_absence,
            "n_possible_absence": self.n_possible_absence,
            "n_unknown": self.n_unknown,
            "mean_confidence": self.mean_confidence,
        }


@dataclass
class PropertyCoverage:
    """Per-property slice of the map: how a single property is covered (§25.11)."""

    property_name: str
    n_cells: int
    by_status: dict[str, int]
    mean_confidence: float

    def as_dict(self) -> dict:
        return {
            "property_name": self.property_name,
            "n_cells": self.n_cells,
            "by_status": self.by_status,
            "mean_confidence": self.mean_confidence,
        }


@dataclass
class AbsenceMap:
    """Structured map of the unknown over a (material × property) grid (§25.11)."""

    domain: str | None
    materials: list[str]
    properties: list[str]
    cells: list[CoverageCell]
    by_status: dict[str, int]
    by_property: dict[str, PropertyCoverage]
    by_domain: dict[str, dict[str, int]]
    summary: AbsenceSummary

    def cell(self, material_id: str, property_name: str) -> CoverageCell | None:
        """Look up a single grid cell by (material_id, property_name)."""
        for c in self.cells:
            if c.material_id == material_id and c.property_name == property_name:
                return c
        return None

    def as_dict(self) -> dict:
        return {
            "domain": self.domain,
            "materials": self.materials,
            "properties": self.properties,
            "n_cells": len(self.cells),
            "by_status": self.by_status,
            "by_property": {k: v.as_dict() for k, v in self.by_property.items()},
            "by_domain": self.by_domain,
            "summary": self.summary.as_dict(),
            "cells": [c.as_dict() for c in self.cells],
        }


def _materials_in(store: KuzuGraphStore, domain: str | None) -> list[str]:
    """Ids of every ``Material`` node (optionally restricted to ``domain``)."""
    if domain:
        rows = store.rows(
            "MATCH (n:Node) WHERE n.label='Material' AND n.domain=$d RETURN n.id ORDER BY n.id",
            {"d": domain},
        )
    else:
        rows = store.rows("MATCH (n:Node) WHERE n.label='Material' RETURN n.id ORDER BY n.id")
    return [r[0] for r in rows]


def _domains_of(store: KuzuGraphStore, cells: list[CoverageCell]) -> dict[str, str]:
    """Resolve each cell's material id to its ``domain`` (cached per material)."""
    domain_of: dict[str, str] = {}
    for c in cells:
        if c.material_id in domain_of:
            continue
        nd = store.get_node(c.material_id)
        domain_of[c.material_id] = (nd or {}).get("domain") or NO_DOMAIN
    return domain_of


def build_absence_map(
    store: KuzuGraphStore,
    materials: list[str] | None = None,
    properties: list[str] | None = None,
    domain: str | None = None,
    *,
    recall: ExtractorRecall | None = None,
) -> AbsenceMap:
    """Build the absence map for a (material × property) grid (§25.11).

    ``materials`` defaults to every ``Material`` node (filtered by ``domain`` when
    given); ``properties`` defaults to ``confidence_of_absence.DEFAULT_PROPERTIES``.
    Coverage + confidence-of-absence for every pair is delegated to
    ``AbsenceAnalyzer.coverage_matrix`` — this function only aggregates the result
    into status counts, a per-property breakdown, a per-domain breakdown and a
    summary (``n_covered / n_confident_absence / n_possible_absence / n_unknown /
    mean_confidence``).
    """
    analyzer = AbsenceAnalyzer(store, recall=recall)
    props = list(properties or DEFAULT_PROPERTIES)
    mats = list(materials) if materials is not None else _materials_in(store, domain)

    cells: list[CoverageCell] = analyzer.coverage_matrix(mats, props) if (mats and props) else []

    by_status = _count_by_status(cells)

    by_property: dict[str, PropertyCoverage] = {}
    for prop in props:
        p_cells = [c for c in cells if c.property_name == prop]
        if not p_cells:
            continue
        by_property[prop] = PropertyCoverage(
            property_name=prop,
            n_cells=len(p_cells),
            by_status=_count_by_status(p_cells),
            mean_confidence=_mean_confidence(p_cells),
        )

    domain_of = _domains_of(store, cells)
    by_domain: dict[str, dict[str, int]] = {}
    for c in cells:
        bucket = by_domain.setdefault(domain_of[c.material_id], dict.fromkeys(STATUSES, 0))
        bucket[c.status] = bucket.get(c.status, 0) + 1

    summary = AbsenceSummary(
        n_cells=len(cells),
        n_covered=by_status[COVERED],
        n_confident_absence=by_status[CONFIDENT_ABSENCE],
        n_possible_absence=by_status[POSSIBLE_ABSENCE],
        n_unknown=by_status[UNKNOWN],
        mean_confidence=_mean_confidence(cells),
    )

    _log.info(
        "absence_map.built",
        domain=domain or "*",
        n_materials=len(mats),
        n_properties=len(props),
        **summary.as_dict(),
    )
    return AbsenceMap(
        domain=domain,
        materials=list(mats),
        properties=props,
        cells=cells,
        by_status=by_status,
        by_property=by_property,
        by_domain=by_domain,
        summary=summary,
    )
