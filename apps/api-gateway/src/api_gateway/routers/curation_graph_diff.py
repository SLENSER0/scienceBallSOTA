"""Визуальный diff графа до/после курирования (§14.6 · §5.2.3/§5.2.8).

Бэкенд уже несёт переиспользуемый движок дельты графа
(:func:`api_gateway.graph_diff.diff_graphs` — трёхсторонний
added/removed/changed по ключу узла и ребра), но не было ни одного эндпоинта,
который бы (а) снимал нормализованный снимок живого подграфа с сервер-профиля
(Neo4j :8000) и (б) сравнивал два снимка «до/после курирования» для наглядной
визуализации. Этот роутер закрывает оба шага, **не переписывая** движок diff и
не дублируя логику стора — он лишь склеивает готовые блоки:

* :meth:`GraphStore.subgraph_from_ids` / :meth:`GraphStore.neighbors` — вытяжка
  живого подграфа вокруг seed-узлов с N-шаговым расширением (§14.6 subgraph).
* :func:`api_gateway.graph_diff.diff_graphs` — трёхсторонняя дельта (§14.6 diff).

Поток курирования / curation flow:

1. ``GET  /snapshot``  — снять снимок «ДО» вокруг seed-узлов и сохранить на
   клиенте (форма ``{nodes, edges}``, готовая к diff).
2. Куратор редактирует граф (merge / edit / verify / mark-inferred …).
3. ``POST /compare``   — сравнить два переданных снимка (полностью офлайн-diff),
   **или**
   ``POST /``          — передать только снимок «ДО» + seed: сервер сам снимет
   текущее (живое) состояние как «ПОСЛЕ» и вернёт дельту одним вызовом.

Каждый ответ несёт узлы/рёбра ``added`` / ``removed`` / ``changed`` (с
``_before`` / ``_after`` снимками изменённой записи) плюс агрегированные счётчики
и человекочитаемую RU/EN-сводку — ровно то, что рендерит экран «Визуальный diff
графа» (§5.2.3 «graph diff → before-after curation», §5.2.8 «compare graph
versions»).

Эндпоинты (prefix ``/api/v1/graph/curation-diff``):

* ``GET  /snapshot`` — нормализованный снимок живого подграфа.
* ``POST /compare``  — дельта двух переданных снимков.
* ``POST /``         — дельта «переданный ДО» vs «живое ПОСЛЕ».
* ``GET  /legend``   — легенда категорий (added/removed/changed) для UI.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from api_gateway.deps import get_store
from api_gateway.graph_diff import diff_graphs

router = APIRouter(prefix="/api/v1/graph/curation-diff", tags=["graph-curation-diff"])

# Поля узла GraphNode, которые несут курируемый смысл и должны участвовать в
# сравнении «изменено». ``properties`` разворачивается плоско, чтобы правки
# отдельных свойств (напр. review_status, verified, confidence) были видны
# пофайлово в _before/_after.
_NODE_SCALARS = ("type", "label", "confidence", "evidence_count", "verified", "community_id")
_EDGE_SCALARS = (
    "source",
    "target",
    "label",
    "type",
    "confidence",
    "evidence_count",
    "inferred",
    "contradicted",
    "evidence_ids",
)

_MAX_NODES = 800
_MAX_EDGES = 2000


def _now_iso() -> str:
    """Текущая метка времени UTC в ISO-8601 (для ``captured_at``)."""
    return datetime.now(UTC).isoformat()


def _node_to_row(node: Any) -> dict[str, Any]:
    """GraphNode DTO → плоский dict для diff'а (ключ ``id`` обязателен).

    Скалярные поля выносятся наверх; словарь ``properties`` разворачивается в
    ``prop:<name>`` ключи, поэтому смена любого курируемого свойства узла
    трактуется движком как «изменение» этого узла (§14.6 changed).
    """
    data = node.model_dump() if hasattr(node, "model_dump") else dict(node)
    row: dict[str, Any] = {"id": str(data.get("id"))}
    for key in _NODE_SCALARS:
        value = data.get(key)
        if value is not None:
            row[key] = value
    props = data.get("properties") or {}
    if isinstance(props, dict):
        for pkey, pval in props.items():
            if pval is not None:
                row[f"prop:{pkey}"] = pval
    return row


def _edge_to_row(edge: Any) -> dict[str, Any]:
    """GraphEdge DTO → плоский dict для diff'а (ключ ``id`` обязателен)."""
    data = edge.model_dump() if hasattr(edge, "model_dump") else dict(edge)
    row: dict[str, Any] = {"id": str(data.get("id"))}
    for key in _EDGE_SCALARS:
        value = data.get(key)
        if value is not None:
            row[key] = value
    return row


def _seed_ids(node_ids: list[str], store: Any, limit: int) -> list[str]:
    """Определить seed-узлы: явно переданные, иначе выборка из живого графа."""
    seeds = [nid.strip() for nid in node_ids if nid and nid.strip()]
    if seeds:
        return seeds
    rows = store.rows(f"MATCH (n:Node) RETURN n.id LIMIT {int(limit)}")
    return [str(r[0]) for r in rows if r and r[0] is not None]


def _capture(node_ids: list[str], expand: int) -> dict[str, Any]:
    """Снять нормализованный снимок живого подграфа вокруг seed-узлов (§14.6).

    Возвращает форму ``{nodes, edges, captured_at, seed_ids, counts, truncated}``,
    где ``nodes`` / ``edges`` — плоские dict'ы, пригодные для :func:`diff_graphs`.
    """
    store = get_store()
    seeds = _seed_ids(node_ids, store, limit=25)
    resp = store.subgraph_from_ids(seeds, expand=max(0, min(int(expand), 3)))

    nodes = [_node_to_row(n) for n in resp.nodes]
    edges = [_edge_to_row(e) for e in resp.edges]
    truncated = len(nodes) > _MAX_NODES or len(edges) > _MAX_EDGES
    nodes = nodes[:_MAX_NODES]
    edges = edges[:_MAX_EDGES]

    return {
        "nodes": nodes,
        "edges": edges,
        "seed_ids": seeds,
        "captured_at": _now_iso(),
        "counts": {"nodes": len(nodes), "edges": len(edges)},
        "truncated": truncated,
    }


def _summary(delta: dict[str, Any]) -> str:
    """Человекочитаемая RU/EN-сводка дельты (для заголовка экрана diff'а)."""
    n_add = len(delta["added_nodes"])
    n_rem = len(delta["removed_nodes"])
    n_chg = len(delta["changed_nodes"])
    e_add = len(delta["added_edges"])
    e_rem = len(delta["removed_edges"])
    e_chg = len(delta["changed_edges"])
    return (
        f"Узлы/Nodes: +{n_add} добавлено/added · −{n_rem} удалено/removed · "
        f"~{n_chg} изменено/changed; "
        f"Рёбра/Edges: +{e_add} добавлено/added · −{e_rem} удалено/removed · "
        f"~{e_chg} изменено/changed"
    )


class Snapshot(BaseModel):
    """Снимок графа для сравнения (форма ``{nodes, edges}``)."""

    nodes: list[dict[str, Any]] = Field(default_factory=list)
    edges: list[dict[str, Any]] = Field(default_factory=list)


class CompareBody(BaseModel):
    """Тело ``POST /compare`` — два снимка ``before`` / ``after``."""

    before: Snapshot = Field(default_factory=Snapshot)
    after: Snapshot = Field(default_factory=Snapshot)
    node_key: str = "id"
    edge_key: str = "id"


class LiveDiffBody(BaseModel):
    """Тело ``POST /`` — снимок «ДО» + seed для съёма живого «ПОСЛЕ»."""

    before: Snapshot = Field(default_factory=Snapshot)
    node_ids: list[str] = Field(default_factory=list)
    expand: int = 1
    node_key: str = "id"
    edge_key: str = "id"


def _diff_payload(
    before: dict[str, Any],
    after: dict[str, Any],
    node_key: str,
    edge_key: str,
) -> dict[str, Any]:
    """Построить дельту двух снимков + счётчики и сводку (общий хелпер)."""
    delta = diff_graphs(
        before,
        after,
        node_key=node_key or "id",
        edge_key=edge_key or "id",
    ).as_dict()
    delta["summary"] = _summary(delta)
    delta["before_counts"] = {
        "nodes": len(before.get("nodes", [])),
        "edges": len(before.get("edges", [])),
    }
    delta["after_counts"] = {
        "nodes": len(after.get("nodes", [])),
        "edges": len(after.get("edges", [])),
    }
    return delta


@router.get("/snapshot")
def snapshot(
    node_ids: str = Query(default="", description="seed-узлы через запятую"),
    expand: int = Query(default=1, ge=0, le=3),
) -> dict[str, Any]:
    """Снять нормализованный снимок живого подграфа вокруг seed-узлов (§14.6).

    Если ``node_ids`` пуст — берётся выборка узлов из живого графа, чтобы экран
    показал осмысленный подграф без ручного ввода id. Форма ответа готова к
    передаче как ``before`` / ``after`` в ``/compare``.
    """
    ids = [x for x in node_ids.split(",") if x.strip()]
    return _capture(ids, expand)


@router.post("/compare")
def compare(body: CompareBody) -> dict[str, Any]:
    """Дельта двух переданных снимков графа — полностью офлайн-diff (§14.6).

    Ответ — узлы/рёбра ``added`` / ``removed`` / ``changed`` (изменённые несут
    ``_before`` / ``_after``) + агрегированные счётчики и RU/EN-сводка.
    """
    return _diff_payload(
        body.before.model_dump(),
        body.after.model_dump(),
        body.node_key,
        body.edge_key,
    )


@router.post("")
def live_diff(body: LiveDiffBody) -> dict[str, Any]:
    """Дельта «переданный ДО» vs «живое ПОСЛЕ» одним вызовом (§14.6).

    Клиент передаёт снимок «до курирования» и seed-узлы; сервер снимает текущее
    (живое, сервер-профиль :8000) состояние подграфа как «после» и возвращает
    дельту. Удобно для кнопки «Сравнить с текущим состоянием» на экране diff'а.
    """
    if not body.before.nodes and not body.before.edges:
        raise HTTPException(
            status_code=422,
            detail="before-снимок пуст: сначала снимите /snapshot до курирования",
        )
    after = _capture(body.node_ids, body.expand)
    payload = _diff_payload(
        body.before.model_dump(),
        {"nodes": after["nodes"], "edges": after["edges"]},
        body.node_key,
        body.edge_key,
    )
    payload["after_snapshot_meta"] = {
        "captured_at": after["captured_at"],
        "seed_ids": after["seed_ids"],
        "truncated": after["truncated"],
    }
    return payload


@router.get("/legend")
def legend() -> dict[str, Any]:
    """Легенда категорий дельты для UI — цвета/подписи added/removed/changed."""
    return {
        "categories": [
            {"key": "added", "label_ru": "Добавлено", "label_en": "Added", "tone": "emerald"},
            {"key": "removed", "label_ru": "Удалено", "label_en": "Removed", "tone": "red"},
            {"key": "changed", "label_ru": "Изменено", "label_en": "Changed", "tone": "amber"},
        ],
        "note": (
            "Изменённые узлы/рёбра несут снимки _before/_after — правка любого "
            "курируемого поля (verified, review_status, confidence, …) видна пофайлово."
        ),
    }
