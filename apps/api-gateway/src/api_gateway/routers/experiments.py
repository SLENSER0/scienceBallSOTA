"""Experiments endpoint family (§14.8).

Экспериментальный слой графа: узлы ``Experiment`` связаны рёбрами
``USED_MATERIAL`` → Material, ``HAS_MEASUREMENT`` → Measurement и
``SUPPORTED_BY`` → Evidence. Endpoints list / detail / query / export / verify.

Experiment nodes carry custom props (protocol, operator, …) that are NOT
Kuzu columns, so read-templates RETURN base columns only and props are read
via :meth:`KuzuGraphStore.get_node`. Filtering + pagination are applied
in-process (demo-scale graph) so the same code path serves the hermetic
read-only fake used in tests.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from api_gateway.auth import current_role
from api_gateway.deps import get_store

router = APIRouter(prefix="/api/v1/experiments", tags=["experiments"])

_CURATOR = {"curator", "admin"}

# One aggregate read over all Experiment nodes: base columns + edge rollups.
# ``collect(DISTINCT m.name)`` first so the fake can disambiguate it from the
# per-experiment material/measurement templates below (§14.8 Kuzu note).
_LIST_CYPHER = (
    "MATCH (e:Node) WHERE e.label='Experiment' "
    "OPTIONAL MATCH (e)-[:Rel {type:'USED_MATERIAL'}]->(m:Node) "
    "OPTIONAL MATCH (e)-[:Rel {type:'HAS_MEASUREMENT'}]->(ms:Node) "
    "RETURN e.id, e.label, e.name, e.domain, "
    "collect(DISTINCT m.name), count(DISTINCT ms), collect(DISTINCT ms.property_name) "
    "LIMIT 1000"
)
_MATERIALS_CYPHER = (
    "MATCH (e:Node {id:$e})-[:Rel {type:'USED_MATERIAL'}]->(m:Node) RETURN m.id, m.name"
)
_MEASUREMENTS_CYPHER = (
    "MATCH (e:Node {id:$e})-[:Rel {type:'HAS_MEASUREMENT'}]->(ms:Node) "
    "RETURN ms.id, ms.name, ms.property_name, ms.value_normalized, ms.normalized_unit"
)
_EVIDENCE_COUNT_CYPHER = (
    "MATCH (e:Node {id:$e})-[:Rel {type:'SUPPORTED_BY'}]->(ev:Node) "
    "WHERE ev.label='Evidence' RETURN count(ev)"
)

_CSV_HEADER = ["id", "name", "property", "value", "unit"]


@dataclass(frozen=True)
class ExperimentSummary:
    """Одна строка списка экспериментов / one experiment list row (§14.8)."""

    id: str
    label: str | None
    name: str | None
    domain: str | None
    material: str | None  # representative USED_MATERIAL name (первый / first), if any
    n_measurements: int

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "label": self.label,
            "name": self.name,
            "domain": self.domain,
            "material": self.material,
            "n_measurements": self.n_measurements,
        }


def _clean_list(value: Any) -> list[str]:
    """Normalise a Kuzu ``collect(...)`` cell to a list of non-empty strings."""
    if value is None:
        return []
    items = value if isinstance(value, list) else [value]
    return [str(x) for x in items if x is not None]


def _row_matches(
    row: list[Any], material: str | None, prop: str | None, domain: str | None
) -> bool:
    """Filter one aggregate list row (domain exact-ci; material/property substring-ci)."""
    dom = row[3]
    materials = _clean_list(row[4])
    properties = _clean_list(row[6])
    if domain and (dom or "").lower() != domain.lower():
        return False
    if material and not any(material.lower() in m.lower() for m in materials):
        return False
    return not (prop and not any(prop.lower() in p.lower() for p in properties))


def _summary(row: list[Any]) -> ExperimentSummary:
    materials = _clean_list(row[4])
    return ExperimentSummary(
        id=row[0],
        label=row[1],
        name=row[2],
        domain=row[3],
        material=materials[0] if materials else None,
        n_measurements=int(row[5] or 0),
    )


def _list_payload(
    material: str | None, prop: str | None, domain: str | None, limit: int, offset: int
) -> dict:
    """Shared list/query implementation — filter then page over Experiment rows."""
    rows = get_store().rows(_LIST_CYPHER)
    matched = [r for r in rows if _row_matches(r, material, prop, domain)]
    limit = max(0, int(limit))
    offset = max(0, int(offset))
    page = matched[offset : offset + limit]
    return {
        "total": len(matched),
        "count": len(page),
        "limit": limit,
        "offset": offset,
        "items": [_summary(r).as_dict() for r in page],
    }


def _measurements(store: Any, eid: str) -> list[dict]:
    return [
        {"id": r[0], "name": r[1], "property": r[2], "value": r[3], "unit": r[4]}
        for r in store.rows(_MEASUREMENTS_CYPHER, {"e": eid})
    ]


def _require_experiment(store: Any, eid: str) -> dict:
    node = store.get_node(eid)
    if node is None or node.get("label") != "Experiment":
        raise HTTPException(status_code=404, detail="experiment not found")
    return node


@router.get("")
def list_experiments(
    material: str | None = None,
    property: str | None = None,  # public query name mirrors the spec (§14.8)
    domain: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """Paginated Experiment list with optional material/property/domain filters (§14.8)."""
    return _list_payload(material, property, domain, limit, offset)


class QueryFilters(BaseModel):
    material: str | None = None
    property: str | None = None
    domain: str | None = None


class QueryBody(BaseModel):
    filters: QueryFilters = QueryFilters()
    limit: int = 50
    offset: int = 0


@router.post("/query")
def query_experiments(body: QueryBody) -> dict:
    """POST form of the list endpoint for richer filter bodies (§14.8)."""
    f = body.filters
    return _list_payload(f.material, f.property, f.domain, body.limit, body.offset)


@router.get("/{eid}")
def experiment_detail(eid: str) -> dict:
    """Full experiment view: props + linked materials, measurements, evidence count (§14.8)."""
    store = get_store()
    node = _require_experiment(store, eid)
    materials = [{"id": r[0], "name": r[1]} for r in store.rows(_MATERIALS_CYPHER, {"e": eid})]
    measurements = _measurements(store, eid)
    ev_rows = store.rows(_EVIDENCE_COUNT_CYPHER, {"e": eid})
    evidence_count = int(ev_rows[0][0]) if ev_rows else 0
    return {
        "id": node["id"],
        "label": node.get("label"),
        "name": node.get("name"),
        "domain": node.get("domain"),
        "operation": node.get("operation"),
        "review_status": node.get("review_status"),
        "verified": node.get("verified"),
        "materials": materials,
        "measurements": measurements,
        "n_measurements": len(measurements),
        "evidence_count": evidence_count,
    }


@router.get("/{eid}/export")
def export_experiment(eid: str, format: str = "json"):  # type: ignore[no-untyped-def]
    """Export an experiment's measurements as CSV (stdlib csv) or JSON (§14.8)."""
    if format not in ("csv", "json"):
        raise HTTPException(status_code=400, detail="format must be csv or json")
    store = get_store()
    _require_experiment(store, eid)
    measurements = _measurements(store, eid)
    if format == "csv":
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(_CSV_HEADER)
        for m in measurements:
            writer.writerow([m["id"], m["name"], m["property"], m["value"], m["unit"]])
        headers = {"Content-Disposition": f'attachment; filename="{eid}.csv"'}
        return PlainTextResponse(buf.getvalue(), media_type="text/csv", headers=headers)
    return {"experiment_id": eid, "count": len(measurements), "measurements": measurements}


@router.post("/{eid}/verify")
def verify_experiment(eid: str, role: str = Depends(current_role)) -> dict:
    """Curator/admin stamps a verification flag on an experiment (§14.8 / §19)."""
    if role not in _CURATOR:
        raise HTTPException(status_code=403, detail="curator role required")
    store = get_store()
    _require_experiment(store, eid)
    store.upsert_node(eid, "Experiment", verified=True)
    return {"id": eid, "verified": True}
