"""Graph diff «до/после курирования» из CurationEvent'ов, Reagraph-формат (§16.10).

§16.10 «curation diff» просит показать в UI, что именно изменило *курирование*
(added / removed / changed с property-level before/after), **отделив** эти
изменения от ingestion. Снапшот-DTO и diff-движок уже написаны и переиспользуются
здесь как есть — этот роутер их НЕ переписывает:

* :func:`kg_retrievers.graph_diff.diff_snapshots` — чистый трёхсторонний diff двух
  снимков графа ``{"nodes": {...}, "edges": {...}}`` → ``added/removed/changed``.
* :func:`kg_retrievers.graph_diff_reagraph.to_reagraph` — переформатирование diff
  в плоские node/edge-списки, где каждый элемент несёт ``status`` (§16.10-критерий
  «рендерится в Reagraph-совместимом формате с пометками статуса»).

Чем этот роутер отличается от общего снапшот-diff (``/api/v1/graph/curation-diff``,
§14.6): тот сравнивает два ПРОИЗВОЛЬНЫХ снимка подграфа и не знает, ingestion это
было или курирование. Здесь diff строится **из самих курирующих событий**: каждое
действие куратора пишет узел ``CurationEvent`` (label='CurationEvent') со снимками
``before`` / ``after`` целевого узла (см. ``curation_service.curation``). Мы читаем
ЭТИ события из живого графа (server-профиль Neo4j :8000 через ``get_store``) — а не
весь граф — поэтому в diff попадают ровно узлы, тронутые куратором; ingestion-правки
(без ``CurationEvent``) не проникают сюда by construction. Окно ``since`` / ``until``
по ``CurationEvent.created_at`` сужает интервал (§16.10 «по связанным
CurationEvent.created_at в интервале»).

Агрегация по цели: у узла может быть несколько событий. Мы берём ``before`` самого
раннего события (состояние ДО курирования) и ``after`` самого позднего (ПОСЛЕ),
получая нетто-дельту курирования по каждому узлу — это и есть «до/после».

Endpoints (prefix ``/api/v1/curation-diff-reagraph``):

* ``GET /events``   — сырой аудит-лог курирующих событий (для панели истории).
* ``GET /reagraph`` — before/after-diff курирования в Reagraph-формате + счётчики.
* ``GET /legend``   — легенда статусов (added/removed/changed) для UI.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Query

from api_gateway.deps import get_store
from kg_retrievers.graph_diff import diff_snapshots
from kg_retrievers.graph_diff_reagraph import to_reagraph

router = APIRouter(prefix="/api/v1/curation-diff-reagraph", tags=["curation-diff-reagraph"])

# Bookkeeping fields that flip on every write — dropped from the property-level
# delta so a curation change reads as its *meaningful* fields (name, value,
# review_status, verified …) and not a wall of timestamps.
_NOISE_FIELDS: frozenset[str] = frozenset(
    {"updated_at", "created_at", "schema_version", "last_curation_event_id"}
)


def _parse_props(raw: Any) -> dict[str, Any] | None:
    """Parse a ``before``/``after`` JSON blob into a props dict (``None`` → absent).

    Curation events store the pre/post node snapshot as a JSON string. A missing,
    empty or literal ``"null"`` value means «no node on that side» (added/removed),
    signalled by returning ``None``.
    """
    if raw in (None, "", "null"):
        return None
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, str):
        try:
            loaded = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None
        return dict(loaded) if isinstance(loaded, dict) else None
    return None


def _clean(props: dict[str, Any] | None) -> dict[str, Any] | None:
    """Drop volatile bookkeeping keys (:data:`_NOISE_FIELDS`) from a props dict."""
    if props is None:
        return None
    return {k: v for k, v in props.items() if k not in _NOISE_FIELDS}


def _label_of(props: dict[str, Any] | None) -> str | None:
    return props.get("label") if props else None


def _load_events(
    *,
    since: str | None,
    until: str | None,
    actor: str | None,
    action: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    """Read curation events from the live store, newest-first, applying filters.

    Reads only ``CurationEvent`` nodes (never the whole graph), so the result is
    curation-only by construction. ``since``/``until`` bound ``created_at``
    (ISO-8601 lexical compare), ``actor``/``action`` are exact-match filters.
    """
    store = get_store()
    rows = store.rows(
        "MATCH (e:Node) WHERE e.label='CurationEvent' "
        "RETURN e.id, e.created_at ORDER BY e.created_at DESC"
    )
    events: list[dict[str, Any]] = []
    for row in rows:
        eid = row[0]
        created = row[1] if len(row) > 1 else None
        node = store.get_node(eid) or {}
        created_at = node.get("created_at") or created or ""
        if since is not None and created_at < since:
            continue
        if until is not None and created_at > until:
            continue
        ev_actor = node.get("actor_id")
        if actor is not None and ev_actor != actor:
            continue
        ev_action = node.get("action")
        if action is not None and ev_action != action:
            continue
        target_id = node.get("target_id")
        if not target_id:
            continue
        events.append(
            {
                "event_id": eid,
                "action": ev_action,
                "actor": ev_actor,
                "target_id": target_id,
                "reason": node.get("reason") or "",
                "created_at": created_at,
                "before": _parse_props(node.get("before")),
                "after": _parse_props(node.get("after")),
            }
        )
        if len(events) >= limit:
            break
    return events


def _build_snapshots(
    events: list[dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]], dict[str, str]]:
    """Fold per-target events into before/after node snapshots + a label index.

    Events arrive newest-first. For each target we keep the ``before`` of its
    *earliest* event (state prior to any curation) and the ``after`` of its
    *latest* event (state after all curation) — the net «до/после курирования»
    for that node. Returns ``(before_nodes, after_nodes, labels)``.
    """
    before_nodes: dict[str, dict[str, Any]] = {}
    after_nodes: dict[str, dict[str, Any]] = {}
    labels: dict[str, str] = {}

    # Oldest-first so «earliest before» / «latest after» fall out naturally.
    for ev in reversed(events):
        tid = ev["target_id"]
        before = _clean(ev["before"])
        after = _clean(ev["after"])
        # earliest before: only set once (first time we see this target).
        if before is not None and tid not in before_nodes:
            before_nodes[tid] = before
        # latest after: overwrite each time so the newest wins.
        if after is not None:
            after_nodes[tid] = after
        lbl = _label_of(after) or _label_of(before)
        if lbl:
            labels[tid] = lbl
    return before_nodes, after_nodes, labels


def _enrich(nodes: list[dict[str, Any]], labels: dict[str, str]) -> list[dict[str, Any]]:
    """Attach a display ``label``/``name`` to each Reagraph node for the UI.

    ``to_reagraph`` emits ``{id, status, data}``. For added/removed nodes ``data``
    is the props snapshot (carries ``name``); for changed nodes ``data`` is only
    the field-delta, so ``name`` falls back to the node id.
    """
    out: list[dict[str, Any]] = []
    for node in nodes:
        data = node.get("data") or {}
        name = data.get("name") if isinstance(data, dict) else None
        enriched = dict(node)
        enriched["label"] = labels.get(node["id"])
        enriched["name"] = name or node["id"]
        out.append(enriched)
    return out


@router.get("/events")
def curation_events(
    since: str | None = Query(None, description="ISO-8601 lower bound on created_at"),
    until: str | None = Query(None, description="ISO-8601 upper bound on created_at"),
    actor: str | None = Query(None, description="filter by actor_id"),
    action: str | None = Query(None, description="filter by curation action"),
    limit: int = Query(500, ge=1, le=5000),
) -> dict[str, Any]:
    """Curation audit trail — the events behind the diff (§16.10 «отделив от ingestion»)."""
    events = _load_events(since=since, until=until, actor=actor, action=action, limit=limit)
    items = [
        {
            "event_id": e["event_id"],
            "action": e["action"],
            "actor": e["actor"],
            "target_id": e["target_id"],
            "reason": e["reason"],
            "created_at": e["created_at"],
            "has_before": e["before"] is not None,
            "has_after": e["after"] is not None,
        }
        for e in events
    ]
    return {"events": items, "count": len(items)}


@router.get("/reagraph")
def curation_reagraph(
    since: str | None = Query(None, description="ISO-8601 lower bound on created_at"),
    until: str | None = Query(None, description="ISO-8601 upper bound on created_at"),
    actor: str | None = Query(None, description="filter by actor_id"),
    action: str | None = Query(None, description="filter by curation action"),
    limit: int = Query(500, ge=1, le=5000),
) -> dict[str, Any]:
    """Reagraph-ready before/after curation diff + counts + backing events (§16.10).

    Pipeline: read curation events (curation-only, windowable) → fold into
    before/after node snapshots → :func:`diff_snapshots` → :func:`to_reagraph`.
    Every returned node/edge carries ``status`` (added/removed/changed); changed
    nodes carry a per-field ``changes`` map ``field → [before, after]``.
    """
    events = _load_events(since=since, until=until, actor=actor, action=action, limit=limit)
    before_nodes, after_nodes, labels = _build_snapshots(events)

    diff = diff_snapshots(
        {"nodes": before_nodes, "edges": {}},
        {"nodes": after_nodes, "edges": {}},
    )
    reagraph = to_reagraph(diff).as_dict()
    reagraph["nodes"] = _enrich(reagraph["nodes"], labels)

    audit = [
        {
            "event_id": e["event_id"],
            "action": e["action"],
            "actor": e["actor"],
            "target_id": e["target_id"],
            "reason": e["reason"],
            "created_at": e["created_at"],
        }
        for e in events
    ]

    return {
        "nodes": reagraph["nodes"],
        "edges": reagraph["edges"],
        "counts": reagraph["counts"],
        "events": audit,
        "window": {"since": since, "until": until, "actor": actor, "action": action},
        "curated_targets": len({**before_nodes, **after_nodes}),
        "event_count": len(events),
    }


@router.get("/legend")
def legend() -> dict[str, Any]:
    """Легенда статусов дельты для UI — цвета/подписи added/removed/changed."""
    return {
        "statuses": [
            {"key": "added", "label_ru": "Добавлено", "label_en": "Added", "tone": "emerald"},
            {"key": "removed", "label_ru": "Удалено", "label_en": "Removed", "tone": "red"},
            {"key": "changed", "label_ru": "Изменено", "label_en": "Changed", "tone": "amber"},
        ],
        "note": (
            "Diff строится из CurationEvent'ов — показаны только изменения курирования, "
            "не ingestion. Изменённые узлы несут пофайловый before/after."
        ),
    }
