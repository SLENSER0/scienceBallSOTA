"""Просмотрщик истории решений с пофайловым диффом before/after (§5.2.8, §12.3).

Чистый билдер проекции: берёт список событий кураторства :class:`CurationEvent`
из §12.3 (``{action, actor, target_type, target_id, before, after, reason,
created_at}``) и строит представление «История решений» из §5.2.8. Для каждого
события вычисляется пофайловый дифф ``diff`` (``added`` / ``removed`` /
``changed``) из снимков ``before``/``after`` и ссылка ``target_ref``. Записи
сортируются по ``created_at`` по убыванию (новейшие первыми), связи стабильны.
Без побочных эффектов, детерминированно, только stdlib.

Pure projection builder: takes a list of §12.3 :class:`CurationEvent` dicts
(``{action, actor, target_type, target_id, before, after, reason, created_at}``)
and builds the §5.2.8 "Decision History" viewer. Each event gains a field-level
``diff`` (``added`` / ``removed`` / ``changed``) computed from the ``before`` /
``after`` snapshots plus a ``target_ref``. Entries are sorted by ``created_at``
descending (newest first) with stable ties. Side-effect free, deterministic,
stdlib only.

* :func:`compute_diff` — снимки before/after → пофайловый дифф / field diff.
* :class:`DecisionHistoryView` — неизменяемое представление с :meth:`as_dict`.
* :func:`build_decision_history` — список событий → ``DecisionHistoryView``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

__all__ = [
    "DecisionHistoryView",
    "build_decision_history",
    "compute_diff",
]


def _as_mapping(value: Any) -> dict[str, Any]:
    """Нормализовать снимок в словарь: ``None`` → ``{}`` / snapshot → dict.

    Отсутствующий или ``None`` снимок трактуется как пустой словарь, поэтому все
    ключи противоположного снимка попадают в ``added`` либо ``removed``.

    A missing or ``None`` snapshot is treated as an empty mapping so every key of
    the opposite snapshot lands in ``added`` or ``removed`` respectively.
    """
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def compute_diff(before: Any, after: Any) -> dict[str, dict[str, Any]]:
    """Вычислить пофайловый дифф между снимками ``before`` и ``after`` (§5.2.8).

    Возвращает ``{added, removed, changed}``: ``added`` — ключи только в
    ``after``; ``removed`` — ключи только в ``before``; ``changed`` — ключи в
    обоих с разными значениями, как ``{key: {'from': x, 'to': y}}``. Неизменённые
    ключи не попадают ни в одну из групп. Пропущенный/``None`` снимок — ``{}``.

    Returns ``{added, removed, changed}``: ``added`` holds keys present only in
    ``after``; ``removed`` keys present only in ``before``; ``changed`` keys in
    both whose values differ, as ``{key: {'from': x, 'to': y}}``. Unchanged keys
    appear in none of the groups. A missing/``None`` snapshot counts as ``{}``.
    """
    before_map = _as_mapping(before)
    after_map = _as_mapping(after)

    added = {k: v for k, v in after_map.items() if k not in before_map}
    removed = {k: v for k, v in before_map.items() if k not in after_map}
    changed = {
        k: {"from": before_map[k], "to": after_map[k]}
        for k in before_map
        if k in after_map and before_map[k] != after_map[k]
    }
    return {"added": added, "removed": removed, "changed": changed}


def _project_entry(event: Mapping[str, Any]) -> dict[str, Any]:
    """Спроецировать одно событие в запись истории с ``diff`` и ``target_ref``.

    Project a single §12.3 event into a history entry, copying its fields and
    appending the computed ``diff`` and a ``target_ref`` ``{type, id}``.
    """
    entry = dict(event)
    entry["diff"] = compute_diff(event.get("before"), event.get("after"))
    entry["target_ref"] = {
        "type": event.get("target_type"),
        "id": event.get("target_id"),
    }
    return entry


@dataclass(frozen=True, slots=True)
class DecisionHistoryView:
    """Неизменяемое представление истории решений (§5.2.8).

    ``entries`` — кортеж записей, отсортированных по ``created_at`` по убыванию
    (новейшие первыми), каждая с полями ``diff`` и ``target_ref``; ``total`` —
    число исходных событий.

    Immutable Decision History projection. ``entries`` is a tuple of entry dicts
    sorted by ``created_at`` descending (newest first), each carrying a ``diff``
    and a ``target_ref``; ``total`` is the count of source events.
    """

    entries: tuple[dict[str, Any], ...]
    total: int

    def as_dict(self) -> dict[str, Any]:
        """Структурная форма — ``{entries, total}`` (§5.2.8), JSON-сериализуемая.

        Structural wire form ``{entries, total}``; entries are returned verbatim
        so the payload is JSON-serialisable.
        """
        return {"entries": list(self.entries), "total": self.total}


def build_decision_history(events: Sequence[Mapping[str, Any]]) -> DecisionHistoryView:
    """Построить :class:`DecisionHistoryView` из событий §12.3 (§5.2.8).

    Каждое событие проецируется в запись с пофайловым ``diff`` и ``target_ref``;
    записи сортируются по ``created_at`` по убыванию (новейшие первыми) стабильно,
    поэтому события с равной датой сохраняют исходный порядок. ``total`` равно
    числу входных событий. Пустой вход даёт ``entries == ()`` и ``total == 0``.

    Project each §12.3 event into an entry bearing a field-level ``diff`` and a
    ``target_ref``, then sort by ``created_at`` descending (newest first) with a
    stable sort so equal-dated events keep their input order. ``total`` equals the
    number of input events. An empty input yields ``entries == ()``, ``total == 0``.
    """
    projected = [_project_entry(event) for event in events]
    projected.sort(key=lambda e: e.get("created_at"), reverse=True)
    return DecisionHistoryView(entries=tuple(projected), total=len(events))
