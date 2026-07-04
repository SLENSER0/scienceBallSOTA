"""Source Catalog in the admin UI — каталог источников (§10.7).

RU: Governance-каталог источников. §10 отдаёт лишь плоский ``/admin/lineage``
(список прогонов), но у админа нет каталога источников с владельцем/лабораторией/
свежестью и наглядного lineage-графа RAW→Neo4j/Qdrant/OpenSearch по клику. Этот
роутер собирает такой каталог **из живого графа** (Document/Paper-узлы сервера
Neo4j), переиспользуя уже готовые чистые модули каталога, и рисуемый lineage-
подграф из канонического §9.1-пайплайна.

EN: Governance source catalog. §10 only ships a flat ``/admin/lineage`` run list;
the admin has no catalog of sources with owner/lab/freshness and no drawable
lineage graph. This router assembles that catalog **from the live graph**
(``Document``/``Paper`` nodes in the server Neo4j store) and a drawable lineage
subgraph from the canonical §9.1 pipeline. Every store read is wrapped so an
unavailable catalog yields a graceful, non-500 fallback (``available: false``).

Reused, already-shipped pure modules (no re-implementation):

* :mod:`kg_common.metadata.source_catalog_card`  — ``build_card`` / ``cards_by_lab``.
* :mod:`kg_common.metadata.catalog_source_query`  — ``query`` (search+sort+page).
* :mod:`kg_common.source_freshness`               — ``classify`` freshness level.
* :mod:`kg_common.metadata.pipeline_lineage_spec` — canonical RAW→stores DAG.
* :mod:`kg_common.metadata.lineage_subgraph`      — ``build_subgraph`` (roles+depth).
* :mod:`kg_common.metadata.urns`                  — DataHub-style dataset URNs.
* :mod:`kg_common.metadata.catalog_deeplink`      — "Open in catalog" deep-link.

Endpoints (admin namespace, §6.2):

* ``GET /api/v1/admin/catalog/sources``               — list/search/paginate.
* ``GET /api/v1/admin/catalog/facets``                — distinct lab/owner/access.
* ``GET /api/v1/admin/catalog/sources/{id}``          — one source card.
* ``GET /api/v1/admin/catalog/sources/{id}/lineage``  — drawable lineage graph.
* ``GET /api/v1/admin/catalog/datasets/{urn}``        — one serving-store dataset.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from api_gateway.auth import current_role
from api_gateway.deps import get_store
from kg_common.metadata.catalog_deeplink import deeplink_for
from kg_common.metadata.catalog_source_query import query as catalog_query
from kg_common.metadata.lineage_subgraph import build_subgraph
from kg_common.metadata.pipeline_lineage_spec import lineage_edges, terminal_outputs
from kg_common.metadata.source_catalog_card import build_card
from kg_common.metadata.urns import build_dataset_urn, is_valid_urn, parse_urn
from kg_common.source_freshness import classify

router = APIRouter(prefix="/api/v1/admin/catalog", tags=["admin-catalog"])

# Labels that represent a *source* in the graph (§8.1 Document/Paper).
_SOURCE_LABELS = ("Document", "Paper")
# How many source nodes to scan at most (catalogs are bounded; keeps reads cheap).
_SCAN_CAP = 2000
# Timestamp fields, best → worst, used to derive "last ingest" for freshness.
_TS_FIELDS = ("last_ingest", "ingested_at", "updated_at", "created_at")

# The three canonical serving stores and how to label / URN them (§9.1 / §10.3).
_STORE_META: dict[str, dict[str, str]] = {
    "neo4j_kg": {"platform": "neo4j", "label": "Neo4j (граф знаний)"},
    "qdrant_index": {"platform": "qdrant", "label": "Qdrant (векторы)"},
    "opensearch_index": {"platform": "opensearch", "label": "OpenSearch (BM25)"},
}
# Human labels for the intermediate pipeline datasets (§9.1 twelve-step DAG).
_DATASET_RU: dict[str, str] = {
    "source_record": "Регистрация источника",
    "parsed_doc": "Docling-парсинг",
    "parsed_s3_ref": "Parsed в S3",
    "chunks": "Чанки",
    "extracted_triples": "Извлечённые триплеты",
    "normalized_triples": "Нормализация единиц",
    "resolved_entities": "Разрешение сущностей",
    "validated_graph": "Валидация схемы",
    "neo4j_kg": "Neo4j (граф знаний)",
    "qdrant_index": "Qdrant (векторы)",
    "opensearch_index": "OpenSearch (BM25)",
}


# --------------------------------------------------------------------------- #
# Store reads — every one is best-effort (graceful, never a 500).             #
# --------------------------------------------------------------------------- #


def _parse_ts(value: Any) -> datetime | None:
    """Best-effort parse of an ISO-8601 timestamp string/datetime → aware datetime."""
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if not value:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        # Bare date, or an unparsable string → treat as unknown freshness.
        try:
            dt = datetime.strptime(text[:10], "%Y-%m-%d")
        except ValueError:
            return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _last_ingest(node: dict[str, Any]) -> tuple[str, datetime | None]:
    """Return ``(iso_string, datetime|None)`` of the source's newest ingest stamp."""
    for field in _TS_FIELDS:
        dt = _parse_ts(node.get(field))
        if dt is not None:
            return dt.isoformat(), dt
    return "", None


def _source_mapping(node: dict[str, Any]) -> dict[str, Any]:
    """Flatten a graph node into the ``source`` mapping ``build_card`` expects.

    ``lab`` falls back to ``domain`` (acceptance §16 Phase 8: «источники
    сгруппированы по domain=лаборатория»); ``version`` is coerced to ``int``.
    """
    last_ingest, _ = _last_ingest(node)
    try:
        version = int(node.get("version", 1) or 1)
    except (TypeError, ValueError):
        version = 1
    return {
        "source_id": str(node.get("id", "")),
        "name": str(node.get("name") or node.get("title") or node.get("id") or ""),
        "owner": str(node.get("owner") or node.get("owner_id") or ""),
        "lab": str(node.get("lab") or node.get("lab_id") or node.get("domain") or ""),
        "access_policy": str(node.get("access_policy") or node.get("access") or ""),
        "version": version,
        "last_ingest": last_ingest,
    }


def _scan_sources(store: Any) -> list[dict[str, Any]]:
    """Read every ``Document``/``Paper`` node (flattened dicts). ``[]`` on failure."""
    rows = store.rows(
        "MATCH (n:Node) WHERE n.label IN $labels RETURN n LIMIT $lim",
        {"labels": list(_SOURCE_LABELS), "lim": _SCAN_CAP},
    )
    out: list[dict[str, Any]] = []
    for row in rows:
        try:
            out.append(store._node_dict(row[0]))
        except Exception:  # pragma: no cover - per-row store defensiveness
            continue
    return out


def _counts_by_source(store: Any, ids: list[str]) -> dict[str, tuple[int, int]]:
    """``{source_id: (evidence_count, run_count)}`` over each source's 2-hop reach.

    One aggregate read; evidence = ``:Evidence`` nodes reachable within two hops,
    runs = distinct ``extractor_run_id`` among them. Returns ``{}`` on any error so
    the catalog degrades to zero counts rather than failing.
    """
    if not ids:
        return {}
    try:
        rows = store.rows(
            "MATCH (d:Node) WHERE d.id IN $ids "
            "OPTIONAL MATCH (d)-[:Rel*1..2]->(e:Node {label:'Evidence'}) "
            "RETURN d.id, count(DISTINCT e.id), count(DISTINCT e.extractor_run_id)",
            {"ids": ids},
        )
    except Exception:
        return {}
    result: dict[str, tuple[int, int]] = {}
    for row in rows:
        sid = str(row[0])
        ev = int(row[1] or 0)
        runs = int(row[2] or 0)
        result[sid] = (ev, runs)
    return result


def _build_cards(store: Any) -> list[dict[str, Any]]:
    """Assemble one catalog card per source, freshness + counts included.

    Raises nothing store-related to the caller: on an unavailable graph the two
    reads yield ``[]`` / ``{}`` and this returns an empty catalog.
    """
    nodes = _scan_sources(store)
    if not nodes:
        return []
    ids = [str(n.get("id", "")) for n in nodes if n.get("id")]
    counts = _counts_by_source(store, ids)
    as_of = datetime.now(UTC)
    cards: list[dict[str, Any]] = []
    for node in nodes:
        src = _source_mapping(node)
        sid = src["source_id"]
        if not sid:
            continue
        _, last_dt = _last_ingest(node)
        fresh = classify(sid, last_dt, as_of)
        ev, runs = counts.get(sid, (0, 0))
        card = build_card(src, freshness=fresh.level, evidence_count=ev, run_count=runs)
        row = card.as_dict()
        row["age_days"] = fresh.age_days
        row["label"] = str(node.get("label") or "Document")
        cards.append(row)
    cards.sort(key=lambda c: (c.get("name") or c.get("source_id") or ""))
    return cards


# --------------------------------------------------------------------------- #
# Lineage graph — RAW → §9.1 pipeline → Neo4j / Qdrant / OpenSearch           #
# --------------------------------------------------------------------------- #

def _dataset_kind(name: str) -> str:
    """Classify a lineage node for colouring: raw / pipeline / store."""
    if name in _STORE_META:
        return "store"
    if name in ("source_record",):
        return "raw"
    return "pipeline"


def _lineage_payload(source_id: str, name: str) -> dict[str, Any]:
    """Build the drawable lineage subgraph for one source (§10.7).

    The canonical §9.1 dataset lineage (``lineage_edges``) is rooted at the real
    source node, so a single BFS downstream yields RAW→…→{Neo4j,Qdrant,OpenSearch}
    with per-node ``role``/``depth`` (via :func:`build_subgraph`). Each store node
    carries a DataHub-style URN and (when a native catalog is configured) a deep-link.
    """
    edges: list[tuple[str, str]] = [(source_id, "source_record"), *lineage_edges()]
    sub = build_subgraph(edges, source_id, up_hops=0, down_hops=16)

    stores = terminal_outputs()
    nodes: list[dict[str, Any]] = []
    for n in sub.nodes:
        kind = "raw" if n.role == "focus" else _dataset_kind(n.id)
        label = name if n.role == "focus" else _DATASET_RU.get(n.id, n.id)
        entry: dict[str, Any] = {
            "id": n.id,
            "role": n.role,
            "depth": n.depth,
            "kind": kind,
            "label": label,
        }
        if n.id in stores and n.id in _STORE_META:
            meta = _STORE_META[n.id]
            urn = build_dataset_urn(meta["platform"], source_id)
            entry["urn"] = urn
            entry["platform"] = meta["platform"]
            deeplink = _deeplink(urn)
            if deeplink is not None:
                entry["deeplink"] = deeplink
        nodes.append(entry)

    return {
        "focus": source_id,
        "name": name,
        "nodes": nodes,
        "edges": [list(e) for e in sub.edges],
    }


def _deeplink(urn: str) -> str | None:
    """"Open in catalog" URL for ``urn`` when a native catalog base is configured.

    Reads ``CATALOG_BASE_URL`` / ``CATALOG_PLATFORM`` (default ``datahub``); returns
    ``None`` when no catalog is wired so the UI simply omits the external link.
    """
    base = os.environ.get("CATALOG_BASE_URL", "").strip()
    if not base:
        return None
    platform = os.environ.get("CATALOG_PLATFORM", "datahub").strip() or "datahub"
    try:
        return deeplink_for(platform, base, urn).url
    except ValueError:
        return None


# --------------------------------------------------------------------------- #
# Endpoints                                                                    #
# --------------------------------------------------------------------------- #


@router.get("/sources")
def list_sources(
    q: str | None = Query(default=None),
    lab: str | None = Query(default=None),
    owner: str | None = Query(default=None),
    access: str | None = Query(default=None),
    sort_by: str | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=500),
    _role: str = Depends(current_role),
) -> dict[str, Any]:
    """List/search/paginate the source catalog (§10.7).

    Filters (``q`` free-text over name/id; ``lab``/``owner``/``access`` equality)
    and pagination are delegated to the pure ``catalog_source_query.query``. When
    the graph store is unavailable the response is an empty, ``available: false``
    page — a graceful fallback, never a 500 (acceptance §10.7).
    """
    try:
        cards = _build_cards(get_store())
        available = True
    except Exception:
        cards, available = [], False

    page = catalog_query(
        cards,
        q=q,
        lab=lab,
        owner=owner,
        access=access,
        sort_by=sort_by,
        offset=offset,
        limit=limit,
    )
    out = page.as_dict()
    out["available"] = available
    out["source_count"] = len(cards)
    return out


@router.get("/facets")
def facets(_role: str = Depends(current_role)) -> dict[str, Any]:
    """Distinct lab / owner / access values + per-lab counts for the filter UI.

    Powers the catalog's filter dropdowns and the «сгруппировано по лаборатории»
    view. Degrades to empty facets when the store is unavailable.
    """
    try:
        cards = _build_cards(get_store())
        available = True
    except Exception:
        cards, available = [], False

    labs = sorted({c["lab"] for c in cards if c.get("lab")})
    owners = sorted({c["owner"] for c in cards if c.get("owner")})
    accesses = sorted({c["access"] for c in cards if c.get("access")})
    # Reuse the pure lab-grouping helper only for counts (cards → SourceCatalogCard
    # not needed here; count on the dict rows directly).
    per_lab = {lab_name: len(rows) for lab_name, rows in cards_by_lab_rows(cards).items()}
    return {
        "available": available,
        "labs": labs,
        "owners": owners,
        "access": accesses,
        "by_lab": per_lab,
        "total": len(cards),
    }


def cards_by_lab_rows(cards: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Group dict-cards by ``lab`` preserving order (dict analogue of ``cards_by_lab``)."""
    grouped: dict[str, list[dict[str, Any]]] = {}
    for card in cards:
        grouped.setdefault(str(card.get("lab", "")), []).append(card)
    return grouped


def _find_card(store: Any, source_id: str) -> dict[str, Any] | None:
    """Return the single catalog card for ``source_id`` (freshness + counts)."""
    node = store.get_node(source_id)
    if not node:
        return None
    src = _source_mapping(node)
    if not src["source_id"]:
        return None
    counts = _counts_by_source(store, [source_id])
    ev, runs = counts.get(source_id, (0, 0))
    _, last_dt = _last_ingest(node)
    fresh = classify(source_id, last_dt, datetime.now(UTC))
    card = build_card(src, freshness=fresh.level, evidence_count=ev, run_count=runs)
    row = card.as_dict()
    row["age_days"] = fresh.age_days
    row["label"] = str(node.get("label") or "Document")
    return row


@router.get("/sources/{source_id:path}/lineage")
def source_lineage(
    source_id: str, _role: str = Depends(current_role)
) -> dict[str, Any]:
    """Drawable lineage graph RAW→Neo4j/Qdrant/OpenSearch for one source (§10.7).

    404 when the source is unknown; on a store error the lineage is still built
    from the canonical §9.1 pipeline spec (``available: false``, no counts) so the
    UI never breaks.
    """
    try:
        card = _find_card(get_store(), source_id)
        available = True
    except Exception:
        card, available = None, False

    if available and card is None:
        raise HTTPException(status_code=404, detail="source not found")

    name = (card or {}).get("name") or source_id
    payload = _lineage_payload(source_id, name)
    payload["available"] = available
    return payload


@router.get("/sources/{source_id:path}")
def source_card(
    source_id: str, _role: str = Depends(current_role)
) -> dict[str, Any]:
    """One source card: owner, lab, version, access, freshness, counts (§10.7).

    404 for an unknown source; graceful ``available: false`` when the store is down.
    """
    try:
        card = _find_card(get_store(), source_id)
        available = True
    except Exception:
        card, available = None, False

    if not available:
        return {"available": False, "source_id": source_id}
    if card is None:
        raise HTTPException(status_code=404, detail="source not found")
    card["available"] = True
    return card


@router.get("/datasets/{urn:path}")
def dataset_card(urn: str, _role: str = Depends(current_role)) -> dict[str, Any]:
    """Serving-store dataset card by DataHub-style URN (§10.7 / §10.3).

    Parses the URN into ``platform``/``name``/``env``; 400 on a malformed URN.
    Adds a native-catalog deep-link when ``CATALOG_BASE_URL`` is configured.
    """
    if not is_valid_urn(urn):
        raise HTTPException(status_code=400, detail="not a valid dataset urn")
    parsed = parse_urn(urn)
    out = parsed.as_dict()
    out["urn"] = urn
    deeplink = _deeplink(urn)
    if deeplink is not None:
        out["deeplink"] = deeplink
    return out
