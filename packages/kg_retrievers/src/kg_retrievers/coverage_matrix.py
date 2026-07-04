"""Coverage-matrix aggregations for the gap dashboard (§15.5).

Three read-only views over the knowledge graph, built on top of
``AbsenceAnalyzer.coverage_matrix`` (§25.3–25.5, confidence_of_absence.py):

- :func:`build_coverage_matrix` — a material × property grid, each cell tagged
  ``covered`` / ``absent`` with an evidence and a *verified* measurement count;
- :func:`aggregate_gaps_by_owner` — existing ``Gap`` nodes grouped by their
  owning lab / domain (лаборатория / домен), so the partition sums to the total
  number of gaps;
- :func:`build_coverage_timeline` — paper / measurement / gap counts bucketed by
  ``Paper.year`` and returned year-ordered (ascending).

All results are frozen dataclasses exposing ``as_dict()`` for JSON transport.
This module is read-only: it never writes to the graph.
"""

from __future__ import annotations

from dataclasses import dataclass

from kg_retrievers.confidence_of_absence import (
    COVERED,
    DEFAULT_COVERAGE_DEPTH,
    DEFAULT_PROPERTIES,
    AbsenceAnalyzer,
)
from kg_retrievers.graph_store import KuzuGraphStore

# Cell status labels for the material × property grid (binary: покрыто / нет).
MATRIX_COVERED = "covered"
MATRIX_ABSENT = "absent"

# Owner bucket used when a Gap can be attached to neither a domain nor a lab.
UNASSIGNED_OWNER = "unassigned"


# ---------------------------------------------------------------------------
# Coverage matrix (material × property)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class MatrixCell:
    """One (material, property) grid cell with coverage + verified evidence (§15.5)."""

    material_id: str
    material_name: str
    property_name: str
    status: str  # MATRIX_COVERED | MATRIX_ABSENT
    evidence_count: int
    verified_count: int

    @property
    def is_covered(self) -> bool:
        return self.status == MATRIX_COVERED

    def as_dict(self) -> dict:
        return {
            "material_id": self.material_id,
            "material_name": self.material_name,
            "property_name": self.property_name,
            "status": self.status,
            "evidence_count": self.evidence_count,
            "verified_count": self.verified_count,
        }


@dataclass(frozen=True)
class CoverageMatrix:
    """A material × property coverage grid (§15.5).

    ``materials`` and ``properties`` are the grid axes (material node ids and
    property names respectively); ``cells`` is their cross product.
    """

    materials: tuple[str, ...]
    properties: tuple[str, ...]
    cells: tuple[MatrixCell, ...]

    @property
    def covered_count(self) -> int:
        return sum(1 for c in self.cells if c.status == MATRIX_COVERED)

    @property
    def absent_count(self) -> int:
        return sum(1 for c in self.cells if c.status == MATRIX_ABSENT)

    def as_dict(self) -> dict:
        return {
            "materials": list(self.materials),
            "properties": list(self.properties),
            "covered_count": self.covered_count,
            "absent_count": self.absent_count,
            "cells": [c.as_dict() for c in self.cells],
        }


def _all_material_ids(store: KuzuGraphStore) -> list[str]:
    rows = store.rows("MATCH (n:Node) WHERE n.label='Material' RETURN n.id ORDER BY n.id")
    return [r[0] for r in rows]


def _verified_count(store: KuzuGraphStore, subject_id: str, property_name: str, depth: int) -> int:
    """Distinct *verified* Measurements of ``property_name`` within N hops (§15.5)."""
    rows = store.rows(
        f"MATCH (s:Node {{id:$sid}})-[:Rel*1..{depth}]-(meas:Node) "
        "WHERE meas.label='Measurement' AND meas.property_name=$prop "
        "AND meas.verified=true RETURN DISTINCT meas.id",
        {"sid": subject_id, "prop": property_name},
    )
    return len(rows)


def build_coverage_matrix(
    store: KuzuGraphStore,
    materials: list[str] | None = None,
    properties: list[str] | None = None,
    *,
    coverage_depth: int = DEFAULT_COVERAGE_DEPTH,
) -> CoverageMatrix:
    """Build a material × property coverage grid (§15.5).

    ``materials`` may be node ids or names (resolved by the analyzer); ``None``
    means *every* ``Material`` node. ``properties`` defaults to the analyzer's
    ``DEFAULT_PROPERTIES``. An empty (``[]``) axis yields an empty grid.

    Each cell is ``covered`` when at least one Measurement of the property is
    reachable within ``coverage_depth`` hops, else ``absent``; ``verified_count``
    counts only measurements flagged ``verified``.
    """
    props = list(properties) if properties is not None else list(DEFAULT_PROPERTIES)
    mat_ids = list(materials) if materials is not None else _all_material_ids(store)

    analyzer = AbsenceAnalyzer(store, coverage_depth=coverage_depth)
    depth = analyzer.coverage_depth
    raw_cells = analyzer.coverage_matrix(mat_ids, props)

    cells: list[MatrixCell] = []
    for c in raw_cells:
        status = MATRIX_COVERED if c.status == COVERED else MATRIX_ABSENT
        verified = _verified_count(store, c.material_id, c.property_name, depth)
        cells.append(
            MatrixCell(
                material_id=c.material_id,
                material_name=c.material_name,
                property_name=c.property_name,
                status=status,
                evidence_count=c.evidence_count,
                verified_count=verified,
            )
        )
    return CoverageMatrix(
        materials=tuple(mat_ids),
        properties=tuple(props),
        cells=tuple(cells),
    )


# ---------------------------------------------------------------------------
# Gaps by owner (lab / domain)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class GapByOwner:
    """Existing ``Gap`` nodes grouped by their owning lab / domain (§15.5)."""

    owner: str  # domain key (RU/EN domain term) or UNASSIGNED_OWNER
    lab_id: str | None
    lab_name: str | None
    gap_count: int
    gap_ids: tuple[str, ...]

    def as_dict(self) -> dict:
        return {
            "owner": self.owner,
            "lab_id": self.lab_id,
            "lab_name": self.lab_name,
            "gap_count": self.gap_count,
            "gap_ids": list(self.gap_ids),
        }


def _labs_by_domain(store: KuzuGraphStore) -> dict[str, tuple[str, str | None]]:
    rows = store.rows(
        "MATCH (l:Node) WHERE l.label='Lab' AND l.domain IS NOT NULL "
        "RETURN l.domain, l.id, l.name ORDER BY l.id"
    )
    # first lab per domain wins (deterministic via ORDER BY l.id)
    out: dict[str, tuple[str, str | None]] = {}
    for domain, lid, name in rows:
        out.setdefault(domain, (lid, name))
    return out


def aggregate_gaps_by_owner(store: KuzuGraphStore) -> list[GapByOwner]:
    """Group existing ``Gap`` nodes by owning lab / domain (§15.5).

    A gap's owner is its own ``domain`` if set, else the domain of any subject it
    points to (``ABOUT`` / ``ABOUT_REGIME`` …), else ``UNASSIGNED_OWNER``. A lab
    sharing the owner's domain is attached when one exists. The returned groups
    partition all ``Gap`` nodes, so ``sum(g.gap_count)`` equals the total.
    """
    rows = store.rows(
        "MATCH (g:Node) WHERE g.label='Gap' "
        "OPTIONAL MATCH (g)-[:Rel]->(subj:Node) "
        "RETURN g.id, g.domain, collect(subj.domain)"
    )
    labs = _labs_by_domain(store)
    buckets: dict[str, list[str]] = {}
    for gid, gdomain, subj_domains in rows:
        owner = gdomain or next((d for d in (subj_domains or []) if d), None) or UNASSIGNED_OWNER
        buckets.setdefault(owner, []).append(gid)

    groups: list[GapByOwner] = []
    for owner in sorted(buckets):
        gid_list = sorted(buckets[owner])
        lab = labs.get(owner)
        groups.append(
            GapByOwner(
                owner=owner,
                lab_id=lab[0] if lab else None,
                lab_name=lab[1] if lab else None,
                gap_count=len(gid_list),
                gap_ids=tuple(gid_list),
            )
        )
    return groups


# ---------------------------------------------------------------------------
# Coverage timeline (by paper year)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class CoverageTimelinePoint:
    """Paper / measurement / gap counts for one ``Paper.year`` bucket (§15.5)."""

    year: int
    paper_count: int
    measurement_count: int
    gap_count: int

    def as_dict(self) -> dict:
        return {
            "year": self.year,
            "paper_count": self.paper_count,
            "measurement_count": self.measurement_count,
            "gap_count": self.gap_count,
        }


# A subject (Measurement / Gap) is dated to a year through either the direct
# ``SUPPORTED_BY`` edge to a dated source (seed graph: ``Paper``) or the real
# server-graph provenance chain ``->Evidence-FROM_CHUNK->Chunk<-HAS_CHUNK-Document``
# (§8.2). Both the source node and the reached Document may carry ``year``, so a
# subject is counted in *every* year it is evidenced by (distinct per year).
_DATED_COUNTS_CYPHER = (
    "MATCH (x:Node)-[:Rel {type:'SUPPORTED_BY'}]->(src:Node) "
    "WHERE x.label=$label "
    "OPTIONAL MATCH (src)-[:Rel {type:'FROM_CHUNK'}]->(:Node)"
    "<-[:Rel {type:'HAS_CHUNK'}]-(doc:Node) "
    "UNWIND ["
    "  CASE WHEN src.label IN ['Paper', 'Document'] THEN src.year ELSE NULL END, "
    "  CASE WHEN doc.label = 'Document' THEN doc.year ELSE NULL END"
    "] AS yr "
    "WITH x.id AS xid, yr WHERE yr IS NOT NULL "
    "RETURN yr, count(DISTINCT xid)"
)


def _dated_counts(store: KuzuGraphStore, label: str) -> dict[int, int]:
    """Map ``year -> distinct count`` of ``label`` subjects dated to that year (§15.5).

    Traverses the real provenance path (``SUPPORTED_BY`` to a dated ``Paper`` /
    ``Document``, or via ``Evidence -> Chunk <- Document``) in a single query, so
    the timeline reflects the actual server graph rather than the non-existent
    ``Measurement -SUPPORTED_BY-> Paper`` shortcut.
    """
    rows = store.rows(_DATED_COUNTS_CYPHER, {"label": label})
    return {int(yr): int(cnt) for yr, cnt in rows}


def build_coverage_timeline(store: KuzuGraphStore) -> list[CoverageTimelinePoint]:
    """Coverage timeline bucketed by ``Paper.year`` (§15.5).

    For each distinct paper year (ascending) counts the papers, the distinct
    Measurements evidenced by a source of that year, and the distinct Gaps
    likewise dated (via the real ``->Evidence->Document`` provenance chain).
    All counts are non-negative ints.
    """
    year_rows = store.rows(
        "MATCH (p:Node) WHERE p.label='Paper' AND p.year IS NOT NULL "
        "RETURN p.year, count(DISTINCT p.id) ORDER BY p.year"
    )
    measurement_by_year = _dated_counts(store, "Measurement")
    gap_by_year = _dated_counts(store, "Gap")
    points: list[CoverageTimelinePoint] = []
    for year, paper_count in year_rows:
        yr = int(year)
        points.append(
            CoverageTimelinePoint(
                year=yr,
                paper_count=int(paper_count),
                measurement_count=measurement_by_year.get(yr, 0),
                gap_count=gap_by_year.get(yr, 0),
            )
        )
    return points
