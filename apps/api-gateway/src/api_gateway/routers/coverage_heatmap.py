"""Material × property coverage heatmap endpoint (§17.14 / §5.2.7 Gap Dashboard).

RU: Отдаёт наружу готовую матрицу покрытия «материал × свойство» в форме, удобной
для тепловой карты (heatmap) панели пробелов. Переиспользует уже готовый чистый
построитель ``kg_retrievers.coverage_matrix.build_coverage_matrix`` (тот же, что
использует ``/admin/coverage-matrix``), но выдаёт компактный heatmap-ориентированный
payload: оси, плоский список ячеек с ``evidence_count`` и флагом пробела, максимум
для нормировки цвета и агрегат покрытия. Плюс drill-down по паре «материал × свойство»
(``GET /coverage/cell``) — конкретные измерения и пробелы для клика по ячейке.

EN: Surfaces the ready material×property coverage grid in a heatmap-friendly shape
for the §5.2.7 Gap Dashboard. It reuses the existing pure builder
``kg_retrievers.coverage_matrix.build_coverage_matrix`` (the same one behind
``/admin/coverage-matrix``) and reshapes it for an ECharts/SVG heatmap: axes, a flat
cell list carrying ``evidence_count`` and a gap flag, the max count for colour
scaling, and a coverage summary. A per-cell drill-down (``GET /coverage/cell``)
returns the measurements and gaps behind one ``(material, property)`` pair.

Distinct ``/coverage`` prefix so it never collides with ``/gaps`` (whose greedy
``GET /gaps/{gap_id}`` would shadow a sibling literal path) nor with the heavier
bundled ``/admin/coverage-matrix`` (which also computes by-owner + timeline).

Strictly read-only: it never mutates the graph. Kuzu/Neo4j note (§14.8): only base
columns (``property_name`` / ``verified`` / ``confidence`` / ``name``) are RETURNed,
matching the live Neo4j server profile used by the rest of the gap dashboard.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from api_gateway.deps import get_store

router = APIRouter(prefix="/api/v1/coverage", tags=["coverage"])

# Gap nodes anchor to their subject via one of these edge kinds (§5.2.7).
_GAP_ABOUT_TYPES = ("ABOUT", "ABOUT_MATERIAL")


@router.get("/matrix")
def coverage_heatmap(
    material_limit: int | None = Query(default=60, ge=1, le=500),
    coverage_depth: int = Query(default=2, ge=1, le=4),
) -> dict:
    """Material × property coverage grid, reshaped for a heatmap (§17.14 / §5.2.7).

    Reuses ``build_coverage_matrix`` and emits a flat cell list. ``material_limit``
    caps the material axis (ordered by id) so the heatmap stays readable and the
    query bounded; ``coverage_depth`` is the reachability depth a Measurement may
    sit from a material to count as evidence. Each cell carries ``evidence_count``
    (for colour intensity), ``verified_count`` and ``gap`` (``status == 'absent'``).
    ``max_evidence`` is the palette's upper bound and ``summary`` the coverage roll-up.
    """
    from kg_retrievers.coverage_matrix import MATRIX_ABSENT, build_coverage_matrix

    store = get_store()

    # Bounded, id-ordered material axis (names carried on the cells themselves).
    mat_ids: list[str] | None = None
    if material_limit is not None:
        rows = store.rows(
            "MATCH (n:Node) WHERE n.label='Material' RETURN n.id ORDER BY n.id "
            f"LIMIT {int(material_limit)}"
        )
        mat_ids = [r[0] for r in rows]

    matrix = build_coverage_matrix(store, materials=mat_ids, coverage_depth=coverage_depth)

    name_by_id: dict[str, str] = {}
    cells: list[dict[str, Any]] = []
    max_evidence = 0
    for c in matrix.cells:
        name_by_id.setdefault(c.material_id, c.material_name or c.material_id)
        if c.evidence_count > max_evidence:
            max_evidence = c.evidence_count
        cells.append(
            {
                "material_id": c.material_id,
                "material_name": c.material_name or c.material_id,
                "property": c.property_name,
                "status": c.status,
                "evidence_count": c.evidence_count,
                "verified_count": c.verified_count,
                "gap": c.status == MATRIX_ABSENT,
            }
        )

    materials = [{"id": mid, "name": name_by_id.get(mid, mid)} for mid in matrix.materials]
    total = len(matrix.cells)
    covered = matrix.covered_count
    return {
        "materials": materials,
        "properties": list(matrix.properties),
        "cells": cells,
        "max_evidence": max_evidence,
        "summary": {
            "covered": covered,
            "absent": matrix.absent_count,
            "total": total,
            "coverage_ratio": round(covered / total, 4) if total else 0.0,
        },
    }


@router.get("/cell")
def coverage_cell(
    material_id: str = Query(..., min_length=1),
    property: str = Query(..., min_length=1),  # wire name matches the axis label
    coverage_depth: int = Query(default=2, ge=1, le=4),
    limit: int = Query(default=100, ge=1, le=500),
) -> dict:
    """Drill-down for one heatmap cell: measurements + gaps for a (material, property).

    ``measurements`` are the ``Measurement`` nodes of ``property`` reachable within
    ``coverage_depth`` hops of the material (the same reachability the grid counts),
    each with its verified flag and confidence. ``gaps`` are ``Gap`` nodes flagging
    the same pair. Feeds the click-through under a heatmap cell (§5.2.7).
    """
    store = get_store()
    depth = int(coverage_depth)

    meas_rows = store.rows(
        f"MATCH (s:Node {{id:$mid}})-[:Rel*1..{depth}]-(meas:Node) "
        "WHERE meas.label='Measurement' AND meas.property_name=$prop "
        "RETURN DISTINCT meas.id, coalesce(meas.name,''), meas.verified, "
        "meas.review_status, meas.value_normalized, meas.normalized_unit "
        f"LIMIT {int(limit)}",
        {"mid": material_id, "prop": property},
    )

    # Rule extraction stamps a flat prior confidence (0.6 on ~all measurements), so the raw
    # stored value made every drill-down read the same "0.6". Derive a meaningful per-measurement
    # confidence from signals the node actually carries: curator review, unit-normalization, and
    # how many measurements corroborate this exact (material × property) pair. Read-only — the
    # stored node value is left untouched.
    _corrob = min(0.12, 0.02 * max(0, len(meas_rows) - 1))

    def _confidence(verified: object, review_status: object, vnorm: object, unit: object) -> float:
        score = 0.5
        if bool(verified) or review_status == "accepted":
            score += 0.28
        if vnorm is not None and unit:
            score += 0.10
        score += _corrob
        return round(min(0.98, max(0.3, score)), 2)

    measurements = [
        {
            "id": r[0],
            "name": r[1] or r[0],
            "verified": bool(r[2]),
            "confidence": _confidence(r[2], r[3], r[4], r[5]),
        }
        for r in meas_rows
    ]

    gap_rows = store.rows(
        "MATCH (g:Node)-[r:Rel]->(m:Node) "
        "WHERE g.label='Gap' AND m.label='Material' AND m.id=$mid "
        "AND r.type IN $types AND g.property_name=$prop "
        "RETURN DISTINCT g.id, coalesce(g.name,''), g.gap_type "
        f"LIMIT {int(limit)}",
        {"mid": material_id, "prop": property, "types": list(_GAP_ABOUT_TYPES)},
    )
    gaps = [{"id": r[0], "name": r[1] or r[0], "gap_type": r[2]} for r in gap_rows]

    return {
        "material_id": material_id,
        "property": property,
        "measurements": measurements,
        "gaps": gaps,
        "counts": {"measurements": len(measurements), "gaps": len(gaps)},
    }
