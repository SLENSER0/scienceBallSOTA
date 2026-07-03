"""3D material × regime × property coverage matrix (§15.5).

The 2D coverage grid (``coverage_matrix.build_coverage_matrix``) audits *material ×
property* only, so it cannot tell whether a property was actually measured **under a
given processing regime** (технологический режим) — a material may be well covered
overall yet have a blind spot for one regime. This module adds the missing third
axis: it cross-products every ``Material`` × ``ProcessingRegime`` × property and marks
each cell ``covered`` iff a single ``Measurement`` links that whole triple.

A ``Measurement`` covers a triple ``(material, regime, property)`` when it

- is ``ABOUT_MATERIAL`` the material, **and**
- is ``ABOUT_REGIME`` the regime, **and**
- carries ``property_name == property``.

Each cell also records how many of the covering measurements are *verified*
(``verified_count``) and whether a ``Gap`` node flags that exact triple
(``has_gap`` / ``gap_ids`` — a Gap that is ``ABOUT_MATERIAL`` the material,
``ABOUT_REGIME`` the regime and carries the same ``property_name``). Gaps are the
audit trail for the *absent* cells: "nobody measured X for this material under this
regime, and here is the recorded knowledge gap that says so".

Filters:
- ``min_confidence`` — only measurements with ``confidence >= min_confidence`` count
  as evidence (a lone low-confidence measurement makes the cell ``absent``);
- ``verified_only`` — only ``verified`` measurements count as evidence.

Neither filter touches the ``Gap`` audit (gaps are separate entities).

The property axis is identified by the ``property_name`` string the graph carries on
``Measurement`` / ``Gap`` nodes; the module surfaces it as ``property_id`` on each
cell. This module is strictly read-only: it never writes to the graph.

Kuzu note: the props this module needs — ``property_name`` / ``verified`` /
``confidence`` — are declared *base* columns (``graph_store.NODE_COLUMNS``), so they
are returned directly; the relationship kind is filtered on the base ``r.type``
column. Any non-column prop would have to be read back via ``store.get_node()``.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from kg_common import get_logger
from kg_retrievers.graph_store import KuzuGraphStore

_log = get_logger("coverage_matrix_3d")

__all__ = [
    "COVERED",
    "ABSENT",
    "Cell",
    "Matrix3D",
    "build_material_regime_property_matrix",
]

# Cell status labels (binary: покрыто / нет).
COVERED = "covered"
ABSENT = "absent"

# Edge kinds anchoring a Measurement / Gap to its material and regime.
_ABOUT_MATERIAL = "ABOUT_MATERIAL"
_ABOUT_REGIME = "ABOUT_REGIME"

# A cell key is the (material id, regime id, property name) triple.
_Triple = tuple[str, str, str]


@dataclass(frozen=True)
class Cell:
    """One (material, regime, property) coverage cell of the 3D matrix (§15.5).

    ``property_id`` is the property identifier (the ``property_name`` the graph carries
    on Measurement / Gap nodes). ``status`` is ``COVERED`` iff at least one qualifying
    Measurement links the whole triple; ``evidence_count`` counts those measurements and
    ``verified_count`` the verified subset. ``has_gap`` / ``gap_ids`` record any ``Gap``
    node flagging the same triple (независимо от фильтров доказательств).
    """

    material_id: str
    regime_id: str
    property_id: str
    status: str  # COVERED | ABSENT
    evidence_count: int
    verified_count: int
    has_gap: bool
    gap_ids: tuple[str, ...]

    @property
    def is_covered(self) -> bool:
        return self.status == COVERED

    def as_dict(self) -> dict:
        return {
            "material_id": self.material_id,
            "regime_id": self.regime_id,
            "property_id": self.property_id,
            "status": self.status,
            "evidence_count": self.evidence_count,
            "verified_count": self.verified_count,
            "has_gap": self.has_gap,
            "gap_ids": list(self.gap_ids),
        }


@dataclass(frozen=True)
class Matrix3D:
    """A material × regime × property coverage cube (§15.5).

    ``materials`` / ``regimes`` / ``properties`` are the three axes; ``cells`` is their
    full cross product (one ``Cell`` per combination, covered or absent). ``as_dict``
    emits ``{"cells": [...], "dims": {...}}`` for JSON transport.
    """

    materials: tuple[str, ...]
    regimes: tuple[str, ...]
    properties: tuple[str, ...]
    cells: tuple[Cell, ...]

    @property
    def covered_count(self) -> int:
        return sum(1 for c in self.cells if c.status == COVERED)

    @property
    def absent_count(self) -> int:
        return sum(1 for c in self.cells if c.status == ABSENT)

    @property
    def gap_count(self) -> int:
        return sum(1 for c in self.cells if c.has_gap)

    def as_dict(self) -> dict:
        return {
            "cells": [c.as_dict() for c in self.cells],
            "dims": {
                "materials": list(self.materials),
                "regimes": list(self.regimes),
                "properties": list(self.properties),
            },
        }


def _material_ids(store: KuzuGraphStore) -> list[str]:
    rows = store.rows("MATCH (n:Node) WHERE n.label='Material' RETURN n.id ORDER BY n.id")
    return [r[0] for r in rows]


def _regime_ids(store: KuzuGraphStore) -> list[str]:
    rows = store.rows("MATCH (n:Node) WHERE n.label='ProcessingRegime' RETURN n.id ORDER BY n.id")
    return [r[0] for r in rows]


def _property_names(store: KuzuGraphStore) -> list[str]:
    """Distinct ``property_name`` across all Measurement and Gap nodes (sorted).

    Both are included so the matrix surfaces an *absent* cell for a property that a Gap
    flags even when no Measurement ever recorded it (свидетельств нет, но пробел есть).
    """
    props: set[str] = set()
    for label in ("Measurement", "Gap"):
        rows = store.rows(
            "MATCH (n:Node) WHERE n.label=$lbl AND n.property_name IS NOT NULL "
            "RETURN DISTINCT n.property_name",
            {"lbl": label},
        )
        props.update(r[0] for r in rows if r[0])
    return sorted(props)


def _measurement_triples(
    store: KuzuGraphStore,
) -> dict[_Triple, dict[str, tuple[bool, float | None]]]:
    """Map each triple to its covering measurements → ``{mid: (verified, confidence)}``.

    One row per ``(measurement, material, regime)`` where the measurement is both
    ``ABOUT_MATERIAL`` the material and ``ABOUT_REGIME`` the regime; the property is the
    measurement's ``property_name``. Measurements without a ``property_name`` cannot be
    placed on the property axis and are skipped.
    """
    rows = store.rows(
        "MATCH (m:Node)-[rm:Rel]->(mat:Node), (m)-[rr:Rel]->(reg:Node) "
        "WHERE m.label='Measurement' AND mat.label='Material' AND reg.label='ProcessingRegime' "
        f"AND rm.type='{_ABOUT_MATERIAL}' AND rr.type='{_ABOUT_REGIME}' "
        "RETURN m.id, mat.id, reg.id, m.property_name, m.verified, m.confidence"
    )
    out: dict[_Triple, dict[str, tuple[bool, float | None]]] = defaultdict(dict)
    for mid, matid, regid, prop, verified, conf in rows:
        if not prop:
            continue
        out[(matid, regid, prop)][mid] = (bool(verified), conf)
    return out


def _gap_triples(store: KuzuGraphStore) -> dict[_Triple, set[str]]:
    """Map each triple to the ids of ``Gap`` nodes flagging it (material×regime×property)."""
    rows = store.rows(
        "MATCH (g:Node)-[rm:Rel]->(mat:Node), (g)-[rr:Rel]->(reg:Node) "
        "WHERE g.label='Gap' AND mat.label='Material' AND reg.label='ProcessingRegime' "
        f"AND rm.type='{_ABOUT_MATERIAL}' AND rr.type='{_ABOUT_REGIME}' "
        "RETURN g.id, mat.id, reg.id, g.property_name"
    )
    out: dict[_Triple, set[str]] = defaultdict(set)
    for gid, matid, regid, prop in rows:
        if not prop:
            continue
        out[(matid, regid, prop)].add(gid)
    return out


def build_material_regime_property_matrix(
    store: KuzuGraphStore,
    *,
    min_confidence: float | None = None,
    verified_only: bool = False,
) -> Matrix3D:
    """Build the 3D material × regime × property coverage matrix (§15.5).

    Axes are every ``Material`` id, every ``ProcessingRegime`` id and every distinct
    ``property_name`` seen on Measurement / Gap nodes. Each cell of the full cross
    product is ``COVERED`` iff at least one qualifying ``Measurement`` links the triple,
    else ``ABSENT``. ``min_confidence`` drops measurements below that confidence and
    ``verified_only`` keeps only verified ones; ``verified_count`` always reports the
    verified subset of the qualifying evidence. ``has_gap`` / ``gap_ids`` flag a
    recorded ``Gap`` for the same triple and are unaffected by the evidence filters.
    """
    materials = _material_ids(store)
    regimes = _regime_ids(store)
    properties = _property_names(store)
    meas = _measurement_triples(store)
    gaps = _gap_triples(store)

    def qualifies(verified: bool, conf: float | None) -> bool:
        if verified_only and not verified:
            return False
        return min_confidence is None or (conf is not None and conf >= min_confidence)

    cells: list[Cell] = []
    for mat in materials:
        for reg in regimes:
            for prop in properties:
                key = (mat, reg, prop)
                found = meas.get(key, {})
                qualifying = [(v, c) for (v, c) in found.values() if qualifies(v, c)]
                evidence_count = len(qualifying)
                verified_count = sum(1 for (v, _c) in qualifying if v)
                gap_ids = tuple(sorted(gaps.get(key, set())))
                cells.append(
                    Cell(
                        material_id=mat,
                        regime_id=reg,
                        property_id=prop,
                        status=COVERED if evidence_count > 0 else ABSENT,
                        evidence_count=evidence_count,
                        verified_count=verified_count,
                        has_gap=bool(gap_ids),
                        gap_ids=gap_ids,
                    )
                )

    matrix = Matrix3D(
        materials=tuple(materials),
        regimes=tuple(regimes),
        properties=tuple(properties),
        cells=tuple(cells),
    )
    _log.info(
        "coverage_matrix_3d.built",
        materials=len(materials),
        regimes=len(regimes),
        properties=len(properties),
        cells=len(cells),
        covered=matrix.covered_count,
    )
    return matrix
