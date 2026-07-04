"""«Спросить агента о выделенном подграфе» / ask-agent-about-selected (§17.8, §5.2.3).

Lasso/box-выделение узлов на canvas графа связывается с агентным чатом: фронт
собирает ``node_ids`` выделенного кластера, а этот роутер грунтует агента ровно
на этом подграфе и возвращает связный ответ — что связывает эти сущности, какие
ключевые свойства и где пробелы.

Дизайн:
- переиспользуем уже готовые кирпичи, ничего не переписываем:
  * :meth:`store.subgraph_from_ids` — тот же билдер ``GraphResponse``, что кормит
    canvas (2D/3D) и community-панель (§17.9);
  * :func:`agent_service.agent.answer_query` — тот же in-process прогон LangGraph,
    что запускает chat-роутер (§14.4). Мы лишь формируем grounded-запрос из
    текстового описания выделенного подграфа и (опционально) вопроса пользователя;
- работает на живом server-профиле (Neo4j :8000) через ``get_store`` — как chat/
  gds-live; на embedded (Kuzu) тоже корректно, т.к. ``subgraph_from_ids`` и
  ``answer_query`` профиль-агностичны;
- read-only: рёбер/узлов не создаёт, только читает подграф и рассуждает о нём.

Отдельный префикс ``/subgraph-ask`` не конфликтует с ``/chat`` и ``/graph``.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api_gateway.auth import current_role
from api_gateway.deps import get_store
from kg_common import GraphResponse

router = APIRouter(prefix="/api/v1/subgraph-ask", tags=["subgraph-ask"])

# Предохранители: не раздуваем prompt и запрос на огромное выделение.
_MAX_IDS = 120
_MAX_EDGES_IN_PROMPT = 40
_MAX_NODES_PER_TYPE = 12


class SubgraphAskBody(BaseModel):
    """POST-тело: выделенные узлы + опциональный вопрос + радиус контекста."""

    node_ids: list[str] = Field(default_factory=list)
    question: str = ""
    # 0 — рассуждать строго о выделенном; 1..2 — подмешать N-hop соседей как контекст.
    expand: int = Field(default=0, ge=0, le=2)


def _label_of(n: Any) -> str:
    """Читаемое имя узла (label в GraphNode = name)."""
    return (getattr(n, "label", None) or getattr(n, "id", "") or "").strip()


def _describe_subgraph(sub: GraphResponse) -> tuple[str, dict[str, list[str]]]:
    """Собрать текстовое описание подграфа для grounding + группировку по типам.

    Возвращает (prompt-текст, {тип -> имена}). Имена группируются по типу узла
    (Material/Property/…), рёбра перечисляются как ``A —REL→ B`` до потолка.
    """
    by_type: dict[str, list[str]] = {}
    id_to_label: dict[str, str] = {}
    for n in sub.nodes:
        name = _label_of(n)
        id_to_label[n.id] = name or n.id
        by_type.setdefault(n.type or "Entity", [])
        if name and name not in by_type[n.type or "Entity"]:
            by_type[n.type or "Entity"].append(name)

    lines: list[str] = []
    for ntype, names in sorted(by_type.items(), key=lambda kv: -len(kv[1])):
        shown = names[:_MAX_NODES_PER_TYPE]
        more = len(names) - len(shown)
        tail = f" (и ещё {more})" if more > 0 else ""
        if shown:
            lines.append(f"- {ntype}: {', '.join(shown)}{tail}")

    rel_lines: list[str] = []
    for e in sub.edges[:_MAX_EDGES_IN_PROMPT]:
        src = id_to_label.get(e.source, e.source)
        dst = id_to_label.get(e.target, e.target)
        rel_lines.append(f"  {src} —{e.type or e.label}→ {dst}")
    if len(sub.edges) > _MAX_EDGES_IN_PROMPT:
        rel_lines.append(f"  … (+{len(sub.edges) - _MAX_EDGES_IN_PROMPT} связей)")

    parts = ["Сущности выделенного подграфа:", *lines]
    if rel_lines:
        parts += ["Связи между ними:", *rel_lines]
    return "\n".join(parts), by_type


def _grounded_query(desc: str, question: str) -> str:
    """Сформировать grounded-запрос к агенту из описания подграфа и вопроса."""
    q = (question or "").strip()
    if q:
        return (
            "Пользователь выделил на графе знаний подграф (кластер сущностей). "
            "Отвечай, опираясь ИМЕННО на этот выделенный подграф.\n\n"
            f"{desc}\n\n"
            f"Вопрос пользователя: {q}"
        )
    return (
        "Пользователь выделил на графе знаний подграф (кластер сущностей). "
        "Кратко и по делу объясни, что связывает эти сущности: какая технология/"
        "материал в центре, ключевые свойства и режимы, какие связи наиболее важны "
        "и где в данных пробелы. Опирайся ИМЕННО на этот выделенный подграф.\n\n"
        f"{desc}"
    )


@router.post("")
def ask_about_subgraph(
    body: SubgraphAskBody,
    role: str = Depends(current_role),
) -> dict[str, Any]:
    """Грунтовать агента на выделенном подграфе и вернуть ответ + сам подграф.

    Тело: ``{ node_ids, question?, expand? }``. Ответ:
    ``{ answer: AnswerPayload, subgraph: GraphResponse, focus: {...} }`` —
    ``answer`` рендерится как обычный ответ ассистента, ``subgraph`` подсвечивает
    ровно то, о чём рассуждал агент.
    """
    ids = [i for i in dict.fromkeys(body.node_ids) if i]  # dedup, keep order
    if not ids:
        raise HTTPException(status_code=400, detail="node_ids пуст — сначала выделите узлы")
    if len(ids) > _MAX_IDS:
        raise HTTPException(
            status_code=413,
            detail=f"слишком большое выделение: {len(ids)} > {_MAX_IDS} узлов",
        )

    store = get_store()
    sub = store.subgraph_from_ids(ids, expand=body.expand)
    if not sub.nodes:
        raise HTTPException(
            status_code=404,
            detail="выделенные узлы не найдены в графе (устаревшее выделение?)",
        )

    desc, by_type = _describe_subgraph(sub)
    query = _grounded_query(desc, body.question)

    # Тот же in-process прогон LangGraph, что и chat-роутер (§14.4).
    from agent_service.agent import answer_query

    payload = answer_query(query, store, role=role, use_llm=True)

    return {
        "answer": payload.model_dump(by_alias=True),
        "subgraph": sub.model_dump(by_alias=True),
        "focus": {
            "selected": len(ids),
            "node_count": len(sub.nodes),
            "edge_count": len(sub.edges),
            "expand": body.expand,
            "entity_types": {t: len(v) for t, v in by_type.items()},
            "question": (body.question or "").strip(),
        },
    }
