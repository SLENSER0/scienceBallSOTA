"""Unit-normalization provenance for the Evidence Inspector (§7.9 / §5.2.6).

Surfaces *how* a measurement's canonical value was obtained: the
``normalization_method`` (direct | converted | rule | manual) and the
``unit_registry_version`` (content hash of the unit catalogue), plus the
canonical unit, its physical dimension and any curator flags. §7.9 asks for
these to be visible in the Evidence Inspector so a reader can trust — and
audit — the normalization behind a cited number.

Three endpoints:

- ``GET  /api/v1/unit-provenance/registry``       — current catalogue version +
  summary (which registry every conversion below is pinned to).
- ``GET  /api/v1/unit-provenance/measurement/{id}`` — provenance for a stored
  ``:Measurement`` node (live server / Neo4j :8000).
- ``POST /api/v1/unit-provenance/explain``        — pure-compute provenance for an
  ad-hoc ``value_raw``/``unit`` (preview, or when a node stores no raw value).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api_gateway.auth import current_role
from api_gateway.deps import get_store
from api_gateway.unit_provenance import (
    UnitProvenance,
    build_provenance,
    provenance_from_node,
)
from kg_common.units.normalization_method import METHODS
from kg_common.units.registry import DIMENSIONS, UNIT_REGISTRY, registry_version

router = APIRouter(prefix="/api/v1/unit-provenance", tags=["unit-provenance"])


class ProvenanceResponse(BaseModel):
    """Full normalization provenance for one measurement (§7.9)."""

    property_id: str | None = None
    value_raw: object = None
    value: float | None = None
    unit: str | None = None
    value_normalized: float | None = None
    normalized_unit: str | None = None
    normalization_method: str
    method_reason: str
    unit_registry_version: str
    dimension: str | None = None
    policy_canonical_unit: str | None = None
    registry_canonical_unit: str | None = None
    in_range: bool
    review_needed: bool
    flags: list[str] = Field(default_factory=list)
    normalized_at: str = ""

    @classmethod
    def of(cls, prov: UnitProvenance) -> ProvenanceResponse:
        return cls(**prov.as_dict())


class ExplainRequest(BaseModel):
    value_raw: object = Field(..., description="Raw value, e.g. 46.5 or '46.5'")
    unit: str | None = Field(None, description="Raw unit token, e.g. 'ksi' (None ⇒ missing)")
    property_id: str | None = Field(
        None, description="Canonical property id, e.g. 'prop:tensile_strength'"
    )
    manual: bool = Field(False, description="Value fixed by a curator (pins method=manual)")


@router.get("/registry")
def registry_summary(_role: str = Depends(current_role)) -> dict:
    """Current unit-catalogue version + summary — pins every conversion (§7.11)."""
    return {
        "unit_registry_version": registry_version(),
        "unit_count": len(UNIT_REGISTRY),
        "dimensions": list(DIMENSIONS),
        "canonical_units": sorted(UNIT_REGISTRY),
        "methods": sorted(METHODS),
    }


@router.post("/explain", response_model=ProvenanceResponse)
def explain(req: ExplainRequest, _role: str = Depends(current_role)) -> ProvenanceResponse:
    """Full-engine provenance for an ad-hoc measurement (§7.9) — pure compute.

    Runs the same engine ingestion should use: reduced normalizer for the value,
    plus method + registry-version + dimension. Never raises on bad input — an
    unparseable value simply yields ``value_normalized=None`` with flags.
    """
    prov = build_provenance(
        req.value_raw,
        req.unit,
        property_id=req.property_id,
        manual=req.manual,
    )
    return ProvenanceResponse.of(prov)


@router.get("/measurement/{measurement_id}", response_model=ProvenanceResponse)
def measurement_provenance(
    measurement_id: str, _role: str = Depends(current_role)
) -> ProvenanceResponse:
    """Normalization provenance for a stored ``:Measurement`` node (§7.9).

    Powers the Evidence Inspector: re-derives ``normalization_method`` and pins
    the ``unit_registry_version`` for the number the reader is citing. A node
    already marked ``normalization_method="manual"`` keeps that label.
    """
    node = get_store().get_node(measurement_id)
    if node is None:
        raise HTTPException(status_code=404, detail="measurement not found")
    if node.get("label") != "Measurement":
        raise HTTPException(
            status_code=400,
            detail=f"node {measurement_id!r} is not a Measurement (label={node.get('label')!r})",
        )
    prov = provenance_from_node(node)
    return ProvenanceResponse.of(prov)
