"""Schema-constrained graph extraction — PropertyGraphIndex whitelist (§6.11).

Surfaces the domain graph-extraction whitelist (§8.1 entities / §8.2 relations)
and the schema filter that keeps LlamaIndex ``SchemaLLMPathExtractor`` honest:
only whitelisted triplets survive, off-schema triplets are dropped. The heavy
lifting lives in :mod:`kg_extractors.graph.property_graph` (the module §6.11
asks for) — this router is a thin HTTP shell over it plus two *live-graph*
diagnostics that prove the guarantee on real Neo4j data (server-profile :8000):

* ``GET  /schema``        — the machine-readable whitelist + validation triples.
* ``POST /constrain``     — apply the schema filter to candidate triplets (any
  profile, no DB): kept vs rejected-with-reason. This is the SchemaLLMPathExtractor
  ``strict=True`` behaviour exposed for inspection / testing.
* ``GET  /sample-path``   — synthesize the canonical ``Sample`` pivot path for an
  experiment (``Experiment-USES_SAMPLE->Sample-{HAS_MATERIAL,PROCESSED_BY}->…``).
* ``GET  /audit``         — scan the live graph's edge signatures and classify each
  against the §8.2 ontology: how many triplets conform, which violate.
* ``GET  /live-sample-paths`` — take real specimen pivots in Neo4j (a Material with
  Measurements, optionally a ProcessingRegime), re-express them as the canonical
  §8.2 ``Sample`` pivot and re-validate against the schema.

The extractor never auto-upserts (§6.11): output is meant to flow through the
span-validator (§6.10) + curation orchestrator (§6.13), not straight to Neo4j.
Prefix ``/property-graph`` does not collide with ``/graph`` or ``/graph-ext``.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from api_gateway.deps import get_store
from kg_common import get_logger, get_settings
from kg_extractors.graph import property_graph as pg
from kg_schema.relationships import is_valid_edge

router = APIRouter(prefix="/api/v1/property-graph", tags=["property-graph"])

_log = get_logger("api.property_graph")

# Distinct edge signatures scanned from the live graph are capped — a handful of
# hundred distinct (label, rel, label) triples already covers the whole schema.
_AUDIT_SIG_LIMIT = 500


def _is_server() -> bool:
    return get_settings().runtime_profile == "server"


def _require_server() -> Any:
    if not _is_server():
        raise HTTPException(
            status_code=409,
            detail=(
                "Аудит живого графа доступен только на server-профиле (Neo4j :8000). "
                "На embedded используйте /api/v1/property-graph/constrain (без БД)."
            ),
        )
    return get_store()


# ---------------------------------------------------------------------------
# GET /schema — the whitelist
# ---------------------------------------------------------------------------


@router.get("/schema")
def schema() -> dict:
    """The domain graph-extraction whitelist (§6.11 / §8.1 / §8.2).

    Returns the entity types, relationship types and the allowed
    ``(subject, relation, object)`` validation triples — exactly what constrains
    ``SchemaLLMPathExtractor``. ``llama_index_available`` tells the UI whether a
    live LLM-driven extractor can be built or only the pure filter is active.
    """
    sch = pg.domain_schema()
    out = sch.as_dict()
    out["extractor"] = "SchemaLLMPathExtractor"
    out["index"] = "PropertyGraphIndex"
    out["strict"] = True
    out["llama_index_available"] = pg.llama_index_available()
    return out


# ---------------------------------------------------------------------------
# POST /constrain — apply the schema filter to candidate triplets
# ---------------------------------------------------------------------------


class TripletIn(BaseModel):
    """One candidate graph triplet (as an LLM extractor would emit)."""

    subject: str = Field(..., description="subject node id or surface name")
    subject_type: str = Field(..., description="§8.1 node label of the subject")
    relation: str = Field(..., description="§8.2 relationship type")
    object: str = Field(..., description="object node id or surface name")
    object_type: str = Field(..., description="§8.1 node label of the object")


class ConstrainRequest(BaseModel):
    triplets: list[TripletIn] = Field(default_factory=list)


@router.post("/constrain")
def constrain(req: ConstrainRequest) -> dict:
    """Apply the schema whitelist to candidate triplets — keep conforming, drop rest.

    Mirrors ``SchemaLLMPathExtractor(strict=True)``: a triplet survives only if its
    ``(subject_type, relation, object_type)`` signature is a declared graph path
    (§8.2). Everything else lands in ``rejected`` with a reason. Pure/deterministic,
    needs no LLM and no DB — the cleanliness guarantee of §6.11 in isolation.
    """
    triplets = [
        pg.Triplet(
            subject=t.subject,
            subject_type=t.subject_type,
            relation=t.relation,
            object=t.object,
            object_type=t.object_type,
        )
        for t in req.triplets
    ]
    result = pg.constrain_triplets(triplets)
    _log.info(
        "property_graph.constrain",
        total=len(triplets),
        kept=len(result.kept),
        rejected=len(result.rejected),
    )
    return result.as_dict()


# ---------------------------------------------------------------------------
# GET /sample-path — synthesize the canonical Sample pivot path
# ---------------------------------------------------------------------------


@router.get("/sample-path")
def sample_path(
    experiment_id: str = Query(..., description="id узла Experiment"),
    material_id: str | None = Query(default=None, description="id узла Material (опц.)"),
    regime_id: str | None = Query(default=None, description="id узла ProcessingRegime (опц.)"),
    measurement_ids: list[str] | None = Query(default=None, description="id узлов Measurement"),
) -> dict:
    """Synthesize the canonical §8.2 ``Sample`` pivot path for one experiment (§6.11).

    Emits ``Experiment-USES_SAMPLE->Sample``, then ``Sample-HAS_MATERIAL->Material``
    / ``Sample-PROCESSED_BY->ProcessingRegime`` and ``Experiment-MEASURED->Measurement``.
    The ``sample_id`` is deterministic (idempotent re-ingest). The returned path is
    whitelisted by construction, so ``constrain`` reports zero rejects for it —
    included as ``constrained`` for proof.
    """
    path = pg.synthesize_sample_path(
        experiment_id,
        material_id=material_id,
        regime_id=regime_id,
        measurement_ids=list(measurement_ids) if measurement_ids else None,
    )
    result = pg.constrain_triplets(path)
    return {
        "experiment_id": experiment_id,
        "sample_id": path[0].object,
        "path": [
            {
                "subject": t.subject,
                "subject_type": t.subject_type,
                "relation": t.relation,
                "object": t.object,
                "object_type": t.object_type,
            }
            for t in path
        ],
        "constrained": result.as_dict(),
    }


# ---------------------------------------------------------------------------
# GET /audit — classify live-graph edge signatures against the schema
# ---------------------------------------------------------------------------


@router.get("/audit")
def audit(
    limit: int = Query(default=_AUDIT_SIG_LIMIT, ge=1, le=2000),
    examples: int = Query(default=20, ge=0, le=200, description="сколько нарушений показать"),
) -> dict:
    """Scan the live graph's edge signatures and classify against §8.2 (§6.11).

    Aggregates every distinct ``(subject_label)-[rel]->(object_label)`` on the live
    Neo4j graph and marks each ``valid`` (in the canonical §8.2 ontology via
    ``is_valid_edge``) or ``violating``, plus ``in_extraction_whitelist`` (inside
    the §6.11 extraction subset). This is the schema-validation §8 receipt: it
    quantifies how clean the graph is and lists the off-schema triplets a
    schema-constrained extractor would have prevented.
    """
    store = _require_server()
    rows = store.rows(
        "MATCH (a:Node)-[r:Rel]->(b:Node) "
        "WHERE a.label IS NOT NULL AND b.label IS NOT NULL AND r.type IS NOT NULL "
        "RETURN a.label AS s, r.type AS rel, b.label AS o, count(*) AS n "
        "ORDER BY n DESC "
        f"LIMIT {int(limit)}",
        {},
    )
    sch = pg.domain_schema()
    signatures: list[dict] = []
    violating: list[dict] = []
    total_edges = 0
    valid_edges = 0
    for s, rel, o, n in rows:
        n = int(n)
        total_edges += n
        valid = is_valid_edge(str(s), str(rel), str(o))
        if valid:
            valid_edges += n
        in_wl = sch.allows(str(s), str(rel), str(o))
        entry = {
            "subject_type": s,
            "relation": rel,
            "object_type": o,
            "count": n,
            "valid": valid,
            "in_extraction_whitelist": in_wl,
        }
        signatures.append(entry)
        if not valid:
            violating.append(entry)

    violating.sort(key=lambda e: e["count"], reverse=True)
    conformance = round(valid_edges / total_edges, 4) if total_edges else 1.0
    _log.info(
        "property_graph.audit",
        signatures=len(signatures),
        violating=len(violating),
        conformance=conformance,
    )
    return {
        "profile": "server",
        "distinct_signatures": len(signatures),
        "violating_signatures": len(violating),
        "total_edges_sampled": total_edges,
        "valid_edges": valid_edges,
        "conformance": conformance,
        "signatures": signatures,
        "violations": violating[: int(examples)] if examples else [],
    }


# ---------------------------------------------------------------------------
# GET /live-sample-paths — real Sample pivot paths already in the graph
# ---------------------------------------------------------------------------


# How many representative Measurement ids to hang off each specimen's pivot path.
_SAMPLE_MEASUREMENT_CAP = 3

# Real specimen pivots in the live graph: a Material that has Measurements
# ``ABOUT_MATERIAL`` it (and, when present, a ProcessingRegime that ``APPLIES_TO``
# it). The corpus carries no native ``Sample`` / ``USES_SAMPLE`` edges, so this is
# the real structure that the canonical §8.2 Sample pivot re-expresses.
_LIVE_PIVOT_CYPHER = (
    "MATCH (mat:Node {label:'Material'})"
    "<-[:Rel {type:'ABOUT_MATERIAL'}]-(ms:Node {label:'Measurement'}) "
    "WITH mat, collect(DISTINCT ms.id) AS all_ms "
    "OPTIONAL MATCH (mat)<-[:Rel {type:'APPLIES_TO'}]-(reg:Node {label:'ProcessingRegime'}) "
    "RETURN mat.id AS mid, mat.name AS mname, reg.id AS rid, reg.name AS rname, "
    "size(all_ms) AS n_ms, all_ms[0.." + str(_SAMPLE_MEASUREMENT_CAP) + "] AS sample_ms "
    "ORDER BY n_ms DESC LIMIT "
)


@router.get("/live-sample-paths")
def live_sample_paths(
    limit: int = Query(default=25, ge=1, le=200),
) -> dict:
    """Re-express real specimen pivots as canonical ``Sample`` paths and validate (§6.11).

    The live graph binds a specimen through ``Measurement-ABOUT_MATERIAL->Material``
    (and optionally ``ProcessingRegime-APPLIES_TO->Material``) rather than the
    canonical ``Experiment-USES_SAMPLE->Sample`` pivot — those §8.2 edges are never
    ingested, so the old walk always came back empty. Instead we take each real
    Material that carries Measurements, re-express it via
    :func:`synthesize_sample_path` as the schema-clean ``Sample`` pivot the §6.11
    extractor would emit, and run every triplet back through
    :func:`constrain_triplets`. The result proves the pivot is whitelisted on real
    corpus nodes. Returns an empty list (not an error) when no material carries a
    measurement yet.
    """
    store = _require_server()
    rows = store.rows(_LIVE_PIVOT_CYPHER + str(int(limit)), {})
    paths: list[dict] = []
    all_valid = True
    for mid, mname, rid, rname, n_ms, sample_ms in rows:
        measurement_ids = [str(x) for x in (sample_ms or [])]
        experiment_id = f"exp:{mid}"  # synthetic pivot anchor over the real Material
        triplets = pg.synthesize_sample_path(
            experiment_id,
            material_id=str(mid),
            regime_id=str(rid) if rid is not None else None,
            measurement_ids=measurement_ids,
        )
        res = pg.constrain_triplets(triplets)
        valid = len(res.rejected) == 0
        all_valid = all_valid and valid
        paths.append(
            {
                "experiment": {"id": experiment_id, "synthetic": True},
                "sample": {"id": triplets[0].object},
                "material": {"id": mid, "name": mname},
                "regime": {"id": rid, "name": rname} if rid is not None else None,
                "measurement_count": int(n_ms or 0),
                "sample_measurement_ids": measurement_ids,
                "edges": [
                    {
                        "subject_type": t.subject_type,
                        "relation": t.relation,
                        "object_type": t.object_type,
                    }
                    for t in triplets
                ],
                "schema_valid": valid,
            }
        )
    return {
        "profile": "server",
        "count": len(paths),
        "all_schema_valid": all_valid,
        "paths": paths,
    }
