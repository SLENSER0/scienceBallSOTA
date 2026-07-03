"""Home 'recent questions' block model (§17.6).

Frontend-agnostic модель блока «недавние вопросы» для главной страницы: свести
дубликаты по нормализованному тексту (casefold+strip), отсортировать по
убыванию ``asked_at`` (ISO-строки), обрезать до ``limit`` и построить превью.
Ни один модуль этого не строит — здесь только чистая доменная логика.

A frontend-agnostic 'recent questions' block for Home: dedupe questions by a
normalised text key (casefold + strip) keeping the most recent occurrence, sort
newest-first by ISO ``asked_at`` string, truncate to ``limit`` and build a
short preview. Pure stdlib; ISO-8601 strings compare lexically.

* :class:`RecentQuestion` — frozen record with camelCase :meth:`as_dict`.
* :class:`RecentQuestionList` — frozen container (``items``, ``total``).
* :func:`build_recent_questions` — dedupe/sort/truncate raw rows into a list.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class RecentQuestion:
    """Неизменяемая запись недавнего вопроса (§17.6).

    Immutable recent-question record. ``session_id`` is the session to restore
    when the question is re-opened; ``preview`` is a truncated ``text``.
    """

    session_id: str
    text: str
    asked_at: str
    preview: str

    def as_dict(self) -> dict[str, Any]:
        """Сериализовать в camelCase dict ('sessionId', 'askedAt').

        Serialise to a JSON-ready ``dict`` with camelCase keys.
        """
        return {
            "sessionId": self.session_id,
            "text": self.text,
            "askedAt": self.asked_at,
            "preview": self.preview,
        }


@dataclass(frozen=True, slots=True)
class RecentQuestionList:
    """Неизменяемый список недавних вопросов с полным числом уникальных (§17.6).

    Immutable container. ``items`` is the (possibly truncated) list and
    ``total`` is the count of distinct questions before the ``limit`` cut.
    """

    items: tuple[RecentQuestion, ...]
    total: int

    def as_dict(self) -> dict[str, Any]:
        """Сериализовать в dict с камель-ключами ('items', 'total').

        Serialise to a JSON-ready ``dict`` with ``items`` and ``total``.
        """
        return {
            "items": [item.as_dict() for item in self.items],
            "total": self.total,
        }


def _preview(text: str, preview_len: int) -> str:
    """Обрезать ``text`` до ``preview_len`` символов, добавив '...' если длиннее.

    Truncate ``text`` to ``preview_len`` chars; append a literal ``'...'`` when
    the original text was longer, otherwise return it unchanged.
    """
    if len(text) <= preview_len:
        return text
    return text[:preview_len] + "..."


def build_recent_questions(
    raw: list[dict],
    *,
    limit: int = 10,
    preview_len: int = 80,
) -> RecentQuestionList:
    """Свести дубли, отсортировать и обрезать недавние вопросы (§17.6).

    Dedupe ``raw`` rows by a normalised text key (``text`` casefolded and
    stripped), keeping the occurrence with the greatest ``asked_at``. Sort the
    distinct questions newest-first by ``asked_at`` (ISO string compare),
    truncate to ``limit`` items, and compute a ``preview`` per item.

    ``total`` reflects the number of distinct questions *before* the ``limit``
    truncation, so the caller can show "showing N of total".
    """
    best: dict[str, dict] = {}
    for row in raw:
        text = str(row["text"])
        key = text.casefold().strip()
        asked_at = str(row["asked_at"])
        current = best.get(key)
        if current is None or asked_at > str(current["asked_at"]):
            best[key] = row

    total = len(best)

    ordered = sorted(best.values(), key=lambda r: str(r["asked_at"]), reverse=True)

    items: list[RecentQuestion] = []
    for row in ordered[:limit]:
        text = str(row["text"])
        items.append(
            RecentQuestion(
                session_id=str(row["session_id"]),
                text=text,
                asked_at=str(row["asked_at"]),
                preview=_preview(text, preview_len),
            )
        )

    return RecentQuestionList(items=tuple(items), total=total)
