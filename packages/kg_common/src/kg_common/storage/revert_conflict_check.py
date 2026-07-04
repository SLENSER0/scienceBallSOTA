"""Revert conflict / safety pre-check (§16.7).

:mod:`kg_common.storage.decision_revert` строит компенсирующие события, но
**никогда** не проверяет, редактировались ли цели решения **более новыми**
событиями. Поэтому откат может молча затереть позднейшую курацию (later
curation) поверх исходного решения. Этот модуль — чистая (pure) проверка
безопасности: он не мутирует стор, а лишь смотрит, есть ли на затронутых
сущностях события *новее* самого решения.

Решение (``decision``) описывается своими ``curation_event_ids`` (id
собственных событий) и ``affected_entity_ids`` (затронутые сущности).
Событие (``event`` в ``all_events``) считается **блокирующим** (blocking),
если одновременно: (1) его ``target_id`` — одна из затронутых сущностей,
(2) оно **не** входит в собственные события решения и (3) его ``created_at``
строго позже максимального ``created_at`` среди событий решения.

RU/EN: откат / revert, блокирующее событие / blocking event, безопасно / safe.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class RevertSafety:
    """Результат проверки безопасности отката (§16.7).

    ``safe`` — истина тогда и только тогда, когда нет блокирующих событий.
    ``blocking_events`` — id событий, помешавших откату (более новые правки
    затронутых сущностей). ``reason`` — человекочитаемое объяснение (RU/EN).
    """

    safe: bool
    blocking_events: list[str]
    reason: str

    def as_dict(self) -> dict[str, object]:
        """Плоский dict (для API/audit-лога); ``blocking_events`` — list."""
        return asdict(self)


def _event_id(event: Mapping) -> str:
    """Id события: ``event_id`` либо ``id`` (пустая строка, если нет)."""
    val = event.get("event_id", event.get("id", ""))
    return str(val) if val is not None else ""


def _decision_event_ids(decision: Mapping) -> set[str]:
    """Множество id собственных событий решения (``curation_event_ids``)."""
    return {str(e) for e in decision.get("curation_event_ids", [])}


def _decision_max_time(decision: Mapping, all_events: Sequence[Mapping]) -> str:
    """Максимальный ``created_at`` среди собственных событий решения.

    Ищет в ``all_events`` события, чей id входит в ``curation_event_ids``, и
    возвращает наибольший ``created_at`` (лексикографически — ISO-8601 время
    сортируется как строка). Если своих событий нет — пустая строка.
    """
    own = _decision_event_ids(decision)
    times = [str(e.get("created_at", "")) for e in all_events if _event_id(e) in own]
    return max(times) if times else ""


def check_revert(decision: Mapping, all_events: Sequence[Mapping]) -> RevertSafety:
    """Проверить, безопасен ли откат ``decision`` (стор не мутируется).

    Помечает каждое событие в ``all_events``, чей ``target_id`` — затронутая
    решением сущность, которое **не** входит в собственные события решения и
    чей ``created_at`` строго позже максимального времени решения. ``safe``
    истинно тогда и только тогда, когда таких блокирующих событий нет.
    """
    affected = {str(a) for a in decision.get("affected_entity_ids", [])}
    own = _decision_event_ids(decision)
    max_time = _decision_max_time(decision, all_events)

    blocking: list[str] = []
    for event in all_events:
        eid = _event_id(event)
        if eid in own:  # собственное событие решения — не блокирует
            continue
        if str(event.get("target_id", "")) not in affected:
            continue
        if str(event.get("created_at", "")) > max_time:  # строго новее
            blocking.append(eid)

    if not blocking:
        reason = "safe: no newer events on affected targets / нет новых правок"
        return RevertSafety(safe=True, blocking_events=[], reason=reason)
    reason = (
        f"unsafe: {len(blocking)} newer event(s) on affected targets / "
        f"{len(blocking)} более новых событий на затронутых целях"
    )
    return RevertSafety(safe=False, blocking_events=blocking, reason=reason)
