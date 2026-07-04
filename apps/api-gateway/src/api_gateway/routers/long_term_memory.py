"""Кросс-сессионная долговременная память / cross-session long-term memory (§13.20).

Экран персонализации ассистента (roadmap §13.20). Агент помнит между сессиями то,
что пользователь подтвердил: канонические алиасы сущностей, предпочтения и часто
используемые фильтры — и применяет это к новому запросу *до* entity_resolver /
query_planner. В production-профиле §13.20 это хранится в LangGraph ``PostgresStore``
под namespace ``(user_id, "memories")``; здесь тот же namespace-контракт и та же
семантика TTL/усечения реализованы поверх durable JSON-файла в ``runtime_dir``, чтобы
память переживала перезапуск процесса и была общей между двумя разными ``session_id``
одного ``user_id`` (критерий приёмки §13.20).

Ничего не переписываем — переиспользуем уже готовые чистые модули agent-service:

* :mod:`agent_service.user_memory` — ``MemoryRecord``, ``namespace``, ``prune``
  (TTL + усечение по свежести / recency truncation).
* :mod:`agent_service.memory_writeback` — ``collect_writes`` выводит из завершённой
  сессии durable-факты (подтверждённые сущности + частые фильтры).
* :mod:`agent_service.memory_personalization` — ``personalize`` складывает записи
  памяти в переписанный запрос (алиасы + фильтры-по-умолчанию).

Endpoints (prefix ``/api/v1/memory``):

* ``GET  /api/v1/memory/{user_id}`` — прочитать память пользователя (после prune).
* ``POST /api/v1/memory/{user_id}`` — записать один подтверждённый факт.
* ``POST /api/v1/memory/{user_id}/learn`` — вывести факты из состояния сессии и сохранить.
* ``POST /api/v1/memory/{user_id}/personalize`` — применить память к новому запросу.
* ``DELETE /api/v1/memory/{user_id}/{key}`` — забыть один факт.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any, Literal

from agent_service.memory_personalization import personalize
from agent_service.memory_writeback import collect_writes
from agent_service.user_memory import MemoryRecord, namespace, prune
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from kg_common import get_logger, get_settings

router = APIRouter(prefix="/api/v1/memory", tags=["memory"])

_log = get_logger("api.long_term_memory")

# Лимит размера памяти на пользователя (§13.20 «размер-лимиты и очистка памяти»).
# prune() держит только самые свежие MAX_ITEMS записей после отсева истёкших по TTL.
MAX_ITEMS = 200

# Единый файл-стор: { user_id: [record_dict, ...] }. Один процесс -> один lock хватает
# для сериализации конкурентных записей API-воркеров.
_LOCK = threading.RLock()


def _store_path() -> Path:
    """Путь к durable JSON-стору памяти в ``runtime_dir`` (создаёт каталог)."""
    s = get_settings()
    root = Path(s.runtime_dir)
    root.mkdir(parents=True, exist_ok=True)
    return root / "long_term_memory.json"


def _load_all() -> dict[str, list[dict[str, Any]]]:
    """Прочитать весь стор; отсутствующий/битый файл -> пустая карта (graceful)."""
    path = _store_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:  # pragma: no cover - I/O guard
        _log.warning("ltm.load_failed", error=str(exc))
        return {}
    if not isinstance(data, dict):
        return {}
    return data


def _save_all(data: dict[str, list[dict[str, Any]]]) -> None:
    """Атомарно записать весь стор (tmp + replace), чтобы не оставить полу-файл."""
    path = _store_path()
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _to_record(raw: dict[str, Any]) -> MemoryRecord | None:
    """Восстановить :class:`MemoryRecord` из сериализованного dict (пропустить битые)."""
    try:
        return MemoryRecord(
            key=str(raw["key"]),
            kind=str(raw["kind"]),
            value=dict(raw["value"]),
            created_at=float(raw["created_at"]),
            ttl_s=(None if raw.get("ttl_s") is None else float(raw["ttl_s"])),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _read_pruned(user_id: str, now: float) -> list[MemoryRecord]:
    """Прочитать записи пользователя и применить :func:`prune` (TTL + усечение)."""
    all_data = _load_all()
    raw = all_data.get(user_id, [])
    records = [r for r in (_to_record(x) for x in raw) if r is not None]
    return prune(records, now=now, max_items=MAX_ITEMS)


def _write_records(user_id: str, records: list[MemoryRecord], now: float) -> list[MemoryRecord]:
    """Persist records for ``user_id`` под lock, вернуть pruned-состояние."""
    with _LOCK:
        all_data = _load_all()
        pruned = prune(records, now=now, max_items=MAX_ITEMS)
        all_data[user_id] = [r.as_dict() for r in pruned]
        _save_all(all_data)
    return pruned


def _upsert(existing: list[MemoryRecord], new: MemoryRecord) -> list[MemoryRecord]:
    """Заменить запись с тем же ``key`` (иначе добавить) — идемпотентный upsert."""
    kept = [r for r in existing if r.key != new.key]
    kept.append(new)
    return kept


# --------------------------------------------------------------------------- API models


class MemoryRecordOut(BaseModel):
    key: str
    kind: str
    value: dict[str, Any]
    created_at: float
    ttl_s: float | None = None
    expired: bool = False


class MemoryListResponse(BaseModel):
    user_id: str
    namespace: list[str]
    count: int
    max_items: int
    counts_by_kind: dict[str, int]
    records: list[MemoryRecordOut]


class PutMemoryRequest(BaseModel):
    """Один подтверждённый пользователем факт для записи в долговременную память."""

    kind: Literal["alias", "preference", "frequent_filter"]
    # alias: {"mention": str, "canonical": str}
    mention: str | None = None
    canonical: str | None = None
    # preference: {"key": str, "value": Any}
    pref_key: str | None = Field(default=None, alias="key")
    pref_value: Any = None
    # frequent_filter: {"filter": {...}}
    filter: dict[str, Any] | None = None
    ttl_s: float | None = Field(default=None, description="Срок жизни в секундах; None = вечно")

    model_config = {"populate_by_name": True}


class LearnRequest(BaseModel):
    """Состояние завершённой сессии, из которого выводятся durable-факты (§13.20)."""

    confirmed_entities: list[dict[str, Any]] = Field(default_factory=list)
    filter_history: list[dict[str, Any]] = Field(default_factory=list)
    threshold: float = 0.8


class LearnResponse(BaseModel):
    user_id: str
    learned: int
    records: list[MemoryRecordOut]


class PersonalizeRequest(BaseModel):
    """Входной запрос новой сессии, к которому применяется память прошлых сессий."""

    mentions: list[str] = Field(default_factory=list)
    filters: dict[str, Any] = Field(default_factory=dict)


class PersonalizeResponse(BaseModel):
    user_id: str
    mentions: list[str]
    filters: dict[str, Any]
    applied: list[str]
    memory_used: int


# --------------------------------------------------------------------------- helpers


def _record_out(r: MemoryRecord, now: float) -> MemoryRecordOut:
    return MemoryRecordOut(
        key=r.key,
        kind=r.kind,
        value=dict(r.value),
        created_at=r.created_at,
        ttl_s=r.ttl_s,
        expired=r.is_expired(now),
    )


def _memory_dicts_for_personalize(records: list[MemoryRecord]) -> list[dict[str, Any]]:
    """Спроецировать хранимые записи в формат, который понимает ``personalize``.

    ``personalize`` смотрит только на ``entity_alias`` (mention→canonical) и
    ``preferred_filter`` (key→value). Наши ``alias`` разворачиваются в первое, а каждый
    ключ ``frequent_filter`` — в отдельный ``preferred_filter`` (фильтр-по-умолчанию).
    """
    out: list[dict[str, Any]] = []
    for r in records:
        if r.kind == "alias":
            mention = r.value.get("mention")
            canonical = r.value.get("canonical")
            if mention is not None and canonical is not None:
                out.append({"kind": "entity_alias", "mention": mention, "canonical": canonical})
        elif r.kind == "frequent_filter":
            filt = r.value.get("filter", {})
            if isinstance(filt, dict):
                for key, value in filt.items():
                    out.append({"kind": "preferred_filter", "key": key, "value": value})
    return out


def _filter_key(filt: dict[str, Any]) -> str:
    """Стабильный ключ фильтра (порядко-независимый), совпадает с memory_writeback."""
    return ";".join(f"{k}={filt[k]!r}" for k in sorted(filt))


# --------------------------------------------------------------------------- endpoints


@router.get("/{user_id}", response_model=MemoryListResponse)
def read_memory(user_id: str) -> MemoryListResponse:
    """Прочитать долговременную память пользователя (после TTL-prune и усечения)."""
    now = time.time()
    records = _read_pruned(user_id, now)
    counts: dict[str, int] = {}
    for r in records:
        counts[r.kind] = counts.get(r.kind, 0) + 1
    ns = namespace(user_id)
    return MemoryListResponse(
        user_id=user_id,
        namespace=list(ns),
        count=len(records),
        max_items=MAX_ITEMS,
        counts_by_kind=counts,
        records=[_record_out(r, now) for r in records],
    )


@router.post("/{user_id}", response_model=MemoryRecordOut)
def put_memory(user_id: str, body: PutMemoryRequest) -> MemoryRecordOut:
    """Записать один подтверждённый факт (upsert по ключу) в память пользователя."""
    now = time.time()
    if body.kind == "alias":
        if not body.mention or not body.canonical:
            raise HTTPException(422, "alias требует непустые mention и canonical")
        key = f"alias:{body.mention}"
        value: dict[str, Any] = {"mention": body.mention, "canonical": body.canonical}
    elif body.kind == "preference":
        if not body.pref_key:
            raise HTTPException(422, "preference требует непустой key")
        key = f"pref:{body.pref_key}"
        value = {"key": body.pref_key, "value": body.pref_value}
    else:  # frequent_filter
        if not body.filter:
            raise HTTPException(422, "frequent_filter требует непустой filter")
        key = f"filter:{_filter_key(body.filter)}"
        value = {"filter": body.filter}

    record = MemoryRecord(key=key, kind=body.kind, value=value, created_at=now, ttl_s=body.ttl_s)
    existing = _read_pruned(user_id, now)
    pruned = _write_records(user_id, _upsert(existing, record), now)
    stored = next((r for r in pruned if r.key == key), record)
    _log.info("ltm.put", user_id=user_id, kind=body.kind, key=key)
    return _record_out(stored, now)


@router.post("/{user_id}/learn", response_model=LearnResponse)
def learn_memory(user_id: str, body: LearnRequest) -> LearnResponse:
    """Вывести durable-факты из завершённой сессии и записать их (§13.20 writeback).

    Переиспользует ``collect_writes``: подтверждённые сущности (>= threshold) дают
    alias-записи, часто применённые фильтры — frequent_filter-записи.
    """
    now = time.time()
    state = {
        "confirmed_entities": body.confirmed_entities,
        "filter_history": body.filter_history,
    }
    writes = collect_writes(state, threshold=body.threshold)

    records = _read_pruned(user_id, now)
    learned: list[MemoryRecord] = []
    for w in writes:
        if w.kind == "entity_alias":
            mention = w.key.removeprefix("alias:")
            rec = MemoryRecord(
                key=w.key,
                kind="alias",
                value={"mention": mention, "canonical": w.value},
                created_at=now,
            )
        else:  # preferred_filter
            rec = MemoryRecord(
                key=w.key,
                kind="frequent_filter",
                value={"filter": w.value},
                created_at=now,
            )
        records = _upsert(records, rec)
        learned.append(rec)

    _write_records(user_id, records, now)
    _log.info("ltm.learn", user_id=user_id, learned=len(learned))
    return LearnResponse(
        user_id=user_id,
        learned=len(learned),
        records=[_record_out(r, now) for r in learned],
    )


@router.post("/{user_id}/personalize", response_model=PersonalizeResponse)
def personalize_query(user_id: str, body: PersonalizeRequest) -> PersonalizeResponse:
    """Применить память прошлых сессий к новому запросу (алиасы + фильтры по умолчанию).

    Это точка, где долговременная память «подхватывается в entity_resolver следующей
    сессии» (§13.20): mentions переписываются на канонические id, а часто используемые
    фильтры инжектятся как значения по умолчанию, не перекрывая явно заданные.
    """
    now = time.time()
    records = _read_pruned(user_id, now)
    mem_dicts = _memory_dicts_for_personalize(records)
    pq = personalize(body.mentions, body.filters, mem_dicts)
    return PersonalizeResponse(
        user_id=user_id,
        mentions=list(pq.mentions),
        filters=dict(pq.filters),
        applied=list(pq.applied),
        memory_used=len(mem_dicts),
    )


@router.delete("/{user_id}/{key:path}")
def forget_memory(user_id: str, key: str) -> dict[str, Any]:
    """Забыть один факт по ключу (напр. отозвать ошибочно подтверждённый алиас)."""
    now = time.time()
    records = _read_pruned(user_id, now)
    remaining = [r for r in records if r.key != key]
    removed = len(records) - len(remaining)
    if removed == 0:
        raise HTTPException(404, f"ключ {key!r} не найден в памяти {user_id!r}")
    _write_records(user_id, remaining, now)
    _log.info("ltm.forget", user_id=user_id, key=key)
    return {"user_id": user_id, "key": key, "removed": removed, "remaining": len(remaining)}
