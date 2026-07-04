"""ExtractorRun provenance & reproducibility surface (§6.14).

RU: Каждое доказательство (*Evidence*) должно знать, **каким прогоном и какой
моделью** оно извлечено — это основа воспроизводимости и lineage (§6.14). Прогон
экстрактора материализуется узлом ``:ExtractorRun`` (модель/версии/seed/params), а
связь ``(:Evidence)-[:EXTRACTED_BY]->(:ExtractorRun)`` (§8.2) привязывает каждое
доказательство к своему прогону.

Роутер читает живой граф (server-профиль, Neo4j :8000; тот же generic ``:Node`` /
``:Rel`` model, что и Kuzu) и отдаёт:

* ``GET  /api/v1/extractor-runs`` — список всех прогонов с воспроизводимыми
  метаданными (extractor, model, версии, schema_version, seed/params) и метрикой
  полноты lineage: сколько ``Evidence`` этого прогона уже связано ребром
  ``EXTRACTED_BY``, а сколько знает прогон только через свойство
  ``extractor_run_id`` (§3.7 provenance-штамп).
* ``GET  /api/v1/extractor-runs/{run_id}`` — карточка одного прогона: полный
  property-map узла ``:ExtractorRun``, что он произвёл (по меткам), примеры
  Evidence и флаг ``lineage_complete`` (все доказательства прогона имеют ребро).
* ``GET  /api/v1/extractor-runs/evidence/{evidence_id}`` — lineage одного
  доказательства: каким прогоном/моделью извлечено (ребро ``EXTRACTED_BY``
  приоритетнее, иначе — по свойству ``extractor_run_id``).
* ``POST /api/v1/extractor-runs/{run_id}/materialize-edges`` — идемпотентно
  достраивает недостающие рёбра ``EXTRACTED_BY`` от каждого ``Evidence`` этого
  прогона (несущего ``extractor_run_id``) к узлу ``:ExtractorRun``, закрывая
  критерий приёмки §6.14 на живом графе. Требует роль curator/admin.

Только чтение графа + идемпотентный ``MERGE`` ребра через штатный
``store.upsert_edge`` — никакого сырого write-Cypher от клиента (§14.6). Ничего не
пересчитывает: воспроизводимые метаданные берутся из узла ``:ExtractorRun``, как
их записал конвейер (:mod:`kg_schema.run_metadata`, §6.14).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api_gateway.auth import current_role
from api_gateway.deps import get_store

router = APIRouter(prefix="/api/v1/extractor-runs", tags=["extractor-run"])

# Roles allowed to mutate the graph (materialise missing EXTRACTED_BY edges).
_WRITE_ROLES = frozenset({"curator", "admin", "project_manager"})

# Relationship + labels this surface is built on (§8.2 / §8.1).
_EXTRACTED_BY = "EXTRACTED_BY"
_EVIDENCE = "Evidence"
_RUN_LABELS = ("ExtractorRun",)

# How many sample Evidence ids to attach to a run detail card (bounded for the UI).
_EVIDENCE_SAMPLE = 12

# Reproducibility-relevant property keys, surfaced (in order) as a run's "params"
# block when present on the :ExtractorRun node (model/prompt/seed/versions, §6.14).
_REPRO_KEYS: tuple[str, ...] = (
    "extractor",
    "extractor_version",
    "pipeline_version",
    "model",
    "schema_version",
    "seed",
    "temperature",
    "prompt_version",
    "prompt_versions",
    "code_git_sha",
    "git_sha",
    "vendor_manifest",
    "thresholds",
    "params",
    "status",
    "started_at",
    "finished_at",
    "n_facts",
    "n_docs",
    "n_entities",
    "n_measurements",
    "n_rejected_no_span",
)

# Node-internal / bookkeeping keys we never echo as reproducibility params.
_SKIP_KEYS = frozenset({"id", "label", "name", "created_at", "_id", "_label"})


# --------------------------------------------------------------------------- #
# Response models                                                              #
# --------------------------------------------------------------------------- #


class RunSummary(BaseModel):
    """One extractor run with its lineage-completeness roll-up (§6.14)."""

    run_id: str
    name: str | None = None
    extractor: str | None = None
    model: str | None = None
    pipeline_version: str | None = None
    schema_version: str | None = None
    created_at: str | None = None
    # Evidence produced by this run, counted two ways (they should converge once
    # EXTRACTED_BY is materialised):
    evidence_by_prop: int = 0  # Evidence carrying extractor_run_id == run_id (§3.7)
    evidence_by_edge: int = 0  # Evidence linked via (:Evidence)-[:EXTRACTED_BY]-> (§8.2)
    lineage_complete: bool = False  # every prop-linked Evidence also has the edge
    missing_edges: int = 0  # prop-linked Evidence still lacking the EXTRACTED_BY edge


class RunListResponse(BaseModel):
    runs: list[RunSummary]
    total_runs: int
    total_missing_edges: int
    fully_linked: bool  # no run has any missing EXTRACTED_BY edge


class RunDetail(BaseModel):
    """Full reproducibility card for one run (§6.14)."""

    run_id: str
    name: str | None = None
    created_at: str | None = None
    reproducibility: dict[str, Any]  # model/versions/seed/params echoed from the node
    produced_by_label: dict[str, int]  # what the run stamped, by node label (§3.7)
    evidence_by_prop: int
    evidence_by_edge: int
    lineage_complete: bool
    missing_edges: int
    evidence_sample: list[str]


class EvidenceLineage(BaseModel):
    """Which run/model extracted a single Evidence node (§6.14)."""

    evidence_id: str
    found: bool
    run_id: str | None = None
    linked_via: str | None = None  # "edge" (EXTRACTED_BY) | "property" | None
    extractor: str | None = None
    model: str | None = None
    pipeline_version: str | None = None
    schema_version: str | None = None
    run: dict[str, Any] | None = None  # full :ExtractorRun property-map when resolved


class MaterializeResult(BaseModel):
    """Outcome of back-filling EXTRACTED_BY edges for one run (§6.14)."""

    run_id: str
    evidence_by_prop: int
    edges_before: int
    edges_created: int
    edges_after: int
    lineage_complete: bool


# --------------------------------------------------------------------------- #
# Store helpers (generic :Node / :Rel model — works on Kuzu + Neo4j)          #
# --------------------------------------------------------------------------- #


def _rows(cypher: str, params: dict[str, Any] | None = None) -> list[list[Any]]:
    """Run a read query against the active graph store, defensively."""
    try:
        return get_store().rows(cypher, params or {})
    except Exception:  # pragma: no cover - store/back-end defensiveness
        return []


def _evidence_by_prop(run_id: str) -> list[str]:
    """Evidence ids that carry ``extractor_run_id == run_id`` (§3.7 provenance)."""
    rows = _rows(
        "MATCH (n:Node) WHERE n.label=$ev AND n.extractor_run_id=$id "
        "RETURN n.id ORDER BY n.id",
        {"ev": _EVIDENCE, "id": run_id},
    )
    return [r[0] for r in rows if r and r[0]]


def _evidence_by_edge(run_id: str) -> list[str]:
    """Evidence ids linked to the run via ``(:Evidence)-[:EXTRACTED_BY]->`` (§8.2)."""
    rows = _rows(
        "MATCH (n:Node)-[r:Rel]->(run:Node {id:$id}) "
        "WHERE r.type=$rt AND n.label=$ev RETURN n.id ORDER BY n.id",
        {"id": run_id, "rt": _EXTRACTED_BY, "ev": _EVIDENCE},
    )
    return [r[0] for r in rows if r and r[0]]


def _run_node(run_id: str) -> dict[str, Any] | None:
    """Load an ``:ExtractorRun`` node, or ``None`` if it is not a run node."""
    try:
        node = get_store().get_node(run_id)
    except Exception:  # pragma: no cover
        node = None
    if not node:
        return None
    if node.get("label") not in _RUN_LABELS:
        return None
    return node


def _reproducibility(node: dict[str, Any]) -> dict[str, Any]:
    """Pick the reproducibility-relevant properties off a run node (§6.14).

    Returns the known keys (:data:`_REPRO_KEYS`, in order) that are present, plus
    any other non-bookkeeping property so nothing extractor-specific is hidden.
    """
    repro: dict[str, Any] = {}
    for key in _REPRO_KEYS:
        if key in node and node[key] is not None:
            repro[key] = node[key]
    for key, val in node.items():
        if key in _SKIP_KEYS or key in repro or val is None:
            continue
        repro[key] = val
    return repro


def _summary_for(run_id: str, node: dict[str, Any]) -> RunSummary:
    """Build a :class:`RunSummary` (with lineage roll-up) for one run node."""
    by_prop = set(_evidence_by_prop(run_id))
    by_edge = set(_evidence_by_edge(run_id))
    missing = by_prop - by_edge
    return RunSummary(
        run_id=run_id,
        name=node.get("name"),
        extractor=node.get("extractor") or node.get("name"),
        model=node.get("model"),
        pipeline_version=node.get("pipeline_version"),
        schema_version=node.get("schema_version"),
        created_at=node.get("created_at") or node.get("started_at"),
        evidence_by_prop=len(by_prop),
        evidence_by_edge=len(by_edge),
        lineage_complete=len(by_prop) > 0 and not missing,
        missing_edges=len(missing),
    )


# --------------------------------------------------------------------------- #
# Endpoints                                                                    #
# --------------------------------------------------------------------------- #


@router.get("", response_model=RunListResponse)
def list_runs(_role: str = Depends(current_role)) -> RunListResponse:
    """List every ``:ExtractorRun`` with reproducibility + lineage completeness (§6.14)."""
    run_rows = _rows(
        "MATCH (r:Node) WHERE r.label IN $labels "
        "RETURN r.id ORDER BY coalesce(r.created_at, r.started_at, r.id)",
        {"labels": list(_RUN_LABELS)},
    )
    summaries: list[RunSummary] = []
    for row in run_rows:
        rid = row[0]
        node = _run_node(rid)
        if node is None:
            continue
        summaries.append(_summary_for(rid, node))
    total_missing = sum(s.missing_edges for s in summaries)
    return RunListResponse(
        runs=summaries,
        total_runs=len(summaries),
        total_missing_edges=total_missing,
        fully_linked=total_missing == 0,
    )


@router.get("/evidence/{evidence_id:path}", response_model=EvidenceLineage)
def evidence_lineage(
    evidence_id: str, _role: str = Depends(current_role)
) -> EvidenceLineage:
    """Resolve which run/model extracted one Evidence node (§6.14).

    Prefers the explicit ``EXTRACTED_BY`` edge (§8.2); falls back to the
    ``extractor_run_id`` provenance stamp on the Evidence node (§3.7) when the edge
    has not been materialised yet.
    """
    try:
        ev = get_store().get_node(evidence_id)
    except Exception:  # pragma: no cover
        ev = None
    if not ev:
        return EvidenceLineage(evidence_id=evidence_id, found=False)

    linked_via: str | None = None
    run_id: str | None = None

    edge_rows = _rows(
        "MATCH (e:Node {id:$id})-[r:Rel]->(run:Node) "
        "WHERE r.type=$rt AND run.label IN $labels RETURN run.id LIMIT 1",
        {"id": evidence_id, "rt": _EXTRACTED_BY, "labels": list(_RUN_LABELS)},
    )
    if edge_rows and edge_rows[0] and edge_rows[0][0]:
        run_id = edge_rows[0][0]
        linked_via = "edge"
    elif ev.get("extractor_run_id"):
        run_id = str(ev["extractor_run_id"])
        linked_via = "property"

    if not run_id:
        return EvidenceLineage(evidence_id=evidence_id, found=True)

    run = _run_node(run_id)
    if run is None:
        # extractor_run_id points at a run node that is absent from the graph.
        return EvidenceLineage(
            evidence_id=evidence_id,
            found=True,
            run_id=run_id,
            linked_via=linked_via,
        )
    return EvidenceLineage(
        evidence_id=evidence_id,
        found=True,
        run_id=run_id,
        linked_via=linked_via,
        extractor=run.get("extractor") or run.get("name"),
        model=run.get("model"),
        pipeline_version=run.get("pipeline_version"),
        schema_version=run.get("schema_version"),
        run=_reproducibility(run),
    )


@router.get("/{run_id:path}", response_model=RunDetail)
def run_detail(run_id: str, _role: str = Depends(current_role)) -> RunDetail:
    """Full reproducibility card for one extractor run (§6.14)."""
    node = _run_node(run_id)
    if node is None:
        raise HTTPException(status_code=404, detail=f"ExtractorRun not found: {run_id}")

    by_prop = _evidence_by_prop(run_id)
    by_edge = set(_evidence_by_edge(run_id))
    missing = set(by_prop) - by_edge

    produced_rows = _rows(
        "MATCH (n:Node) WHERE n.extractor_run_id=$id "
        "RETURN n.label, count(n) ORDER BY count(n) DESC",
        {"id": run_id},
    )
    produced = {r[0]: r[1] for r in produced_rows if r and r[0] is not None}

    return RunDetail(
        run_id=run_id,
        name=node.get("name"),
        created_at=node.get("created_at") or node.get("started_at"),
        reproducibility=_reproducibility(node),
        produced_by_label=produced,
        evidence_by_prop=len(by_prop),
        evidence_by_edge=len(by_edge),
        lineage_complete=len(by_prop) > 0 and not missing,
        missing_edges=len(missing),
        evidence_sample=by_prop[:_EVIDENCE_SAMPLE],
    )


@router.post("/{run_id:path}/materialize-edges", response_model=MaterializeResult)
def materialize_edges(
    run_id: str, role: str = Depends(current_role)
) -> MaterializeResult:
    """Back-fill missing ``EXTRACTED_BY`` edges for a run, idempotently (§6.14).

    For every ``Evidence`` that carries ``extractor_run_id == run_id`` (§3.7) but
    lacks the ``(:Evidence)-[:EXTRACTED_BY]->(:ExtractorRun)`` edge (§8.2), MERGE the
    edge via the store's parameterised ``upsert_edge`` (no raw write-Cypher, §14.6).
    Re-running is safe — already-linked Evidence is skipped, so the operation is
    idempotent and drives the run toward ``lineage_complete``.
    """
    if role not in _WRITE_ROLES:
        raise HTTPException(status_code=403, detail="curator/admin role required")

    node = _run_node(run_id)
    if node is None:
        raise HTTPException(status_code=404, detail=f"ExtractorRun not found: {run_id}")

    by_prop = set(_evidence_by_prop(run_id))
    edges_before = set(_evidence_by_edge(run_id))
    to_link = by_prop - edges_before

    store = get_store()
    schema_version = node.get("schema_version")
    created_at = node.get("created_at") or node.get("started_at")
    created = 0
    for ev_id in sorted(to_link):
        props: dict[str, Any] = {"extractor_run_id": run_id}
        if schema_version is not None:
            props["schema_version"] = schema_version
        if created_at is not None:
            props["created_at"] = created_at
        try:
            store.upsert_edge(ev_id, run_id, _EXTRACTED_BY, **props)
            created += 1
        except Exception:  # pragma: no cover - one bad edge must not abort the batch
            continue

    edges_after = len(set(_evidence_by_edge(run_id)))
    return MaterializeResult(
        run_id=run_id,
        evidence_by_prop=len(by_prop),
        edges_before=len(edges_before),
        edges_created=created,
        edges_after=edges_after,
        lineage_complete=len(by_prop) > 0 and edges_after >= len(by_prop),
    )
