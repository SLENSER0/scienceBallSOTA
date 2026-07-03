"""Revert of a multi-event decision via compensating events (§16.7).

Строит ON :mod:`kg_common.storage.decisions`: модуль не редактирует стор, а
переиспользует :class:`DecisionStore` / ``record_decision`` / ``history_for``.

Откат многособытийного решения не удаляет исходные записи — audit-trail
сохраняется («no destructive revert»). Для решения, агрегирующего N прямых
событий цели, план строит N *компенсирующих* событий, инвертирующих каждое
(``before_hash`` ↔ ``after_hash``) в обратном порядке, и восстанавливает
состояние сущности до решения (``restored_status`` = ``before_hash`` первого
события). Применение фиксирует одно новое компенсирующее решение с версией
``max+1`` по цели; статус ``"reverted"`` пишется в поле ``action`` (в схеме
``decisions`` нет отдельной колонки status, а редактировать её нельзя).

Операция идемпотентна по детерминированному id ``revert:<decision_id>``:
``record_decision`` идемпотентен по ``decision_id``, поэтому повторный откат не
плодит записей и не увеличивает версию.

RU/EN: решение / decision, откат / revert, компенсация / compensating event.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from sqlalchemy import select

from kg_common.errors import NotFoundError
from kg_common.storage.decisions import Decision, DecisionStore, decisions

# Компенсирующие решения помечены этим префиксом id: исключаются из «прямой»
# истории и дают идемпотентность (record_decision идемпотентен по decision_id).
REVERT_ID_PREFIX = "revert:"
# Статус компенсирующего решения, записываемый в поле ``action``.
REVERTED_STATUS = "reverted"


@dataclass(frozen=True)
class RevertPlan:
    """План отката многособытийного решения (§16.7).

    ``compensating`` — N словарей в обратном порядке событий; каждый инвертирует
    одно прямое событие (``before_hash`` ↔ ``after_hash``). ``restored_status`` —
    состояние цели до решения (``before_hash`` первого прямого события).
    """

    decision_id: str
    target_id: str
    compensating: list[dict[str, Any]]
    restored_status: str

    def as_dict(self) -> dict[str, Any]:
        """Плоский dict (для API/audit-лога)."""
        return asdict(self)


def _find_decision(store: DecisionStore, decision_id: str) -> Decision | None:
    """Найти решение по id (read-only через общий engine стора)."""
    q = select(decisions).where(decisions.c.decision_id == decision_id)
    with store.engine.begin() as conn:
        row = conn.execute(q).first()
    return Decision(**row._mapping) if row else None


def _forward_events(store: DecisionStore, target_id: str) -> list[Decision]:
    """Прямые (не компенсирующие) события цели в порядке возрастания версии."""
    return [
        d for d in store.history_for(target_id) if not d.decision_id.startswith(REVERT_ID_PREFIX)
    ]


def plan_revert(store: DecisionStore, decision_id: str) -> RevertPlan:
    """Построить план отката решения ``decision_id`` (стор не мутируется).

    Решение агрегирует N прямых событий своей цели; план содержит N
    компенсирующих событий в обратном порядке и состояние до решения.
    Неизвестное решение → :class:`~kg_common.errors.NotFoundError`.
    """
    ref = _find_decision(store, decision_id)
    if ref is None:
        raise NotFoundError(f"decision not found: {decision_id}")
    events = _forward_events(store, ref.target_id)
    if not events:  # цель без прямых событий — нечего откатывать
        raise NotFoundError(f"decision has no forward events: {decision_id}")
    compensating = [
        {
            "reverts_decision_id": e.decision_id,
            "event_id": e.event_id,
            "target_id": e.target_id,
            "action": "revert",
            "before_hash": e.after_hash,  # инверсия before ↔ after
            "after_hash": e.before_hash,
        }
        for e in reversed(events)
    ]
    return RevertPlan(
        decision_id=decision_id,
        target_id=ref.target_id,
        compensating=compensating,
        restored_status=events[0].before_hash,  # состояние до первого события
    )


def apply_revert(store: DecisionStore, decision_id: str, *, actor: str, now: str) -> Decision:
    """Зафиксировать компенсирующее решение (``action="reverted"``) и вернуть его.

    Пишет одну новую запись версии ``max+1`` по цели: ``before_hash`` — текущее
    состояние, ``after_hash`` — ``restored_status`` (состояние до решения).
    Исходные события не удаляются (audit-trail). Идемпотентно по
    детерминированному id ``revert:<decision_id>``: повторный вызов возвращает уже
    записанное решение, не увеличивая версию. ``now`` передаётся явно.
    """
    plan = plan_revert(store, decision_id)
    current_state = plan.compensating[0]["before_hash"]  # after_hash последнего события
    compensation = Decision(
        decision_id=f"{REVERT_ID_PREFIX}{decision_id}",
        target_id=plan.target_id,
        event_id=f"{REVERT_ID_PREFIX}{decision_id}",
        action=REVERTED_STATUS,
        actor=actor,
        before_hash=current_state,
        after_hash=plan.restored_status,
        created_at=now,
    )
    return store.record_decision(compensation)
