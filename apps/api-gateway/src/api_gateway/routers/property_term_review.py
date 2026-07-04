"""Эмиссия ``new_property_term`` (schema_change) в очередь ревью (§8.6).

RU: когда извлекатель встречает неизвестное свойство/термин, он не должен молча
его отбрасывать или угадывать — управляемая эволюция онтологии требует, чтобы такой
термин попал к куратору. Этот роутер прогоняет наблюдаемые property-упоминания через
УЖЕ ГОТОВЫЙ каскадный маппер (§8.6 :class:`kg_er.decision.PropertyMapper`): точный/
синоним-lookup → fuzzy fallback; при top-1 similarity ниже порога упоминание
помечается ``review_needed`` и порождает событие ``schema_change`` с причиной
``new_property_term`` (§12.2), которое ПЕРСИСТИТСЯ в очередь ревью
(§16.5 :class:`kg_common.storage.review_queue.ReviewQueue`) с дедупликацией по
стабильному ``dedup_key`` (§16.4) — повторная эмиссия того же термина не плодит задач.
Совместимость единицы измерения с ``allowed_units`` canonical-свойства проверяется
через тот же маппер (флаг ``unit_mismatch``, §8.6/§9.2 Step 5).

EN: emit a ``new_property_term`` schema-change review task when an extractor meets an
unknown property term. Reuses the shipped cascade mapper (exact/synonym → fuzzy) and
the shipped persistent review queue; nothing is re-implemented. Every enqueue is
idempotent by ``dedup_key`` so the same unknown term never duplicates a task.

Endpoints (schema namespace, §6.2):

* ``POST /api/v1/schema/property-terms/map``      — сопоставить упоминания, эмитить
  ``new_property_term`` для неизвестных; вернуть решения + черновики ``CurationEvent``.
* ``GET  /api/v1/schema/property-terms/pending``  — открытые задачи ``new_property_term``
  из очереди ревью (priority desc, created_at asc).
* ``GET  /api/v1/schema/property-terms/vocab``    — сводка controlled-vocabulary
  (§8.2): число терминов, sample canonical-id, активный порог.
"""

from __future__ import annotations

import functools
import hashlib
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from api_gateway.auth import current_role
from kg_common import get_settings

router = APIRouter(prefix="/api/v1/schema/property-terms", tags=["schema", "curation"])

# --- constants (§8.6 / §12.2 / §16.2) ----------------------------------------
#: task_type/reason задачи ревью для неизвестного property-термина (§8.6 acceptance).
REASON_NEW_PROPERTY_TERM = "new_property_term"
#: CurationEvent.action для расширения схемы (§12.3 enum).
ACTION_SCHEMA_CHANGE = "schema_change"
#: CurationEvent.target_type — термин нацелен на схему (§12.3 enum).
TARGET_TYPE_SCHEMA = "schema"
#: kind в очереди ревью (§16.4 review_tasks.kind); совпадает с reason.
QUEUE_KIND = REASON_NEW_PROPERTY_TERM
#: Порог semantic-fallback по умолчанию (§8.6 ``property_map_min_sim``).
DEFAULT_MIN_SIM = 0.82
#: Базовый приоритет new_property_term (§16.4: самый низкий из 6 типов = rank 1).
_BASE_PRIORITY = 10.0


def _now() -> str:
    return datetime.now(UTC).isoformat()


# ---------------------------------------------------------------------------
# Lazy singletons (mapper vocab + persistent review queue)
# ---------------------------------------------------------------------------
@functools.lru_cache(maxsize=1)
def _mapper(min_sim: float = DEFAULT_MIN_SIM):
    """Каскадный property-маппер поверх controlled-vocabulary (§8.6). Кэшируется."""
    from kg_er.decision.property_mapper import PropertyMapper
    from kg_er.store.property_vocab import default_vocabulary

    return PropertyMapper(default_vocabulary(), min_sim=min_sim)


@functools.lru_cache(maxsize=1)
def _queue():
    """Персистентная очередь ревью (§16.5). SQLite-файл под ``var/`` (server-safe)."""
    from kg_common.storage.review_queue import ReviewQueue

    settings = get_settings()
    db_path = settings.path("var", "review_queue.db")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    q = ReviewQueue(f"sqlite:///{db_path}")
    q.migrate()
    return q


# ---------------------------------------------------------------------------
# Dedup / priority (§16.4, согласовано с review_task_gen)
# ---------------------------------------------------------------------------
def make_dedup_key(term_norm: str, unit_norm: str = "") -> str:
    """Стабильный ``dedup_key`` (§16.4): sha1 по (reason, нормализованный термин, unit).

    Одна открытая задача на (термин, unit): повторная эмиссия того же неизвестного
    термина не плодит задач (идемпотентность §16.5). ``unit_norm`` различает
    ``unit_mismatch``-вариант того же термина от чистого ``new_property_term``.
    """
    raw = "|".join([REASON_NEW_PROPERTY_TERM, term_norm, unit_norm])
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
    return f"rev:{digest}"


def compute_priority(*, score: float, occurrences: int, unit_mismatch: bool) -> float:
    """Приоритет new_property_term (§16.4).

    База — низкая (rank 1). Чем дальше термин от известного (меньше ``score`` →
    вероятнее по-настоящему новый термин), чем чаще встречается и есть ли конфликт
    единицы — тем выше приоритет. Округляется до 6 знаков.
    """
    dist_term = 1.0 - _clamp01(score)
    occ_term = 0.1 * min(max(occurrences, 0), 10)
    unit_term = 0.5 if unit_mismatch else 0.0
    return round(_BASE_PRIORITY + dist_term + occ_term + unit_term, 6)


def _clamp01(v: Any) -> float:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return 0.0
    return 0.0 if f < 0.0 else 1.0 if f > 1.0 else f


def _norm(text: Any) -> str:
    return " ".join(str(text or "").split()).lower()


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------
class PropertyMention(BaseModel):
    mention: str = Field(..., min_length=1, description="Сырой property-термин из извлечения")
    unit: str | None = Field(default=None, description="Единица измерения упоминания (опц.)")
    context: str | None = Field(default=None, description="Контекст/сниппет, где встречен термин")
    doc_id: str | None = Field(default=None, description="Документ-источник (для payload)")
    occurrences: int = Field(default=1, ge=1, description="Сколько раз встречен в батче")


class MapRequest(BaseModel):
    mentions: list[PropertyMention] = Field(..., min_length=1, max_length=500)
    min_sim: float | None = Field(
        default=None, ge=0.0, le=1.0, description="Override порога semantic-fallback (§8.6)"
    )
    persist: bool = Field(
        default=True, description="Персистить new_property_term в очередь ревью (§16.5)"
    )
    actor_id: str = Field(default="system", description="Автор эмиссии (CurationEvent.actor_id)")


# ---------------------------------------------------------------------------
# Core: map one mention -> decision (+ optional schema_change emission)
# ---------------------------------------------------------------------------
def _schema_change_event(
    *, term: str, nearest: str | None, score: float, actor_id: str, context: str | None
) -> dict[str, Any]:
    """Черновик ``CurationEvent`` формата §12.3 (action=schema_change, target=schema)."""
    return {
        "action": ACTION_SCHEMA_CHANGE,
        "actor_id": actor_id,
        "target_type": TARGET_TYPE_SCHEMA,
        "target_id": f"schema:property:{term}",
        "before": None,
        "after": {
            "term": term,
            "reason": REASON_NEW_PROPERTY_TERM,
            "mapping_suggestion": nearest,
            "score": round(float(score), 4),
        },
        "reason": REASON_NEW_PROPERTY_TERM,
        "created_at": _now(),
    }


def evaluate_mention(m: PropertyMention, mapper: Any) -> dict[str, Any]:
    """Сопоставить одно упоминание и решить: mapped / new_property_term / unit_mismatch.

    Переиспользует :meth:`PropertyMapper.map` (§8.6): точный/синоним → fuzzy →
    порог. Ниже порога — ``review_needed`` с причиной ``new_property_term``.
    Дополнительно поднимает ``unit_mismatch``, если термин сопоставлен, но unit
    несовместим с ``allowed_units`` canonical-свойства (§8.6/§9.2 Step 5).
    """
    result = mapper.map(m.mention, unit=m.unit)
    term_norm = _norm(m.mention)
    unit_norm = _norm(m.unit)
    is_new = result.status == "review_needed"
    unit_mismatch = (not is_new) and (not result.unit_ok)
    flags: list[str] = []
    if is_new:
        flags.append(REASON_NEW_PROPERTY_TERM)
    if unit_mismatch:
        flags.append("unit_mismatch")
    return {
        "mention": m.mention,
        "unit": m.unit,
        "canonical_id": result.canonical_id,
        "score": round(float(result.score), 4),
        "status": result.status,
        "unit_ok": bool(result.unit_ok),
        "flags": flags,
        "review_needed": is_new,
        "_term_norm": term_norm,
        "_unit_norm": unit_norm if unit_mismatch else "",
        "_occurrences": m.occurrences,
        "_context": m.context,
        "_doc_id": m.doc_id,
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.post("/map")
def map_terms(req: MapRequest, role: str = Depends(current_role)) -> dict[str, Any]:
    """Сопоставить property-упоминания; эмитить ``new_property_term`` для неизвестных (§8.6).

    Для каждого упоминания возвращается решение маппера; для упоминаний со статусом
    ``review_needed`` формируется событие ``schema_change`` (§12.2) с причиной
    ``new_property_term`` и, если ``persist``, ставится задача в очередь ревью (§16.5)
    с дедупликацией (§16.4). ``unit_mismatch`` (термин известен, но unit несовместим)
    отражается флагом и тоже может уходить в ревью.
    """
    min_sim = req.min_sim if req.min_sim is not None else DEFAULT_MIN_SIM
    mapper = _mapper(min_sim)
    q = _queue() if req.persist else None

    results: list[dict[str, Any]] = []
    emitted: list[dict[str, Any]] = []
    for m in req.mentions:
        ev = evaluate_mention(m, mapper)
        needs_task = ev["review_needed"] or ("unit_mismatch" in ev["flags"])
        if needs_task:
            dedup_key = make_dedup_key(ev["_term_norm"], ev["_unit_norm"])
            task_id = dedup_key  # deterministic id == dedup_key (§16.4 idempotent)
            priority = compute_priority(
                score=ev["score"],
                occurrences=int(ev["_occurrences"]),
                unit_mismatch="unit_mismatch" in ev["flags"],
            )
            event = _schema_change_event(
                term=m.mention,
                nearest=ev["canonical_id"],
                score=ev["score"],
                actor_id=req.actor_id,
                context=ev["_context"],
            )
            if q is not None:
                from kg_common.storage.review_queue import ReviewTask

                q.enqueue(
                    ReviewTask(
                        task_id=task_id,
                        target_id=event["target_id"],
                        kind=QUEUE_KIND,
                        priority=priority,
                        dedup_key=dedup_key,
                        created_at=_now(),
                    )
                )
            emitted.append(
                {
                    "task_id": task_id,
                    "dedup_key": dedup_key,
                    "kind": QUEUE_KIND,
                    "priority": priority,
                    "target_id": event["target_id"],
                    "flags": ev["flags"],
                    "curation_event": event,
                    "payload": {
                        "term": m.mention,
                        "unit": m.unit,
                        "context": ev["_context"],
                        "doc_id": ev["_doc_id"],
                        "occurrences": int(ev["_occurrences"]),
                        "nearest": ev["canonical_id"],
                        "score": ev["score"],
                    },
                }
            )
        # drop internal helper keys from the public per-mention result
        results.append({k: v for k, v in ev.items() if not k.startswith("_")})

    return {
        "count": len(results),
        "emitted": len(emitted),
        "persisted": bool(req.persist),
        "min_sim": min_sim,
        "results": results,
        "tasks": emitted,
    }


@router.get("/pending")
def pending(limit: int = 50, _role: str = Depends(current_role)) -> dict[str, Any]:
    """Открытые задачи ``new_property_term`` из очереди ревью (§16.5).

    Отсортированы по (priority desc, created_at asc) — как всё в очереди (§16.4).
    Задачи других видов (low_confidence, contradiction, …) отфильтрованы по ``kind``.
    """
    limit = max(1, min(int(limit), 500))
    q = _queue()
    # берём с запасом и фильтруем по kind (очередь общая для всех правил §16.5)
    tasks = [t.as_dict() for t in q.next_tasks(limit=limit * 4) if t.kind == QUEUE_KIND]
    counts = q.counts_by_status()
    return {
        "kind": QUEUE_KIND,
        "count": len(tasks[:limit]),
        "status_counts": counts,
        "tasks": tasks[:limit],
    }


@router.get("/vocab")
def vocab_summary(_role: str = Depends(current_role)) -> dict[str, Any]:
    """Сводка controlled property-vocabulary (§8.2): размер, sample, активный порог."""
    from kg_er.store.property_vocab import default_vocabulary

    v = default_vocabulary()
    canonical_ids = sorted(v.alias_index().keys())
    return {
        "term_count": len(v),
        "min_sim": DEFAULT_MIN_SIM,
        "reason": REASON_NEW_PROPERTY_TERM,
        "action": ACTION_SCHEMA_CHANGE,
        "target_type": TARGET_TYPE_SCHEMA,
        "sample_canonical_ids": canonical_ids[:40],
    }


__all__ = [
    "router",
    "evaluate_mention",
    "make_dedup_key",
    "compute_priority",
    "REASON_NEW_PROPERTY_TERM",
]
