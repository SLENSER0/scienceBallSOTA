"""Full decision traceability (§16.7): value → CurationEvent → Decision → actor → evidence.

Pure functions over *rows* — no store, no I/O, no ``datetime.now`` inside the logic
(детерминированность: тот же вход даёт ту же трассу). Модуль ничего не пишет; он лишь
сшивает уже прочитанные строки в цепочку прослеживаемости для одной сущности.

Каждый CurationEvent — плоский dict формы::

    {"event_id": "ev1",          # идентификатор события
     "target_id": "e1",          # сущность, которой касается событие
     "actor": "alice",           # кто автор события
     "evidence_ids": ["s1"],     # доказательства (payload события)
     "created_at": "2026-..."}   # метка времени (для сортировки asc)

Каждый Decision — плоский dict формы::

    {"decision_id": "d1",                 # идентификатор решения
     "curation_event_ids": ["ev1", ...]}  # события, INCLUDES которых он охватывает

Трасса отвечает на «через какое решение и с чьей руки прошло каждое событие и на
каких доказательствах», не трогая источник. RU/EN: событие / event, решение /
decision, автор / actor, доказательство / evidence, трасса / trace.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class TraceLink:
    """Одно звено трассы: событие сущности и решение, что его INCLUDES (§16.7).

    Fields
    ------
    entity_id:
        Сущность (значение), к которой относится событие — ``CurationEvent.target_id``.
    event_id:
        Идентификатор CurationEvent.
    decision_id:
        Решение, охватывающее событие (``Decision.curation_event_ids`` contains
        ``event_id``); ``""`` если событие-сирота (не входит ни в одно решение).
    actor:
        Автор события (кто внёс правку), переносится из события.
    evidence_ids:
        Доказательства события (payload ``evidence_ids``), сохраняются как есть.
    """

    entity_id: str
    event_id: str
    decision_id: str
    actor: str
    evidence_ids: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        """Full structured view (all fields, JSON-friendly, list copied)."""
        return asdict(self)


def _event_ids_of(decision: Mapping[str, Any]) -> list[str]:
    """Список event id, которые решение INCLUDES (устойчиво к отсутствию поля)."""
    raw = decision.get("curation_event_ids") or []
    return [str(eid) for eid in raw]


def build_trace(
    entity_id: str,
    events: Sequence[Mapping[str, Any]],
    decisions: Sequence[Mapping[str, Any]],
) -> list[TraceLink]:
    """Сшить события сущности с их решениями в упорядоченную трассу (§16.7).

    Отбираются CurationEvents с ``target_id == entity_id``; для каждого ищется
    Decision, чей ``curation_event_ids`` содержит ``event_id`` (связь INCLUDES). Автор
    и ``evidence_ids`` переносятся из события; событие-сирота получает
    ``decision_id == ""``. Звенья сортируются по ``created_at`` по возрастанию
    (раннее — первым). Не мутирует стор, лишь читает переданные строки. Пустой вход →
    ``[]``. См. форму строк в docstring модуля.
    """
    event_to_decision: dict[str, str] = {}
    for decision in decisions:
        decision_id = str(decision.get("decision_id", ""))
        for event_id in _event_ids_of(decision):
            event_to_decision.setdefault(event_id, decision_id)

    selected = [ev for ev in events if str(ev.get("target_id", "")) == entity_id]
    selected.sort(key=lambda ev: str(ev.get("created_at", "")))

    links: list[TraceLink] = []
    for event in selected:
        event_id = str(event.get("event_id", ""))
        evidence = [str(ev) for ev in (event.get("evidence_ids") or [])]
        links.append(
            TraceLink(
                entity_id=entity_id,
                event_id=event_id,
                decision_id=event_to_decision.get(event_id, ""),
                actor=str(event.get("actor", "")),
                evidence_ids=evidence,
            )
        )
    return links


def latest_actor(links: Sequence[TraceLink]) -> str | None:
    """Автор последнего (новейшего) звена трассы или ``None`` для пустой трассы (§16.7)."""
    if not links:
        return None
    return links[-1].actor
