"""Parametric graph-query templates → live subgraph + generated Cypher (§17.8/§6.2).

Демонстрирует ядро §6.2 «материал + режим + свойство»: слева в Graph Explorer
(§17.8) исследователь выбирает готовый шаблон, заполняет параметрическую форму
(материал, операция режима, свойство) и получает конверт §6.2 —
``summary`` / ``experiments`` / ``gaps`` / ``graph`` — плюс РЕАЛЬНО сгенерированный
и исполненный Cypher в ``queryContext.generatedCypher`` (раскрываемый блок §14.6).

This router is the missing glue between three pieces that already existed but were
never wired to the live graph:

* :mod:`api_gateway.graph_query_presets`  — the left-sidebar preset catalogue
  (``material_regime_property``) with its parameter-form field schemas.
* :mod:`api_gateway.graph_query_body`     — validates the §6.2 request body the
  form values are folded into (``query_type``, ``material``, nested
  ``processing``, ``property``, ``filters``).
* :mod:`api_gateway.query_context`        — the §5.3 ``queryContext`` transparency
  carrier (``userQuery`` / ``filters`` / ``generatedCypher``).

Every executed query is a *parameterized*, read-only traversal over the shared
``:Node`` / ``:Rel`` model (works on both the embedded Kuzu store and the server
Neo4j store), hardened by :func:`graph_service.cypher_guard.guard_read_query`
(mutating clause / missing ``LIMIT`` → refused) before it ever reaches the graph.
The material name is matched over ``name`` / ``canonical_name`` / ``aliases_text``;
the property over the measurement's ``property_name``; the regime over the
processing regime's ``operation`` (and optional ``temperature_c``). No free-form
Text2Cypher is ever accepted — only named presets with bound parameters (§19.6).
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from api_gateway.deps import get_store
from api_gateway.graph_query_body import parse_graph_query
from api_gateway.graph_query_presets import build_request, get_preset, list_presets
from api_gateway.query_context import QueryContext

router = APIRouter(prefix="/api/v1/graph", tags=["graph-templates"])

# Canonical relationship types this template traverses (§8.2 / seed conventions):
# a Measurement points ABOUT_MATERIAL → Material and ABOUT_REGIME → ProcessingRegime,
# a Gap points ABOUT_MATERIAL → Material and ABOUT_REGIME → ProcessingRegime.
_REL_ABOUT_MATERIAL = "ABOUT_MATERIAL"
_REL_ABOUT_REGIME = "ABOUT_REGIME"

_MAX_LIMIT = 500
_DEFAULT_LIMIT = 200

# Presets this router can actually execute (others are catalogue-only for now).
_EXECUTABLE = {"material_regime_property", "property_material"}


# -- request model -------------------------------------------------------------
class TemplateRunRequest(BaseModel):
    """Left-sidebar parameter-form submission (§17.8).

    ``key`` selects the preset; the remaining fields are its form values. Empty
    strings are treated as "unset" so a blank optional field is simply omitted.
    """

    key: str = Field(default="material_regime_property")
    material: str | None = None
    property: str | None = None
    operation: str | None = None
    temperature_c: float | None = None
    min_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    limit: int = Field(default=_DEFAULT_LIMIT, ge=1, le=_MAX_LIMIT)


# -- helpers -------------------------------------------------------------------
def _clean(value: str | None) -> str | None:
    """Trim a form string; treat blank as unset (``None``)."""
    if value is None:
        return None
    text = value.strip()
    return text or None


def _norm_evidence_ids(value: Any) -> list[str]:
    """Normalise an edge ``evidence_ids`` cell (list from Neo4j, JSON str from Kuzu)."""
    if isinstance(value, list):
        return [str(x) for x in value]
    if isinstance(value, str) and value:
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        return [str(x) for x in parsed] if isinstance(parsed, list) else []
    return []


def _material_filter(alias: str, param: str) -> str:
    """Case-insensitive material match over name / canonical_name / aliases_text."""
    return (
        f"(lower(coalesce({alias}.name, '')) CONTAINS ${param}\n"
        f"       OR lower(coalesce({alias}.canonical_name, '')) CONTAINS ${param}\n"
        f"       OR lower(coalesce({alias}.aliases_text, '')) CONTAINS ${param})"
    )


def _build_material_regime_property(
    *,
    material: str,
    property_name: str | None,
    operation: str | None,
    temperature_c: float | None,
    min_confidence: float,
    limit: int,
) -> tuple[str, dict[str, Any]]:
    """Render the ``material_regime_property`` traversal → (cypher, bound params).

    All variable inputs are bound parameters (never string-interpolated) — the
    only interpolated value is the literal integer ``LIMIT``. When a regime
    ``operation`` is supplied the regime match is *required* (and optionally
    constrained by ``temperature_c``); otherwise it is an ``OPTIONAL MATCH`` so
    measurements without a linked regime still surface.
    """
    params: dict[str, Any] = {"material": material.lower()}
    where = [
        "meas.label = 'Measurement'",
        "mat.label = 'Material'",
        _material_filter("mat", "material"),
    ]
    if property_name:
        params["property"] = property_name.lower()
        where.append("lower(coalesce(meas.property_name, '')) CONTAINS $property")
    if min_confidence > 0.0:
        params["min_confidence"] = min_confidence
        where.append("coalesce(meas.confidence, 0.0) >= $min_confidence")

    lines = [
        f"MATCH (meas:Node)-[:Rel {{type: '{_REL_ABOUT_MATERIAL}'}}]->(mat:Node)",
        "WHERE " + "\n  AND ".join(where),
    ]

    if operation:
        params["operation"] = operation.lower()
        reg_where = [
            "reg.label = 'ProcessingRegime'",
            "lower(coalesce(reg.operation, '')) CONTAINS $operation",
        ]
        if temperature_c is not None:
            params["temperature_c"] = temperature_c
            reg_where.append("reg.temperature_c = $temperature_c")
        lines.append(f"MATCH (meas)-[:Rel {{type: '{_REL_ABOUT_REGIME}'}}]->(reg:Node)")
        lines.append("WHERE " + "\n  AND ".join(reg_where))
    else:
        lines.append(f"OPTIONAL MATCH (meas)-[:Rel {{type: '{_REL_ABOUT_REGIME}'}}]->(reg:Node)")

    lines.append(
        "RETURN DISTINCT mat.id AS material_id, meas.id AS measurement_id, reg.id AS regime_id"
    )
    lines.append(f"LIMIT {int(limit)}")
    return "\n".join(lines), params


def _build_property_material(
    *, property_name: str, min_confidence: float, limit: int
) -> tuple[str, dict[str, Any]]:
    """Render the ``property_material`` traversal (materials exhibiting a property)."""
    params: dict[str, Any] = {"property": property_name.lower()}
    where = [
        "meas.label = 'Measurement'",
        "mat.label = 'Material'",
        "lower(coalesce(meas.property_name, '')) CONTAINS $property",
    ]
    if min_confidence > 0.0:
        params["min_confidence"] = min_confidence
        where.append("coalesce(meas.confidence, 0.0) >= $min_confidence")
    cypher = (
        f"MATCH (meas:Node)-[:Rel {{type: '{_REL_ABOUT_MATERIAL}'}}]->(mat:Node)\n"
        "WHERE " + "\n  AND ".join(where) + "\n"
        f"OPTIONAL MATCH (meas)-[:Rel {{type: '{_REL_ABOUT_REGIME}'}}]->(reg:Node)\n"
        "RETURN DISTINCT mat.id AS material_id, meas.id AS measurement_id, reg.id AS regime_id\n"
        f"LIMIT {int(limit)}"
    )
    return cypher, params


def _measurement_record(store: Any, meas_id: str) -> dict[str, Any]:
    """Build one §6.2 ``experiment`` record from a measurement node."""
    nd = store.get_node(meas_id) or {}
    return {
        "id": meas_id,
        "name": nd.get("name") or nd.get("canonical_name") or meas_id,
        "property": nd.get("property_name"),
        "value": nd.get("value_normalized"),
        "unit": nd.get("normalized_unit") or nd.get("unit"),
        "valueRaw": nd.get("value_raw"),
        "confidence": nd.get("confidence"),
        "polarity": nd.get("polarity"),
        "domain": nd.get("domain"),
        "reviewStatus": nd.get("review_status"),
        "evidenceIds": [],
    }


def _attach_evidence(store: Any, records: dict[str, dict[str, Any]]) -> None:
    """Fold provenance edge ``evidence_ids`` into each measurement record in place."""
    ids = list(records)
    if not ids:
        return
    try:
        rows = store.rows(
            "MATCH (m:Node)-[r:Rel]->(x:Node) "
            "WHERE m.id IN $ids AND r.evidence_ids IS NOT NULL "
            "RETURN m.id, r.evidence_ids",
            {"ids": ids},
        )
    except Exception:
        return
    for mid, raw in rows:
        rec = records.get(str(mid))
        if rec is None:
            continue
        seen = set(rec["evidenceIds"])
        for ev in _norm_evidence_ids(raw):
            if ev not in seen:
                rec["evidenceIds"].append(ev)
                seen.add(ev)


def _gap_records(
    store: Any, material_ids: list[str], regime_ids: list[str]
) -> list[dict[str, Any]]:
    """Gap nodes about the matched materials or their regimes (§6.2 gaps envelope)."""
    gap_ids: dict[str, None] = {}
    if material_ids:
        try:
            for r in store.rows(
                f"MATCH (g:Node)-[:Rel {{type: '{_REL_ABOUT_MATERIAL}'}}]->(mat:Node) "
                "WHERE g.label = 'Gap' AND mat.id IN $ids RETURN DISTINCT g.id",
                {"ids": material_ids},
            ):
                gap_ids.setdefault(str(r[0]), None)
        except Exception:
            pass
    if regime_ids:
        try:
            for r in store.rows(
                f"MATCH (g:Node)-[:Rel {{type: '{_REL_ABOUT_REGIME}'}}]->(reg:Node) "
                "WHERE g.label = 'Gap' AND reg.id IN $ids RETURN DISTINCT g.id",
                {"ids": regime_ids},
            ):
                gap_ids.setdefault(str(r[0]), None)
        except Exception:
            pass
    gaps: list[dict[str, Any]] = []
    for gid in gap_ids:
        nd = store.get_node(gid) or {}
        gaps.append(
            {
                "id": gid,
                "name": nd.get("name") or gid,
                "gapType": nd.get("gap_type"),
                "domain": nd.get("domain"),
                "reviewStatus": nd.get("review_status"),
            }
        )
    return gaps


def _human_query(
    preset_title: str, material: str | None, operation: str | None, property_name: str | None
) -> str:
    """A one-line natural-language echo of the parametric query (queryContext.userQuery)."""
    parts: list[str] = [preset_title]
    if material:
        parts.append(f"материал «{material}»")
    if operation:
        parts.append(f"режим «{operation}»")
    if property_name:
        parts.append(f"свойство «{property_name}»")
    return " · ".join(parts)


# -- endpoints -----------------------------------------------------------------
@router.get("/templates")
def graph_templates() -> dict:
    """List the left-sidebar query-template presets and their parameter-form schemas (§17.8)."""
    presets = [p.as_dict() for p in list_presets()]
    for preset in presets:
        preset["executable"] = preset["key"] in _EXECUTABLE
    return {"templates": presets}


@router.post("/templates/run")
def run_graph_template(req: TemplateRunRequest) -> dict:
    """Execute a parametric template → §6.2 envelope + generated Cypher (§17.8/§14.6).

    Folds the form values into a validated §6.2 body (:mod:`graph_query_body`),
    renders a read-only parameterized Cypher, hardens it through the read-path
    guard, runs it on the live graph, and returns
    ``{summary, experiments, gaps, graph, queryContext}`` where
    ``queryContext.generatedCypher`` is the exact query that was executed.
    """
    from graph_service.cypher_guard import CypherGuardError, guard_read_query

    key = req.key
    preset = get_preset(key)
    if preset is None:
        raise HTTPException(status_code=404, detail=f"unknown template: {key!r}")
    if key not in _EXECUTABLE:
        raise HTTPException(status_code=400, detail=f"template {key!r} is not executable yet")

    # Cleaned, blank-aware form values drive the *executable* query: a blank
    # optional field must stay unset (an unfilled "regime" must not silently
    # force an ``operation`` filter), so we do not let preset defaults leak in.
    material = _clean(req.material)
    property_name = _clean(req.property)
    operation = _clean(req.operation)
    temperature_c = req.temperature_c

    # Fold the supplied values into (and validate against) the §6.2 request body so
    # the query_type is contract-checked and the transparency echo is canonical.
    form_values: dict[str, object] = {}
    if material is not None:
        form_values["material"] = material
    if property_name is not None:
        form_values["property"] = property_name
    if operation is not None:
        form_values["operation"] = operation
    if temperature_c is not None:
        form_values["temperature_c"] = temperature_c
    try:
        body = parse_graph_query(build_request(key, form_values))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if key == "material_regime_property":
        if not material:
            raise HTTPException(status_code=422, detail="material is required")
        cypher, params = _build_material_regime_property(
            material=material,
            property_name=property_name,
            operation=operation,
            temperature_c=temperature_c,
            min_confidence=req.min_confidence,
            limit=req.limit,
        )
    else:  # property_material
        if not property_name:
            raise HTTPException(status_code=422, detail="property is required")
        cypher, params = _build_property_material(
            property_name=property_name, min_confidence=req.min_confidence, limit=req.limit
        )

    # Defense-in-depth: refuse anything but a read-only, LIMIT-bounded query (§19.6).
    try:
        cypher = guard_read_query(cypher, max_rows=_MAX_LIMIT)
    except CypherGuardError as exc:  # pragma: no cover - templates are audited
        raise HTTPException(status_code=500, detail=f"generated query rejected: {exc}") from exc

    store = get_store()
    try:
        rows = store.rows(cypher, params)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"graph query failed: {exc}") from exc

    # Collect ids (order-preserving) from the (material_id, measurement_id, regime_id) rows.
    material_ids: dict[str, None] = {}
    measurement_ids: dict[str, None] = {}
    regime_ids: dict[str, None] = {}
    for row in rows:
        mat_id, meas_id, reg_id = ([*row, None, None, None])[:3]
        if mat_id:
            material_ids.setdefault(str(mat_id), None)
        if meas_id:
            measurement_ids.setdefault(str(meas_id), None)
        if reg_id:
            regime_ids.setdefault(str(reg_id), None)

    # Experiments (measurements + values + evidence).
    records = {mid: _measurement_record(store, mid) for mid in measurement_ids}
    _attach_evidence(store, records)
    experiments = list(records.values())

    gaps = _gap_records(store, list(material_ids), list(regime_ids))

    # Subgraph of everything touched (material + measurements + regimes + gaps).
    seed_ids = [
        *material_ids,
        *measurement_ids,
        *regime_ids,
        *(g["id"] for g in gaps),
    ]
    graph = store.subgraph_from_ids(list(dict.fromkeys(seed_ids)), expand=0)

    evidence_total = sorted({ev for rec in experiments for ev in rec["evidenceIds"]})

    # Transparency block: verbatim generated Cypher + the applied filters (§5.3/§14.6).
    ctx = QueryContext(
        user_query=_human_query(preset.title, material, operation, property_name),
        filters={"queryType": body.query_type, **params},
        generated_cypher=cypher,
    )
    query_context = ctx.as_dict()
    graph.query_context = query_context

    summary = {
        "queryType": body.query_type,
        "materialsMatched": len(material_ids),
        "measurements": len(measurement_ids),
        "regimes": len(regime_ids),
        "gaps": len(gaps),
        "evidence": len(evidence_total),
        "text": (
            f"Найдено измерений: {len(measurement_ids)} по {len(material_ids)} материал(ам); "
            f"режимов: {len(regime_ids)}; пробелов: {len(gaps)}; "
            f"свидетельств: {len(evidence_total)}."
        ),
    }

    return {
        "summary": summary,
        "experiments": experiments,
        "gaps": gaps,
        "graph": graph.model_dump(by_alias=True),
        "queryContext": query_context,
    }
