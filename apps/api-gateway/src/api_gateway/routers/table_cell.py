"""Table-cell Evidence endpoints — клик по числу → подсветка ячейки (§6.10/§8.3).

Тонкий роутер поверх :mod:`api_gateway.table_cell_resolver`: трассирует число к
исходной таблице (``table_id``/``row``/``col``) и отдаёт сетку с подсвеченной
ячейкой. RBAC повторяет Evidence Inspector: restricted-доказательства скрыты от
непривилегированных ролей (§6.2).

* ``GET  /api/v1/evidence/{evidence_id}/table-cell`` — по узлу Evidence.
* ``POST /api/v1/evidence/table-cell/resolve``       — по явному локатору (§3.6).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api_gateway.auth import current_role
from api_gateway.deps import get_store
from api_gateway.table_cell_resolver import resolve_locator, resolve_table_cell

router = APIRouter(prefix="/api/v1/evidence", tags=["evidence", "table-cell"])

_PRIVILEGED = {"researcher", "analyst", "project_manager", "admin", "curator"}
_RESTRICTED = {"internal", "restricted", "commercial_secret"}


@router.get("/{evidence_id}/table-cell")
def evidence_table_cell(evidence_id: str, role: str = Depends(current_role)) -> dict:
    """Trace a number back to the exact cell of its source table (§6.10/§8.3).

    Powers the «клик по числу → подсветка ячейки» demo: returns the reconstructed
    table grid plus the ``{row, col}`` to highlight. 404 if the evidence is
    unknown; 403 if it is restricted and the caller is not privileged.
    """
    store = get_store()
    nd = store.get_node(evidence_id)
    if nd is None:
        raise HTTPException(status_code=404, detail="evidence not found")
    if nd.get("confidentiality_level") in _RESTRICTED and role not in _PRIVILEGED:
        raise HTTPException(status_code=403, detail="restricted evidence — access denied")
    view = resolve_table_cell(store, evidence_id)
    if view is None:  # pragma: no cover - guarded by the get_node check above
        raise HTTPException(status_code=404, detail="evidence not found")
    return view.as_dict()


class LocatorBody(BaseModel):
    """Explicit table-cell locator (§3.6) for the «click a number» path."""

    doc_id: str = ""
    source_type: str = "table_cell"
    table_id: str | None = None
    row_index: int | None = None
    col_index: int | None = None
    page: int | None = None
    text: str = ""
    evidence_id: str | None = None


@router.post("/table-cell/resolve")
def resolve_table_cell_locator(body: LocatorBody, role: str = Depends(current_role)) -> dict:
    """Resolve an explicit locator to a highlighted source-table grid (§6.10/§8.3).

    For numbers that carry their own ``table_id``/row/col without a materialised
    Evidence node. Requires at least ``table_id`` so the grid can be reconstructed.
    """
    if not body.table_id:
        raise HTTPException(status_code=422, detail="table_id is required")
    view = resolve_locator(get_store(), body.model_dump())
    return view.as_dict()
