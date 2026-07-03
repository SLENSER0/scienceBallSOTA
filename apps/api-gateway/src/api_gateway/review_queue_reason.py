"""Классификация причин и приоритизация очереди ревью (§12.1 / §14.14).

Модуль на чистом stdlib для эндпоинта ``GET /curation/review-queue``. Определяет
почему задача попала в очередь ревью §12.1 (:func:`classify_reason`), сопоставляет
причине числовой приоритет (:func:`priority_of`) и устойчиво упорядочивает очередь
по убыванию приоритета, затем по возрастанию ``created_at`` (:func:`sort_queue`).

Pure-stdlib helpers for the ``GET /curation/review-queue`` endpoint. Classifies
*why* a task landed in the §12.1 review queue (:func:`classify_reason`), maps a
reason to a numeric priority (:func:`priority_of`) and stably orders the queue by
priority descending, then ``created_at`` ascending (:func:`sort_queue`).

* :data:`REVIEW_REASONS` — шесть допустимых кодов причин / six allowed reason codes.
* :class:`ReviewReason` — frozen ``(code, priority)`` c :meth:`as_dict`.
* :func:`classify_reason` — задача → код причины / task → reason code.
* :func:`priority_of` — код причины → приоритет / reason code → priority.
* :func:`sort_queue` — задачи → устойчиво отсортированный список / stably sorted list.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

#: Шесть допустимых кодов причин ревью §12.1 / the six §12.1 review reason codes.
REVIEW_REASONS: frozenset[str] = frozenset(
    {
        "low_confidence",
        "ambiguous_resolution",
        "contradicts_existing",
        "missing_critical_field",
        "low_quality_ocr",
        "new_schema_term",
    }
)

#: Приоритет каждой причины (больше = важнее) / per-reason priority (higher = sooner).
_PRIORITY: dict[str, int] = {
    "contradicts_existing": 60,
    "missing_critical_field": 50,
    "ambiguous_resolution": 40,
    "low_quality_ocr": 30,
    "new_schema_term": 20,
    "low_confidence": 10,
}


@dataclass(frozen=True, slots=True)
class ReviewReason:
    """Неизменяемая пара ``(code, priority)`` / immutable ``(code, priority)`` pair."""

    code: str
    priority: int

    def as_dict(self) -> dict[str, Any]:
        """Сериализация в словарь / serialise to a plain dict."""
        return {"code": self.code, "priority": self.priority}


def classify_reason(task: Mapping[str, Any], *, confidence_threshold: float = 0.6) -> str:
    """Определить код причины ревью для ``task`` / classify a task's review reason.

    Порядок проверки флагов (первый истинный побеждает) / flag precedence
    (first truthy wins): ``contradicts`` → ``missing_field`` → ``ambiguous`` →
    ``low_quality_ocr`` → ``new_schema_term`` → ``confidence < threshold``.

    Возвращает ``""`` если ни одно условие не выполнено / returns ``""`` when no
    condition matches (task should not be queued).
    """
    if task.get("contradicts"):
        return "contradicts_existing"
    if task.get("missing_field"):
        return "missing_critical_field"
    if task.get("ambiguous"):
        return "ambiguous_resolution"
    if task.get("low_quality_ocr"):
        return "low_quality_ocr"
    if task.get("new_schema_term"):
        return "new_schema_term"
    confidence = task.get("confidence")
    if confidence is not None and float(confidence) < confidence_threshold:
        return "low_confidence"
    return ""


def priority_of(reason: str) -> int:
    """Приоритет причины / priority of a reason code.

    :raises ValueError: если ``reason`` не входит в :data:`REVIEW_REASONS` /
        if ``reason`` is not a known §12.1 code.
    """
    if reason not in REVIEW_REASONS:
        raise ValueError(f"unknown review reason: {reason!r}")
    return _PRIORITY[reason]


def sort_queue(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Устойчиво отсортировать очередь / stably order the review queue.

    Ключ сортировки: приоритет по убыванию, затем ``created_at`` по возрастанию.
    Sort key: priority descending, then ``created_at`` ascending. Исходный список
    не мутируется / the input list is not mutated.
    """

    def _key(task: dict[str, Any]) -> tuple[int, str]:
        priority = priority_of(str(task["reason"]))
        created_at = str(task.get("created_at", ""))
        return (-priority, created_at)

    return sorted(tasks, key=_key)
