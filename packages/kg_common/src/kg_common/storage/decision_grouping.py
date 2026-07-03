"""Decision aggregation (§16.7) — авто-предложение группировки CurationEvents.

`decisions.py` хранит решения, а `decision_dag`/`decision_summary` рендерят уже
существующие. Но никто не предлагает, *как* сгруппировать связанные события
курирования (`CurationEvent`) в одно решение (`Decision`) — например, всплеск
слияний (`merge`), разрешающих дубликаты одним автором за короткий промежуток.

Этот модуль — чистая функция без хранилища: на вход последовательность событий
(`Mapping` формы `event_id`/`actor_id`/`action`/`target_id`/`created_at`), на
выходе список предложений `DecisionProposal`. Событие попадает в текущую группу,
если у него тот же `actor_id` И то же `action`, И его `created_at` — в пределах
`window_minutes` от *первого* события группы; иначе открывается новая группа.

RU/EN: предложение / proposal, автор / actor, действие / action, окно / window.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class DecisionProposal:
    """Предложение сгруппировать события в одно решение (§16.7).

    `event_ids` — идентификаторы вошедших событий (в порядке `created_at`);
    `affected_entity_ids` — де-дублицированное объединение `target_id` событий;
    `title` — человекочитаемый заголовок вида `f'{action} x{n}'`.
    """

    event_ids: list[str]
    affected_entity_ids: list[str]
    title: str

    def as_dict(self) -> dict[str, Any]:
        """Плоский dict (для API/preview UI)."""
        return asdict(self)


def _minutes_between(a_iso: str, b_iso: str) -> float:
    """Разница `b - a` в минутах по ISO-8601 меткам (может быть отрицательной)."""
    a = datetime.fromisoformat(a_iso)
    b = datetime.fromisoformat(b_iso)
    return (b - a).total_seconds() / 60.0


def propose_groups(
    events: Sequence[Mapping[str, Any]],
    window_minutes: int = 30,
) -> list[DecisionProposal]:
    """Предложить группировку событий курирования в решения (§16.7).

    События сортируются по `created_at`. Событие добавляется в текущую группу,
    если совпадают `actor_id` И `action`, И его `created_at` укладывается в
    `window_minutes` от первого события группы; иначе начинается новая группа.
    `title == f'{action} x{n}'`, где `n` — число событий; `affected_entity_ids`
    де-дублицирует `target_id` (сохраняя порядок первого появления).
    """
    if not events:
        return []

    ordered = sorted(events, key=lambda e: e["created_at"])

    proposals: list[DecisionProposal] = []
    current: list[Mapping[str, Any]] = []

    def _flush() -> None:
        if not current:
            return
        action = str(current[0]["action"])
        event_ids = [str(e["event_id"]) for e in current]
        seen: dict[str, None] = {}
        for e in current:
            seen.setdefault(str(e["target_id"]), None)
        proposals.append(
            DecisionProposal(
                event_ids=event_ids,
                affected_entity_ids=list(seen),
                title=f"{action} x{len(event_ids)}",
            )
        )

    for event in ordered:
        if not current:
            current = [event]
            continue
        first = current[0]
        same_actor = event["actor_id"] == first["actor_id"]
        same_action = event["action"] == first["action"]
        within = (
            _minutes_between(str(first["created_at"]), str(event["created_at"])) <= window_minutes
        )
        if same_actor and same_action and within:
            current.append(event)
        else:
            _flush()
            current = [event]

    _flush()
    return proposals
