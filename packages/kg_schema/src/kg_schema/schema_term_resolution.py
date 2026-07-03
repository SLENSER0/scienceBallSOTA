"""Резолюция нового термина схемы — accept / map / reject (§16.6/§16.5).

Когда экстрактор предлагает *новый* термин словаря (``new_schema_term``), куратор
принимает решение (*resolution*): ``accept`` — добавить термин в словарь (версия
словаря растёт на 1), ``map`` — сопоставить существующему термину (термин НЕ
добавляется, версия не меняется), ``reject`` — отклонить (термин не добавляется).

Чистые (*pure*) функции без побочных эффектов: :func:`resolve_term` строит
замороженное решение :class:`TermResolution`, а :func:`apply_vocabulary` отдаёт
новый отсортированный словарь (добавляя термин только при ``accept``). Модуль ничего
не читает из графа Kuzu — работает только с переданным словарём (§16.6/§16.5).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal

Action = Literal["accept", "map", "reject"]

_ACTIONS: frozenset[str] = frozenset({"accept", "map", "reject"})


@dataclass(frozen=True, slots=True)
class TermResolution:
    """Замороженное (*frozen*) решение куратора по новому термину (§16.6/§16.5).

    ``action`` — исходное действие (``accept`` / ``map`` / ``reject``);
    ``mapped_to`` — целевой термин для ``map`` (иначе ``None``);
    ``vocabulary_version`` — версия словаря ПОСЛЕ решения (растёт лишь при ``accept``);
    ``accepted`` — True только для ``accept`` (термин добавлен в словарь).
    """

    term: str
    action: Action
    mapped_to: str | None
    vocabulary_version: int
    accepted: bool

    def as_dict(self) -> dict[str, Any]:
        """JSON-совместимое представление решения (echoes ``action``) (§16.6/§16.5)."""
        return {
            "term": self.term,
            "action": self.action,
            "mapped_to": self.mapped_to,
            "vocabulary_version": self.vocabulary_version,
            "accepted": self.accepted,
        }


def resolve_term(
    term: str,
    action: str,
    vocabulary: Sequence[str],
    mapped_to: str | None = None,
    current_version: int = 1,
) -> TermResolution:
    """Построить решение по новому термину ``term`` (§16.6/§16.5).

    ``accept`` — термин добавляется, ``accepted=True``, версия ``current_version + 1``.
    ``map`` — требует ``mapped_to`` в ``vocabulary`` (иначе :class:`ValueError`);
    ``accepted=False``, версия не меняется. ``reject`` — ``accepted=False``, версия
    не меняется. Неизвестное ``action`` -> :class:`ValueError`.
    """
    if action not in _ACTIONS:
        raise ValueError(f"unknown action: {action!r} (expected accept/map/reject)")

    if action == "accept":
        return TermResolution(
            term=term,
            action="accept",
            mapped_to=None,
            vocabulary_version=current_version + 1,
            accepted=True,
        )

    if action == "map":
        if mapped_to is None or mapped_to not in vocabulary:
            raise ValueError(f"map target {mapped_to!r} not present in vocabulary")
        return TermResolution(
            term=term,
            action="map",
            mapped_to=mapped_to,
            vocabulary_version=current_version,
            accepted=False,
        )

    # action == "reject"
    return TermResolution(
        term=term,
        action="reject",
        mapped_to=None,
        vocabulary_version=current_version,
        accepted=False,
    )


def apply_vocabulary(vocabulary: Sequence[str], resolution: TermResolution) -> list[str]:
    """Применить решение к словарю — новый отсортированный список (§16.6/§16.5).

    Термин добавляется только при ``accepted`` (``accept``); дубликаты схлопываются.
    """
    terms = set(vocabulary)
    if resolution.accepted:
        terms.add(resolution.term)
    return sorted(terms)
