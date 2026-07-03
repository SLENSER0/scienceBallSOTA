"""Детекция правила ``new_schema_term`` — сканирование неизвестных терминов (§16.5).

Экстрактор наблюдает термины (``observed``) с их видом (``kind``) и контекстом.
Термин, чей нормализованный вид отсутствует в нормализованном словаре
(*vocabulary*), считается *новым термином схемы* и порождает находку
:class:`UnknownTermFinding`. Каждая находка нацелена на схему
(``target_type='schema'``) и, при наличии близкого известного термина, несёт
подсказку сопоставления (``suggested_mapping``).

Чистые (*pure*) функции без побочных эффектов: модуль ничего не читает из графа
Kuzu — работает только с переданными наблюдениями и словарём (§16.5).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class UnknownTermFinding:
    """Замороженная (*frozen*) находка неизвестного термина схемы (§16.5).

    ``term`` — исходный (ненормализованный) термин; ``kind`` — вид термина
    (например, ``property`` / ``method``); ``context`` — первый контекст, в котором
    термин встречен; ``suggested_mapping`` — близкий известный термин словаря или
    ``None``. Находка всегда нацелена на схему (``target_type='schema'``).
    """

    term: str
    kind: str
    context: str
    suggested_mapping: str | None

    def as_dict(self) -> dict[str, Any]:
        """JSON-совместимое представление находки (``target_type='schema'``) (§16.5)."""
        return {
            "target_type": "schema",
            "term": self.term,
            "kind": self.kind,
            "context": self.context,
            "suggested_mapping": self.suggested_mapping,
        }


def _normalize(term: str) -> str:
    """Нормализовать термин: lowercase, strip, схлопнуть пробелы (§16.5).

    ``'  Yield  Strength '`` -> ``'yield strength'``. Внутренние пробельные
    последовательности (табы, переводы строк) сжимаются в один пробел.
    """
    return " ".join(term.split()).lower()


def nearest_known(term: str, vocabulary: Sequence[str]) -> str | None:
    """Ближайший известный термин словаря к ``term`` или ``None`` (§16.5).

    Сопоставление регистронезависимое по нормализованному вхождению
    (*containment*) / префиксу: кандидат подходит, если нормализованный термин и
    запись словаря являются префиксом друг друга либо один содержится в другом.
    Возвращается кандидат с наименьшей разницей длин; при отсутствии — ``None``.
    """
    norm_term = _normalize(term)
    if not norm_term:
        return None

    best: str | None = None
    best_delta = -1
    for candidate in vocabulary:
        norm_cand = _normalize(candidate)
        if not norm_cand:
            continue
        matches = (
            norm_cand.startswith(norm_term)
            or norm_term.startswith(norm_cand)
            or norm_term in norm_cand
            or norm_cand in norm_term
        )
        if not matches:
            continue
        delta = abs(len(norm_cand) - len(norm_term))
        if best is None or delta < best_delta:
            best = candidate
            best_delta = delta
    return best


def scan_terms(
    observed: Sequence[Mapping[str, Any]],
    vocabulary: Sequence[str],
) -> list[UnknownTermFinding]:
    """Найти неизвестные термины схемы среди наблюдений ``observed`` (§16.5).

    Для каждого наблюдения ``{term, kind, context}`` с нормализованным термином вне
    нормализованного словаря порождается находка. Дедупликация по ключу
    ``(kind, нормализованный term)`` — сохраняется первый встреченный контекст.
    ``suggested_mapping`` берётся из :func:`nearest_known`.
    """
    known: frozenset[str] = frozenset(_normalize(entry) for entry in vocabulary)

    findings: list[UnknownTermFinding] = []
    seen: set[tuple[str, str]] = set()
    for obs in observed:
        term = str(obs["term"])
        kind = str(obs["kind"])
        context = str(obs["context"])
        norm_term = _normalize(term)
        if norm_term in known:
            continue
        dedup_key = (kind, norm_term)
        if dedup_key in seen:
            continue
        seen.add(dedup_key)
        findings.append(
            UnknownTermFinding(
                term=term,
                kind=kind,
                context=context,
                suggested_mapping=nearest_known(term, vocabulary),
            )
        )
    return findings
