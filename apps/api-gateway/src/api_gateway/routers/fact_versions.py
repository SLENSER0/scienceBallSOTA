"""§3.7 «Машина времени факта» — эволюция каждого числа сущности + never-overwrite-reviewed.

Даёт Entity Detail (§5.2.4) ленту версий любого factual-поля: v1 — исходное
извлечение (с `extractor_run_id`), v≥2 — правки куратора, каждая как **новая
версия** со ссылкой на решение (`Decision`, §16.7), а не перезапись. Реализует
критерий §3.7 «изменение факта создаёт новую версию, старая остаётся достижима»
и инвариант «never overwrite reviewed fields automatically».

Endpoints (off the ``/api/v1`` root, вне ``/entities/{id}/neighbors`` graph-роутера):

* ``GET  /api/v1/fact-versions/{entity_id}``                       — обзор versionable-полей.
* ``GET  /api/v1/fact-versions/{entity_id}/{field}``               — полная лента версий поля.
* ``GET  /api/v1/fact-versions/{entity_id}/{field}/decisions``     — история решений куратора.
* ``POST /api/v1/fact-versions/{entity_id}/{field}/revise``        — добавить новую версию.

Запись RBAC-gated (curator+), аудируется и эхо-логируется в governance/curation
(§16 / §24.14). Никакого LLM/сети — чтение из живого графа + локальные версии.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api_gateway import audit
from api_gateway.auth import current_role, current_user
from api_gateway.deps import get_store
from api_gateway.fact_versions_store import (
    EntityNotFound,
    FieldNotVersionable,
    InvalidRevision,
    ReviewedProtected,
    decision_history,
    entity_facts,
    revise,
    timeline,
)

router = APIRouter(prefix="/api/v1/fact-versions", tags=["fact-versions"])

# Те же write-capable роли, что и у ручной коррекции/курирования (§16/§19).
_CAN_REVISE = {"admin", "curator", "researcher", "analyst", "project_manager"}


def _require_revise(role: str) -> None:
    if role not in _CAN_REVISE:
        raise HTTPException(status_code=403, detail="role may not revise facts")


# -- reads ---------------------------------------------------------------------
@router.get("/{entity_id}")
def facts(entity_id: str) -> dict:
    """Обзор всех versionable factual-полей сущности со сводкой по каждой ленте."""
    try:
        return entity_facts(entity_id)
    except EntityNotFound as exc:
        raise HTTPException(status_code=404, detail="entity not found") from exc


@router.get("/{entity_id}/source")
def entity_source(entity_id: str) -> dict:
    """Провенанс факта (§3.7/§5.2.4): связанные Evidence (SUPPORTED_BY) + дедуп исходных документов.

    ВАЖНО: объявлено ТЕКСТУАЛЬНО ДО ``/{entity_id}/{field}``, иначе FastAPI сматчил
    бы "source" как {field}. Пустые массивы (а не ошибка) для seed-заглушек без
    привязанного Evidence; 404 только если самой сущности нет.
    """
    store = get_store()
    if store.get_node(entity_id) is None:
        raise HTTPException(status_code=404, detail="entity not found")

    evidence: list[dict] = []
    doc_ids: list[str] = []
    try:
        ev = store.rows(
            "MATCH (m:Node {id:$id})-[r:Rel]-(e:Node {label:'Evidence'}) "
            "WHERE r.type='SUPPORTED_BY' "
            "RETURN e.id, e.text, e.page, e.doc_id, e.source_type, e.evidence_strength, e.confidence "
            "LIMIT 25",
            {"id": entity_id},
        )
    except Exception:
        ev = []
    for row in ev:
        eid, text, page, doc_id, source_type, strength, conf = (list(row) + [None] * 7)[:7]
        try:
            page_val = int(page) if page is not None else None
        except (TypeError, ValueError):
            page_val = None
        try:
            conf_val = float(conf) if conf is not None else None
        except (TypeError, ValueError):
            conf_val = None
        evidence.append(
            {
                "evidenceId": eid,
                "text": text,
                "page": page_val,
                "docId": doc_id,
                "sourceType": source_type,
                "evidenceStrength": strength,
                "confidence": conf_val,
            }
        )
        if doc_id and doc_id not in doc_ids:
            doc_ids.append(doc_id)

    documents: list[dict] = []
    if doc_ids:
        try:
            drows = store.rows(
                "MATCH (d:Node) WHERE d.label IN ['Document','Paper'] AND d.id IN $ids "
                "RETURN d.id, coalesce(d.name, d.canonical_name, d.id), d.label",
                {"ids": doc_ids},
            )
        except Exception:
            drows = []
        by_id: dict[str, dict] = {}
        for row in drows:
            did, title, label = (list(row) + [None] * 3)[:3]
            if did is not None:
                by_id[did] = {"docId": did, "title": title, "docType": (label or "").lower()}
        # Порядок документов — по первому появлению в evidence.
        documents = [by_id[did] for did in doc_ids if did in by_id]

    # Также резолвим документы, достижимые НАПРЯМУЮ через SUPPORTED_BY: часть фактов
    # ссылается прямо на :Paper/:Document, а не только через Evidence.doc_id. Union + дедуп,
    # чтобы «Источник» находился и когда doc_id не сматчился на id узла.
    seen_docs = {d["docId"] for d in documents}
    try:
        prows = store.rows(
            "MATCH (m:Node {id:$id})-[r:Rel]-(d:Node) "
            "WHERE r.type='SUPPORTED_BY' AND d.label IN ['Document','Paper'] "
            "RETURN d.id, coalesce(d.name, d.canonical_name, d.id), d.label LIMIT 10",
            {"id": entity_id},
        )
    except Exception:
        prows = []
    for row in prows:
        did, title, label = (list(row) + [None] * 3)[:3]
        if did is not None and did not in seen_docs:
            seen_docs.add(did)
            documents.append({"docId": did, "title": title, "docType": (label or "").lower()})

    return {"entityId": entity_id, "evidence": evidence, "documents": documents}


@router.get("/{entity_id}/{field}")
def field_timeline(entity_id: str, field: str) -> dict:
    """Полная лента версий поля: v1 (извлечение) → все правки куратора."""
    try:
        return timeline(entity_id, field).as_dict()
    except EntityNotFound as exc:
        raise HTTPException(status_code=404, detail="entity not found") from exc
    except FieldNotVersionable as exc:
        raise HTTPException(status_code=422, detail=f"field not versionable: {field}") from exc


@router.get("/{entity_id}/{field}/decisions")
def field_decisions(entity_id: str, field: str) -> dict:
    """История решений куратора (§16.7) по данному полю, oldest→newest."""
    try:
        timeline(entity_id, field)  # validate entity + field exist
    except EntityNotFound as exc:
        raise HTTPException(status_code=404, detail="entity not found") from exc
    except FieldNotVersionable as exc:
        raise HTTPException(status_code=422, detail=f"field not versionable: {field}") from exc
    return {"entityId": entity_id, "field": field, "decisions": decision_history(entity_id, field)}


# -- write (new version, never overwrite reviewed) -----------------------------
class ReviseBody(BaseModel):
    """Правка factual-поля как новой версии (§3.7)."""

    value: Any = None
    action: str = Field(default="correct")  # correct | accept | reject | reopen
    review_status: str | None = None
    reason: str = ""
    curation_event_id: str | None = None
    force_curation: bool = False


@router.post("/{entity_id}/{field}/revise")
def revise_field(
    entity_id: str,
    field: str,
    body: ReviseBody,
    role: str = Depends(current_role),
    user: str = Depends(current_user),
) -> dict:
    """Добавить новую версию поля (старая сохраняется) со ссылкой на решение.

    Инвариант §3.7: если текущая версия `accepted/corrected`, авто-правка
    отклоняется (409) — нужен явный curation-override (`force_curation=true` +
    `curation_event_id`). Событие аудируется и эхо-логируется в curation (§16).
    """
    _require_revise(role)
    try:
        version, tl = revise(
            entity_id,
            field,
            value=body.value,
            action=body.action,
            review_status=body.review_status,
            reason=body.reason,
            actor=user,
            curation_event_id=body.curation_event_id,
            force_curation=body.force_curation,
        )
    except EntityNotFound as exc:
        raise HTTPException(status_code=404, detail="entity not found") from exc
    except FieldNotVersionable as exc:
        raise HTTPException(status_code=422, detail=f"field not versionable: {field}") from exc
    except ReviewedProtected as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except InvalidRevision as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    detail = {
        "entity_id": entity_id,
        "field": field,
        "version": version.version,
        "action": version.action,
        "review_status": version.review_status,
        "decision_id": version.decision_id,
        "curation_event_id": version.curation_event_id,
        "reason": version.reason,
    }
    # §24.14 audit + §16 governance/curation echo (один append-only лог).
    audit.record("revise_fact", user=user, role=role, detail=detail)
    audit.record("curation.fact_revised", user=user, role=role, detail=detail)

    return {"created": version.as_dict(), "timeline": tl.as_dict()}
