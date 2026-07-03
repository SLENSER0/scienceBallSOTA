"""§15.4 / §15.7 / §12.1 review-task payloads from critical gaps & contradictions.

RU: Чистый (без хранилища) конвертер, превращающий *критичные* пробелы (gap) и
противоречия (contradiction) в полезную нагрузку задач курирования (review-task) для
очереди §15.7. Триггеры §12.1: «critical field missing» (критичное поле отсутствует)
и «claim contradicts existing claim» (утверждение противоречит существующему).
:func:`gap_to_task` пропускает только критичные типы пробелов и отбрасывает пробелы
с severity ``'low'``; :func:`contradiction_to_task` выводит приоритет из
``relative_diff``; :func:`build_review_tasks` собирает и дедуплицирует задачи по
тройке ``(kind, subject_id, gap_type)``.

EN: Pure-python converter (no store/graph/DB) turning *critical* gaps and
contradictions into curation review-task payloads for the §15.7 queue. §12.1 triggers
are «critical field missing» and «claim contradicts existing claim». A gap becomes a
task only when its ``gap_type`` is in :data:`CRITICAL_GAP_TYPES` and its ``severity``
is not ``'low'``; a contradiction always becomes a task with priority derived from its
``relative_diff``. :func:`build_review_tasks` merges both streams and de-duplicates by
``(kind, subject_id, gap_type)``, keeping the first occurrence.

Kuzu note: custom node props are NOT queryable columns — RETURN base columns and read
the rest via ``get_node()`` before assembling the ``dict``s fed to these functions.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

# §15.4: sha1 hex-prefix length keying the compact, stable task_id fingerprint.
_HASH_LEN = 12

# §12.1: gap types severe enough to raise a curation task. Anything outside this set
# (e.g. ``missing_baseline``) is informational and yields no task.
CRITICAL_GAP_TYPES: frozenset[str] = frozenset(
    {
        "unverified_claim",
        "contradictory_measurements",
        "missing_source_span",
        "low_confidence_entity_resolution",
    }
)

# Severities that never raise a task even for a critical ``gap_type`` (§12.1).
_SKIP_SEVERITIES: frozenset[str] = frozenset({"low"})

# §12.1 trigger reason strings.
_REASON_GAP = "critical field missing"
_REASON_CONTRADICTION = "claim contradicts existing claim"

# Contradiction ``relative_diff`` thresholds → priority (§15.4). ``>=0.5`` is high.
_CONTRADICTION_HIGH = 0.5
_CONTRADICTION_MEDIUM = 0.2


@dataclass(frozen=True)
class ReviewTask:
    """A single curation review-task payload (§15.4 / §15.7).

    ``task_id`` — детерминированный отпечаток задачи; ``kind`` — ``'gap'`` или
    ``'contradiction'``; ``priority`` — ``'high' | 'medium' | 'low'``; ``subject_id`` —
    идентификатор сущности/утверждения; ``gap_type`` — тип пробела (``None`` для
    противоречий); ``evidence_ids`` — переносимые как есть идентификаторы улик;
    ``reason`` — человекочитаемая причина (триггер §12.1).
    """

    task_id: str
    kind: str
    priority: str
    subject_id: str
    gap_type: str | None
    evidence_ids: list[str]
    reason: str

    def as_dict(self) -> dict[str, Any]:
        """Plain-dict projection exposing all seven fields (§15.4, house style)."""
        return {
            "task_id": self.task_id,
            "kind": self.kind,
            "priority": self.priority,
            "subject_id": self.subject_id,
            "gap_type": self.gap_type,
            "evidence_ids": list(self.evidence_ids),
            "reason": self.reason,
        }


def _evidence_ids(source: dict[str, Any]) -> list[str]:
    """Carry ``evidence_ids`` through as a list of ``str``, preserving order (§15.4)."""
    raw: Iterable[Any] = source.get("evidence_ids") or ()
    return [str(item) for item in raw]


def _task_id(kind: str, subject_id: str, gap_type: str | None, evidence_ids: list[str]) -> str:
    """Deterministic ``task:<kind>:<sha1[:12]>`` id for a review task (§15.4).

    Отпечаток берётся от ``kind``, ``subject_id``, ``gap_type`` и **отсортированного**
    множества ``evidence_ids`` через разделитель ``\\x00`` (не встречается в id), поэтому
    один и тот же вход всегда даёт один и тот же id, а порядок улик на него не влияет.
    """
    gap_part = gap_type if gap_type is not None else ""
    parts = [kind, subject_id, gap_part, *sorted(set(evidence_ids))]
    payload = "\x00".join(parts).encode("utf-8")
    digest = hashlib.sha1(payload).hexdigest()[:_HASH_LEN]  # fingerprint, not crypto
    return f"task:{kind}:{digest}"


def gap_to_task(gap: dict[str, Any]) -> ReviewTask | None:
    """Convert a critical gap ``dict`` to a :class:`ReviewTask`, else ``None`` (§12.1).

    Возвращает ``None``, если ``gap_type`` не входит в :data:`CRITICAL_GAP_TYPES` или
    ``severity`` попадает в :data:`_SKIP_SEVERITIES` (``'low'``). Иначе строит задачу
    ``kind='gap'`` с ``priority == severity`` (например ``'high' -> 'high'``),
    перенося ``subject_id``, ``gap_type`` и ``evidence_ids`` из исходного словаря.
    """
    gap_type = gap.get("gap_type")
    if gap_type not in CRITICAL_GAP_TYPES:
        return None
    severity = str(gap.get("severity", "")).strip().lower()
    if severity in _SKIP_SEVERITIES:
        return None
    priority = severity or "medium"
    subject_id = str(gap.get("subject_id", ""))
    evidence_ids = _evidence_ids(gap)
    reason = str(gap.get("reason") or _REASON_GAP)
    return ReviewTask(
        task_id=_task_id("gap", subject_id, str(gap_type), evidence_ids),
        kind="gap",
        priority=priority,
        subject_id=subject_id,
        gap_type=str(gap_type),
        evidence_ids=evidence_ids,
        reason=reason,
    )


def _contradiction_priority(relative_diff: float) -> str:
    """Map a contradiction ``relative_diff`` to a priority band (§15.4)."""
    if relative_diff >= _CONTRADICTION_HIGH:
        return "high"
    if relative_diff >= _CONTRADICTION_MEDIUM:
        return "medium"
    return "low"


def contradiction_to_task(c: dict[str, Any]) -> ReviewTask:
    """Convert a contradiction ``dict`` to a ``kind='contradiction'`` task (§12.1).

    Приоритет выводится из ``relative_diff``: ``>=0.5 -> 'high'``, ``>=0.2 -> 'medium'``,
    иначе ``'low'``. ``gap_type`` всегда ``None`` (это противоречие, не пробел). Причина —
    триггер §12.1 «claim contradicts existing claim», если своя не задана.
    """
    try:
        relative_diff = float(c.get("relative_diff", 0.0))
    except (TypeError, ValueError):
        relative_diff = 0.0
    subject_id = str(c.get("subject_id", ""))
    evidence_ids = _evidence_ids(c)
    reason = str(c.get("reason") or _REASON_CONTRADICTION)
    return ReviewTask(
        task_id=_task_id("contradiction", subject_id, None, evidence_ids),
        kind="contradiction",
        priority=_contradiction_priority(relative_diff),
        subject_id=subject_id,
        gap_type=None,
        evidence_ids=evidence_ids,
        reason=reason,
    )


def build_review_tasks(
    gaps: list[dict[str, Any]],
    contradictions: list[dict[str, Any]],
) -> list[ReviewTask]:
    """Build and de-duplicate review tasks from gaps and contradictions (§15.4 / §15.7).

    Прогоняет ``gaps`` через :func:`gap_to_task` (не-критичные и ``severity='low'``
    отбрасываются, возвращая ``None``) и ``contradictions`` через
    :func:`contradiction_to_task`. Задачи дедуплицируются по тройке
    ``(kind, subject_id, gap_type)`` с сохранением первого вхождения; порядок — сперва
    задачи по пробелам, затем по противоречиям.
    """
    seen: set[tuple[str, str, str | None]] = set()
    tasks: list[ReviewTask] = []
    gap_tasks = (gap_to_task(gap) for gap in gaps)
    contra_tasks = (contradiction_to_task(c) for c in contradictions)
    for task in (*gap_tasks, *contra_tasks):
        if task is None:
            continue
        key = (task.kind, task.subject_id, task.gap_type)
        if key in seen:
            continue
        seen.add(key)
        tasks.append(task)
    return tasks
