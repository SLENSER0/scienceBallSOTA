"""Material → regime → property coverage sankey endpoint (§17.14 / §5.2.7 Gap Dashboard).

RU: Отдаёт наружу трёхосное покрытие «материал → технологический режим → свойство»
в форме, удобной для потоковой диаграммы (sankey). Переиспользует уже готовый чистый
построитель ``kg_retrievers.coverage_matrix_3d.build_material_regime_property_matrix``
(тот же куб material × regime × property, что описан в §15.5) и сворачивает его в два
слоя потоков:

- ``material → regime`` — сумма измерений-доказательств по всем свойствам этой пары;
- ``regime → property`` — сумма измерений-доказательств по всем материалам этой пары.

Толщина потока = число измерений (``value`` = evidence count), ровно как требует
критерий приёмки §17.14 («толщина = evidence/experiment count»). Узлы несут пропускную
способность (``throughput``) для вертикальной раскладки и число зафиксированных пробелов
(``gap_count``) для подсветки «слепых» режимов/свойств.

EN: Surfaces the ready material × regime × property coverage cube as a two-hop sankey
flow for the §5.2.7 Gap Dashboard. Reuses the pure builder
``build_material_regime_property_matrix`` (the same cube behind §15.5) and folds it into
material→regime and regime→property links whose ``value`` is the summed measurement
(evidence) count — the flow thickness. Names are resolved from the graph so the diagram
shows human labels, not ids.

Distinct ``/coverage/sankey`` path (own router, shared ``/api/v1/coverage`` prefix with
the sibling heatmap endpoint) so it never collides with ``/gaps`` nor the heavier
``/admin/coverage-matrix``. Strictly read-only: it never mutates the graph. Only base
columns (``property_name`` / ``verified`` / ``confidence`` / ``name``) are RETURNed,
matching the live Neo4j server profile used by the rest of the gap dashboard.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from fastapi import APIRouter, Query

from api_gateway.deps import get_store

router = APIRouter(prefix="/api/v1/coverage", tags=["coverage"])

# Node id prefixes keep the three axes in separate namespaces so a material and a
# property that happen to share a string never collapse into one sankey node.
_MAT = "m"
_REG = "r"
_PROP = "p"


def _name_map(store: Any, label: str) -> dict[str, str]:
    """id → display name for every node of ``label`` (falls back to id)."""
    rows = store.rows(
        "MATCH (n:Node) WHERE n.label=$lbl RETURN n.id, coalesce(n.name,'')",
        {"lbl": label},
    )
    return {r[0]: (r[1] or r[0]) for r in rows}


@router.get("/sankey")
def coverage_sankey(
    material_limit: int | None = Query(default=25, ge=1, le=200),
    min_evidence: int = Query(default=1, ge=0, le=1000),
    min_confidence: float | None = Query(default=None, ge=0.0, le=1.0),
    verified_only: bool = Query(default=False),
) -> dict:
    """Material → regime → property coverage flows, reshaped for a sankey (§17.14).

    Reuses ``build_material_regime_property_matrix`` and folds its cube into two layers
    of links whose ``value`` is the summed evidence (measurement) count — the flow
    thickness required by §5.2.7. ``material_limit`` caps the material axis to the top
    materials by total evidence (keeps the diagram readable and the payload bounded);
    ``min_evidence`` drops thin flows below that many measurements. ``min_confidence`` /
    ``verified_only`` are passed straight through to the builder's evidence filters.

    Returns ``nodes`` (each with ``id`` / ``label`` / ``layer`` 0..2 / ``kind`` /
    ``throughput`` / ``gap_count``) and ``links`` (``source`` / ``target`` node ids,
    ``value`` = evidence count, ``gap_value`` = flagged gaps on the pair). ``summary``
    rolls up the totals for the dashboard header.
    """
    from kg_retrievers.coverage_matrix_3d import (
        build_material_regime_property_matrix,
    )

    store = get_store()
    matrix = build_material_regime_property_matrix(
        store,
        min_confidence=min_confidence,
        verified_only=verified_only,
    )

    mat_names = _name_map(store, "Material")
    reg_names = _name_map(store, "ProcessingRegime")

    # Fold the cube into the two flow layers. Keys are the axis-id pairs; values sum
    # evidence (flow thickness) and gap flags separately.
    mr_ev: dict[tuple[str, str], int] = defaultdict(int)
    mr_gap: dict[tuple[str, str], int] = defaultdict(int)
    rp_ev: dict[tuple[str, str], int] = defaultdict(int)
    rp_gap: dict[tuple[str, str], int] = defaultdict(int)
    mat_total: dict[str, int] = defaultdict(int)  # total evidence per material

    for c in matrix.cells:
        ev = c.evidence_count
        gap = 1 if c.has_gap else 0
        if ev <= 0 and gap == 0:
            continue
        mat_total[c.material_id] += ev
        mr_ev[(c.material_id, c.regime_id)] += ev
        mr_gap[(c.material_id, c.regime_id)] += gap
        rp_ev[(c.regime_id, c.property_id)] += ev
        rp_gap[(c.regime_id, c.property_id)] += gap

    # Keep only the top materials by total evidence so the fan-out stays readable.
    ranked = sorted(mat_total.items(), key=lambda kv: (-kv[1], kv[0]))
    if material_limit is not None:
        ranked = ranked[:material_limit]
    keep_materials = {mid for mid, _ in ranked}

    # Build the surviving links (respecting material_limit + min_evidence), then derive
    # the node set from the endpoints that actually carry a link.
    links: list[dict[str, Any]] = []
    node_throughput: dict[str, int] = defaultdict(int)
    node_gap: dict[str, int] = defaultdict(int)
    live_regimes: set[str] = set()

    for (mid, rid), ev in mr_ev.items():
        if mid not in keep_materials or ev < min_evidence:
            continue
        src, dst = f"{_MAT}:{mid}", f"{_REG}:{rid}"
        links.append(
            {"source": src, "target": dst, "value": ev, "gap_value": mr_gap[(mid, rid)]}
        )
        node_throughput[src] += ev
        node_throughput[dst] += ev
        node_gap[src] += mr_gap[(mid, rid)]
        live_regimes.add(rid)

    for (rid, prop), ev in rp_ev.items():
        if rid not in live_regimes or ev < min_evidence:
            continue
        src, dst = f"{_REG}:{rid}", f"{_PROP}:{prop}"
        links.append(
            {"source": src, "target": dst, "value": ev, "gap_value": rp_gap[(rid, prop)]}
        )
        node_throughput[dst] += ev
        node_gap[dst] += rp_gap[(rid, prop)]

    # Only keep material→regime links whose regime survived a regime→property link,
    # so no flow dead-ends at a regime with nothing downstream.
    downstream_regimes = {
        lk["source"].split(":", 1)[1] for lk in links if lk["source"].startswith(f"{_REG}:")
    }

    def _dead_ends(lk: dict[str, Any]) -> bool:
        tgt = lk["target"]
        return tgt.startswith(f"{_REG}:") and tgt.split(":", 1)[1] not in downstream_regimes

    links = [lk for lk in links if not _dead_ends(lk)]

    referenced = {lk["source"] for lk in links} | {lk["target"] for lk in links}

    nodes: list[dict[str, Any]] = []
    for nid in sorted(referenced):
        kind, raw = nid.split(":", 1)
        if kind == _MAT:
            layer, label, node_kind = 0, mat_names.get(raw, raw), "material"
        elif kind == _REG:
            layer, label, node_kind = 1, reg_names.get(raw, raw), "regime"
        else:
            layer, label, node_kind = 2, raw, "property"
        nodes.append(
            {
                "id": nid,
                "raw_id": raw,
                "label": label,
                "layer": layer,
                "kind": node_kind,
                "throughput": node_throughput.get(nid, 0),
                "gap_count": node_gap.get(nid, 0),
            }
        )

    total_flow = sum(lk["value"] for lk in links)
    total_gap = sum(lk["gap_value"] for lk in links)
    return {
        "nodes": nodes,
        "links": links,
        "summary": {
            "materials": sum(1 for n in nodes if n["kind"] == "material"),
            "regimes": sum(1 for n in nodes if n["kind"] == "regime"),
            "properties": sum(1 for n in nodes if n["kind"] == "property"),
            "links": len(links),
            "total_evidence": total_flow,
            "total_gaps": total_gap,
        },
    }
