"""Curation-decision summary (§16.13): свод по строкам решений без правки стора.

Pure functions over *decision rows* — no store, no I/O, no ``datetime.now`` inside
the logic (детерминированность: тот же вход даёт тот же свод). Модуль строит ON
:mod:`kg_common.storage.decisions`: он ничего не пишет в :class:`DecisionStore`, а
лишь агрегирует уже прочитанные решения. Каждая строка — плоский dict формы
:meth:`kg_common.storage.decisions.Decision.as_dict` (нужны лишь четыре поля)::

    {"target_id": "e1",       # сущность, которой касается решение
     "action": "approve",     # что сделано (для by_action)
     "actor": "alice",        # кто автор (для by_actor)
     "version": 2}            # версия per-target (растёт 1, 2, 3, …)

Свод отвечает на «сколько решений какого действия/автора» и «какая последняя
версия у каждой цели», не трогая источник. RU/EN: решение / decision, действие /
action, автор / actor, свод / summary.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from typing import Any


def _as_int(value: Any) -> int:
    """Привести версию к int (``None`` / пусто → ``0``) — устойчиво к неполным строкам."""
    if value is None or value == "":
        return 0
    return int(value)


@dataclass(frozen=True)
class DecisionSummary:
    """Свод по решениям курирования — snapshot over decision rows (§16.13).

    Fields
    ------
    total:
        Все увиденные строки решений (общее число, весь вход).
    by_action:
        ``{action: count}`` гистограмма по действиям, отсортирована по ключу для
        детерминированного вывода.
    by_actor:
        ``{actor: count}`` гистограмма по авторам, отсортирована по ключу.
    latest_per_target:
        ``{target_id: max_version}`` — для каждой цели её наибольшая версия
        (последнее по времени решение хранит max ``version``), отсортировано по
        ``target_id``.
    """

    total: int
    by_action: dict[str, int] = field(default_factory=dict)
    by_actor: dict[str, int] = field(default_factory=dict)
    latest_per_target: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        """Full structured view (all fields, JSON-friendly, dicts copied)."""
        return asdict(self)


def summarize_decisions(decisions: Sequence[Mapping[str, Any]]) -> DecisionSummary:
    """Aggregate ``decisions`` rows into a :class:`DecisionSummary` (§16.13).

    ``by_action`` / ``by_actor`` — гистограммы по всем строкам; ``latest_per_target``
    хранит для каждого ``target_id`` наибольшую ``version`` (не мутирует стор, лишь
    читает переданные строки). Пустой вход → все счётчики нули / пустые словари.
    Порядок ключей в словарях детерминирован (сортировка по ключу). См. форму строки
    в docstring модуля.
    """
    by_action: dict[str, int] = {}
    by_actor: dict[str, int] = {}
    latest: dict[str, int] = {}
    for row in decisions:
        action = str(row.get("action", ""))
        actor = str(row.get("actor", ""))
        target_id = str(row.get("target_id", ""))
        version = _as_int(row.get("version"))
        by_action[action] = by_action.get(action, 0) + 1
        by_actor[actor] = by_actor.get(actor, 0) + 1
        if target_id not in latest or version > latest[target_id]:
            latest[target_id] = version
    return DecisionSummary(
        total=len(decisions),
        by_action=dict(sorted(by_action.items())),
        by_actor=dict(sorted(by_actor.items())),
        latest_per_target=dict(sorted(latest.items())),
    )
