"""Attachments-aware chat turn: «спросить агента о выделенном подграфе» в СЕССИИ (§14.4 / §5.2.3).

Штатный ``POST /chat/sessions/{sid}/messages`` (:mod:`routers.chat`) принимает
поле ``attachments`` нетипизированно и *ничего с ним не делает* (в коде прямо
написано ``accepted; not persisted separately``). Отдельный роутер
:mod:`routers.subgraph_ask` умеет грунтовать агента на lasso-выделении, но он
stateless — вне истории сессии. §14.4 (строки 3089-3090) требует ровно стыка
этих двух: пользователь тянет lasso по графу, а выделенные ``node_ids`` /
подграф уходят *вложением* в сообщение чат-сессии, агент грунтуется именно на
них, и весь ход (вопрос + ответ + артефакты) ложится в историю сессии.

Этот НОВЫЙ роутер закрывает этот шов, ничего не переписывая:

* парсер вложений — уже готовый, но до сих пор осиротевший (нигде не
  импортировался) :func:`api_gateway.chat_attachments.parse_attachments`
  (валидирует ``node_ids`` / ``subgraph`` / ``doc_ids`` из §5.2.3 lasso);
* билдер подграфа — тот же ``store.subgraph_from_ids``, что кормит canvas и
  :mod:`routers.subgraph_ask`;
* описание подграфа и grounded-prompt — переиспользуем ``_describe_subgraph`` /
  ``_grounded_query`` из :mod:`routers.subgraph_ask` (единый текст grounding);
* хранилище сессий и правило владения — тот же ``ChatStore`` и
  ``_owned_session`` из :mod:`routers.chat` (одна и та же ``chat.db``, единая
  проверка 404-на-чужую), поэтому сессии, созданные обычным chat-роутером,
  видны здесь и наоборот;
* прогон агента — тот же in-process ``agent_service.agent.answer_query``.

Ответ отдаёт ``stream_url``, указывающий на *существующий*
``GET /chat/sessions/{sid}/stream`` — сохранённый ``AnswerPayload`` реплеится
как типизированные SSE-события §5.3 без нового стрим-кода. Плюс инлайн
возвращаем ``answer`` + ``subgraph`` + ``focus``, чтобы UI отрисовал ответ сразу
(как subgraph_ask), а ссылка на сессию давала персистентность (§14.4).

Read-only относительно графа: узлов/рёбер не создаёт, только читает подграф.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api_gateway.auth import current_role, current_user
from api_gateway.chat_attachments import is_empty, parse_attachments
from api_gateway.deps import get_store
from api_gateway.routers.chat import _chat, _owned_session
from api_gateway.routers.subgraph_ask import (
    _MAX_IDS,
    _describe_subgraph,
    _grounded_query,
)
from kg_common import GraphResponse

router = APIRouter(prefix="/api/v1/chat-attach", tags=["chat"])


class AttachMessageBody(BaseModel):
    """POST-тело: текст + вложение lasso-выделения (§5.2.3).

    ``attachments`` — единый объект ``{ node_ids?, subgraph?, doc_ids? }`` (как в
    :func:`parse_attachments`). ``expand`` — радиус подмешивания соседей вокруг
    выделения (0 = строго выделенное).
    """

    content: str = ""
    attachments: dict[str, Any] | None = None
    expand: int = Field(default=0, ge=0, le=2)


def _subgraph_for(store: Any, att: Any, expand: int) -> GraphResponse:
    """Собрать подграф для grounding: живой из ``node_ids`` или переданный клиентом.

    Приоритет — свежий подграф из графа по ``node_ids`` (``subgraph_from_ids``);
    если id нет, но клиент прислал готовый ``subgraph`` (снимок с canvas) —
    валидируем его в :class:`GraphResponse`. Иначе — пустой подграф.
    """
    if att.node_ids:
        ids = list(att.node_ids)
        if len(ids) > _MAX_IDS:
            raise HTTPException(
                status_code=413,
                detail=f"слишком большое выделение: {len(ids)} > {_MAX_IDS} узлов",
            )
        return store.subgraph_from_ids(ids, expand=expand)
    if att.subgraph:
        try:
            return GraphResponse.model_validate(att.subgraph)
        except Exception as exc:  # payload-валидация клиента → 400
            raise HTTPException(
                status_code=400, detail=f"некорректный subgraph во вложении: {exc}"
            ) from exc
    return GraphResponse(nodes=[], edges=[])


@router.post("/sessions/{sid}/messages")
def post_attached_message(
    sid: str,
    body: AttachMessageBody,
    role: str = Depends(current_role),
    user: str = Depends(current_user),
) -> dict[str, Any]:
    """Персистентный чат-ход с lasso-вложением: грунтовать агента и сохранить в сессию.

    Тело: ``{ content?, attachments?{node_ids,subgraph,doc_ids}, expand? }``.
    Ответ: ``{ message_id, stream_url, answer, subgraph, focus }`` — ``answer``
    рендерится сразу, ``stream_url`` реплеит его как SSE (§5.3), а ход сохранён
    в историю сессии (виден в ``GET /chat/sessions/{sid}``).
    """
    _owned_session(sid, user)  # 404 на чужую/несуществующую (не течёт §19)

    att = parse_attachments(body.attachments)
    content = (body.content or "").strip()
    if is_empty(att) and not content:
        raise HTTPException(
            status_code=400,
            detail="пустой ход: приложите выделение (node_ids/subgraph) или введите текст",
        )

    store = get_store()
    sub = _subgraph_for(store, att, body.expand)

    # Grounding: описываем выделенный подграф и склеиваем с вопросом (переиспуск
    # текста из subgraph_ask). Без вложения — обычный вопрос по тексту.
    by_type: dict[str, list[str]] = {}
    if sub.nodes:
        desc, by_type = _describe_subgraph(sub)
        query = _grounded_query(desc, content)
    else:
        if not content:
            raise HTTPException(
                status_code=404,
                detail="выделенные узлы не найдены в графе (устаревшее выделение?)",
            )
        query = content

    chat = _chat()
    # Сохраняем ход пользователя. Текст для истории — вопрос + компактная пометка
    # о вложении (чтобы в истории было видно, что спрашивали о выделении).
    user_text = content or "(разбор выделенного подграфа)"
    if not is_empty(att):
        tag = f"  [вложение: {len(att.node_ids)} узлов"
        if body.expand:
            tag += f", +{body.expand} hop"
        tag += "]"
        user_text += tag
    user_mid = f"msg:{uuid.uuid4().hex[:12]}"
    chat.add_message(sid, "user", user_text, user_mid)

    # Тот же in-process прогон LangGraph, что и chat-роутер (§14.4).
    from agent_service.agent import answer_query

    payload = answer_query(query, store, role=role, use_llm=True)
    asst_mid = f"msg:{uuid.uuid4().hex[:12]}"
    # AnswerPayload JSON несёт ответ + артефакты; существующий /stream реплеит его.
    chat.add_message(sid, "assistant", payload.model_dump_json(by_alias=True), asst_mid)

    return {
        "message_id": asst_mid,
        "stream_url": f"/api/v1/chat/sessions/{sid}/stream?message_id={asst_mid}",
        "answer": payload.model_dump(by_alias=True),
        "subgraph": sub.model_dump(by_alias=True),
        "focus": {
            "selected": len(att.node_ids),
            "node_count": len(sub.nodes),
            "edge_count": len(sub.edges),
            "expand": body.expand,
            "entity_types": {t: len(v) for t, v in by_type.items()},
            "doc_ids": list(att.doc_ids),
            "question": content,
        },
    }
