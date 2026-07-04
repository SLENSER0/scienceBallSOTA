"""Incremental entity-resolution step API (§8.10).

Surfaces the ingestion ER step (``ingestion_service.er_step``) — Step 6 of the
§9.1 flow ``NORMALIZE --> ER --> VALIDATE`` — over HTTP so the pipeline stage is
inspectable and demonstrable on the live graph (server profile, Neo4j :8000):

* ``GET  /api/v1/ingestion/er/status``   — config + supported types.
* ``GET  /api/v1/ingestion/er/preview``  — dry-run ER over existing canonicals of
  a type; shows the merge groups the resolver would propose (read-only).
* ``POST /api/v1/ingestion/er/run``      — resolve caller-supplied *new* mentions
  incrementally against existing canonicals; ``apply=true`` folds auto-merge
  groups into their canonical via the tested ``CurationService.merge_entities``.
* ``POST /api/v1/ingestion/er/demo``     — the §8.10 acceptance scenario: a second
  document's ``AA2024`` mention merges into the existing ``material:al-cu-2024``
  without creating a duplicate.

The ``review_needed`` / ``separate`` decisions never block: they are reported but
not applied, matching the pipeline contract.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from api_gateway.deps import get_store

router = APIRouter(prefix="/api/v1/ingestion/er", tags=["entity-resolution"])

_CANONICAL_ID = "material:al-cu-2024"
_DEMO_NEW_ID = "material:aa2024-doc2"


# --------------------------------------------------------------------------- #
# Schemas                                                                      #
# --------------------------------------------------------------------------- #
class MentionIn(BaseModel):
    unique_id: str | None = None
    name: str | None = None
    formula: str | None = None
    designation: str | None = None
    alloy_family: str | None = None
    manufacturer: str | None = None
    model: str | None = None
    orcid: str | None = None
    org: str | None = None


class ERRunBody(BaseModel):
    entity_type: str = "Material"
    mentions: list[MentionIn] = Field(default_factory=list)
    apply: bool = False


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #
def _curation():  # type: ignore[no-untyped-def]
    from curation_service.curation import CurationService

    return CurationService(get_store())


def _to_mentions(items: list[MentionIn]) -> list[dict[str, Any]]:
    from kg_common import make_id

    out: list[dict[str, Any]] = []
    for i, m in enumerate(items):
        d = m.model_dump(exclude_none=True)
        uid = d.get("unique_id") or make_id("Material", f"mention:{m.name or i}")
        d["unique_id"] = uid
        out.append(d)
    return out


def _count_material_formula(store: Any, formula_key: str) -> int:
    """How many Material nodes carry a given (raw) formula — duplicate probe."""
    try:
        rows = store.rows(
            "MATCH (n:Node) WHERE n.label = 'Material' AND n.formula = $f RETURN count(n)",
            {"f": formula_key},
        )
    except Exception:
        return -1
    return int(rows[0][0]) if rows and rows[0] else 0


# --------------------------------------------------------------------------- #
# Endpoints                                                                    #
# --------------------------------------------------------------------------- #
@router.get("/status")
def er_status() -> dict[str, Any]:
    """Report ER-step config + supported entity types (§8.10)."""
    from ingestion_service.er_step import SUPPORTED_TYPES, ERStepConfig

    cfg = ERStepConfig.from_env()
    return {
        "supported_types": list(SUPPORTED_TYPES),
        "config": {
            "incremental": cfg.incremental,
            "retrain_on_schedule": cfg.retrain_on_schedule,
            "threshold": cfg.threshold,
            "max_existing": cfg.max_existing,
        },
        "pipeline_position": "Step 6 (NORMALIZE → ER → VALIDATE)",
    }


@router.get("/preview")
def er_preview(
    type: str = Query(default="Material"),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    """Dry-run ER over existing canonicals of *type* (read-only, §8.10 preview)."""
    from ingestion_service.er_step import SUPPORTED_TYPES, pull_existing, resolve_incremental

    entity_type = type if type in SUPPORTED_TYPES else "Material"
    store = get_store()
    existing = pull_existing(store, entity_type)
    # Full pass: treat all canonicals as the incoming batch against an empty base
    # so every candidate merge group (and its canonical id) is surfaced.
    decisions = resolve_incremental(entity_type, existing, [])
    decisions.sort(key=lambda d: d.match_probability, reverse=True)
    payload = [d.as_dict() for d in decisions[:limit]]
    by_decision: dict[str, int] = {}
    for d in decisions:
        by_decision[d.decision] = by_decision.get(d.decision, 0) + 1
    return {
        "entity_type": entity_type,
        "n_existing": len(existing),
        "n_groups": len(decisions),
        "by_decision": by_decision,
        "decisions": payload,
    }


@router.post("/run")
def er_run(body: ERRunBody) -> dict[str, Any]:
    """Incrementally resolve new mentions against existing canonicals (§8.10).

    When ``apply=true``, auto-merge groups that fold a new mention into an
    existing canonical are applied via ``CurationService.merge_entities``.
    """
    from ingestion_service.er_step import (
        SUPPORTED_TYPES,
        ERStepConfig,
        apply_merges,
        run_er_step,
    )

    if body.entity_type not in SUPPORTED_TYPES:
        raise HTTPException(status_code=400, detail=f"unsupported type {body.entity_type!r}")
    if not body.mentions:
        raise HTTPException(status_code=400, detail="mentions required")

    store = get_store()
    mentions = _to_mentions(body.mentions)
    report = run_er_step(
        {body.entity_type: mentions},
        store,
        extraction_run_id="er-run-api",
        config=ERStepConfig.from_env(),
    )
    applied: list[dict[str, Any]] = []
    if body.apply:
        applied = apply_merges(report, _curation().merge_entities, actor="er_api")
    out = report.as_dict()
    out["applied"] = applied
    return out


@router.post("/demo")
def er_demo() -> dict[str, Any]:
    """§8.10 acceptance demo: second doc's ``AA2024`` merges into the existing
    ``material:al-cu-2024`` — no duplicate created.

    Seeds the existing canonical if absent, upserts a fresh ``AA2024`` node as if a
    second document introduced it, runs the incremental ER step with apply, then
    proves only one Material with that composition survives.
    """
    from ingestion_service.er_step import apply_merges, node_to_mention, run_er_step

    store = get_store()

    # 1) ensure the existing canonical (as if ingested from document #1)
    if store.get_node(_CANONICAL_ID) is None:
        store.upsert_node(
            _CANONICAL_ID,
            "Material",
            name="Сплав Al-Cu 2024 (Д16)",
            canonical_name="Al-Cu 2024",
            formula="Al2Cu",
            designation="2024",
            confidence=0.7,
        )

    # 2) second document introduces the same alloy under a different surface form
    store.upsert_node(
        _DEMO_NEW_ID,
        "Material",
        name="AA2024",
        canonical_name="AA2024",
        formula="Al2Cu",
        designation="2024",
        confidence=0.5,
    )
    before = _count_material_formula(store, "Al2Cu")

    # 3) run the incremental ER step over just the new mention
    new_node = store.get_node(_DEMO_NEW_ID) or {}
    new_mention = node_to_mention(new_node)
    report = run_er_step(
        {"Material": [new_mention] if new_mention else []},
        store,
        extraction_run_id="er-demo-doc2",
    )
    applied = apply_merges(report, _curation().merge_entities, actor="er_demo")

    after = _count_material_formula(store, "Al2Cu")
    duplicate_survives = store.get_node(_DEMO_NEW_ID) is not None
    canonical = store.get_node(_CANONICAL_ID) or {}
    return {
        "scenario": "second document AA2024 → material:al-cu-2024",
        "canonical_id": _CANONICAL_ID,
        "material_al2cu_before": before,
        "material_al2cu_after": after,
        "duplicate_removed": (not duplicate_survives),
        "merged_without_duplicate": (after == 1 and not duplicate_survives),
        "canonical_aliases": canonical.get("aliases_text") or canonical.get("aliases"),
        "report": report.as_dict(),
        "applied": applied,
    }
