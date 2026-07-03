"""Bulk resolution planner for the §16.9 curation backend (RU/EN).

Чистый планировщик (pure planner) — вычисляет, какие задачи очереди курации
(curation queue tasks) попадут под одно массовое действие (bulk action), а какие
будут пропущены и почему, **не выполняя** никаких записей в граф. Это позволяет
показать оператору предпросмотр (preview) прежде, чем действие применится.

A task participates only when it is still actionable (``status`` in
``{open, in_review}``) and its ``task_type`` is one of the ``allowed_types`` for
the requested action (e.g. "accept all evidence from a trusted doc"). Skipped
tasks record a reason: ``'closed'`` (already resolved) or ``'type_not_allowed'``.
Distinct ``target_ids`` are collected in first-seen order for deduplicated apply.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

# Statuses that still accept a bulk action (открытые задачи).
_OPEN_STATUSES = frozenset({"open", "in_review"})


def is_applicable(task: Mapping, allowed_types: Sequence[str]) -> bool:
    """Return ``True`` if ``task`` may receive the bulk action (§16.9).

    Задача применима, когда её ``status`` ещё открыт (``open``/``in_review``) и
    её ``task_type`` входит в ``allowed_types``. Missing keys are treated as a
    non-open status / disallowed type, i.e. not applicable.
    """
    status = str(task.get("status", ""))
    task_type = str(task.get("task_type", ""))
    return status in _OPEN_STATUSES and task_type in set(allowed_types)


@dataclass(frozen=True)
class BulkPlan:
    """Planned fan-out of one curation action across many tasks (§16.9).

    План массового разрешения: ``applicable`` — id задач, к которым действие
    будет применено; ``skipped`` сопоставляет id пропущенной задачи с причиной
    (``'closed'`` либо ``'type_not_allowed'``); ``target_ids`` — различные
    целевые id (сущности/ребра) в порядке первого появления (dedup, first-seen).
    """

    action: str
    applicable: list[str]
    skipped: dict[str, str]
    target_ids: list[str]

    def as_dict(self) -> dict:
        """Return a JSON-friendly plain-``dict`` view (сериализуемый вид)."""
        return {
            "action": self.action,
            "applicable": list(self.applicable),
            "skipped": dict(self.skipped),
            "target_ids": list(self.target_ids),
        }


def plan_bulk(
    tasks: Sequence[Mapping],
    action: str,
    allowed_types: Sequence[str],
) -> BulkPlan:
    """Compute a :class:`BulkPlan` for applying ``action`` across ``tasks`` (§16.9).

    Каждая задача с ``status`` в ``{open, in_review}`` и ``task_type`` из
    ``allowed_types`` идёт в ``applicable``; остальные попадают в ``skipped`` с
    причиной ``'closed'`` (неоткрытый статус) или ``'type_not_allowed'`` (тип не
    разрешён). ``target_ids`` собираются без дублей в порядке первого появления.

    Задача идентифицируется по ключу ``task_id``; цель — по ключу ``target_id``.
    """
    allowed = set(allowed_types)

    applicable: list[str] = []
    skipped: dict[str, str] = {}
    target_ids: list[str] = []
    seen_targets: set[str] = set()

    for task in tasks:
        task_id = str(task["task_id"])
        status = str(task.get("status", ""))
        task_type = str(task.get("task_type", ""))

        if status not in _OPEN_STATUSES:
            skipped[task_id] = "closed"
            continue
        if task_type not in allowed:
            skipped[task_id] = "type_not_allowed"
            continue

        applicable.append(task_id)
        if "target_id" in task and task["target_id"] is not None:
            target_id = str(task["target_id"])
            if target_id not in seen_targets:
                seen_targets.add(target_id)
                target_ids.append(target_id)

    return BulkPlan(
        action=action,
        applicable=applicable,
        skipped=skipped,
        target_ids=target_ids,
    )
