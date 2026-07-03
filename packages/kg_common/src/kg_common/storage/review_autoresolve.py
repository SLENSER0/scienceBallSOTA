"""Auto-resolve stale review tasks (§16.4 авто-снятие устаревших задач ревью).

A *задача ревью* (review task) is opened when an extractor or a guard finds a
defect: a missing critical field, a low-confidence value, a contradiction, an
ambiguous ER (entity-resolution) merge, and so on. Over time the *target state*
(the current node / decision the task points at) may drift so that the original
defect **no longer holds** — the field got filled, confidence rose, the
contradiction was resolved, the ambiguous merge was decided. Such a task is
*stale*: keeping it open wastes a curator's attention.

The :class:`~kg_common.storage.review_queue.ReviewTask` model already defines an
``auto_resolved`` status and the metrics layer tracks ``auto_resolved_ratio``,
but nothing *detects* staleness. This module supplies that detector as pure,
deterministic functions — no store, no I/O, no ``datetime.now`` — so results are
fully hand-checkable (детерминированность). The caller feeds each task plus its
current target state; the module decides whether the defect has cleared.

Per-``task_type`` checks (проверки по типу задачи)
--------------------------------------------------
* ``missing_critical_field`` — resolves once **every** field named in
  ``payload['missing_fields']`` is present and non-null in the target state;
* ``low_confidence`` — resolves once ``target_state['confidence']`` has risen to
  at least ``payload['threshold']``;
* ``contradiction`` — resolves once ``target_state['status'] == 'resolved'``;
* ``ambiguous_er`` — resolves once ``target_state['decision'] == 'resolved'``;
* any other type (``low_quality_ocr``, ``low_confidence`` variants we don't
  model, …) **never** auto-resolves — a human must look.

:func:`evaluate_task` returns an :class:`AutoResolveDecision` for one task;
:func:`scan` returns only the ``resolve=True`` decisions, and only for tasks
that are still *open* / *in_review* (уже закрытые задачи пропускаются).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

# -- task-type vocabulary (словарь типов задач, §16.4) --------------------
#: The task types this module knows how to auto-resolve. Anything else is left
#: for a human (see module docstring).
MISSING_CRITICAL_FIELD = "missing_critical_field"
LOW_CONFIDENCE = "low_confidence"
CONTRADICTION = "contradiction"
AMBIGUOUS_ER = "ambiguous_er"

#: Statuses a task must have to be eligible for a :func:`scan` sweep. A task
#: that is already ``resolved`` / ``auto_resolved`` / ``dismissed`` is skipped.
OPEN_STATUSES: frozenset[str] = frozenset({"open", "in_review"})


@dataclass(frozen=True, slots=True)
class AutoResolveDecision:
    """Verdict for one review task (вердикт авто-снятия для одной задачи).

    ``resolve`` is ``True`` iff the original defect no longer holds; ``reason``
    names the satisfied (or unsatisfied) condition in plain English for the
    audit trail / metrics.
    """

    task_id: str
    resolve: bool
    reason: str

    def as_dict(self) -> dict[str, Any]:
        """Serialize to a plain ``dict`` (round-trips via ``**d`` into the ctor)."""
        return {"task_id": self.task_id, "resolve": self.resolve, "reason": self.reason}


def _field_present(state: Mapping[str, Any], field: str) -> bool:
    """True iff ``field`` is present in ``state`` **and** its value is non-null."""
    return field in state and state[field] is not None


def _eval_missing_critical_field(
    task_id: str, payload: Mapping[str, Any], target_state: Mapping[str, Any]
) -> AutoResolveDecision:
    """Resolve once every ``payload['missing_fields']`` is present + non-null."""
    missing_fields = payload.get("missing_fields") or []
    absent = [f for f in missing_fields if not _field_present(target_state, f)]
    if absent:
        return AutoResolveDecision(
            task_id, False, f"missing_critical_field: still missing {sorted(absent)}"
        )
    return AutoResolveDecision(
        task_id,
        True,
        f"missing_critical_field: all fields present {sorted(missing_fields)}",
    )


def _eval_low_confidence(
    task_id: str, payload: Mapping[str, Any], target_state: Mapping[str, Any]
) -> AutoResolveDecision:
    """Resolve once ``target_state['confidence'] >= payload['threshold']``."""
    threshold = payload["threshold"]
    confidence = target_state.get("confidence")
    if confidence is not None and confidence >= threshold:
        return AutoResolveDecision(
            task_id,
            True,
            f"low_confidence: confidence {confidence} >= threshold {threshold}",
        )
    return AutoResolveDecision(
        task_id,
        False,
        f"low_confidence: confidence {confidence} < threshold {threshold}",
    )


def _eval_status_resolved(
    task_id: str, target_state: Mapping[str, Any], task_type: str
) -> AutoResolveDecision:
    """Resolve once ``target_state['status'] == 'resolved'`` (contradiction)."""
    status = target_state.get("status")
    if status == "resolved":
        return AutoResolveDecision(task_id, True, f"{task_type}: target status resolved")
    return AutoResolveDecision(
        task_id, False, f"{task_type}: target status {status!r} != 'resolved'"
    )


def _eval_decision_resolved(task_id: str, target_state: Mapping[str, Any]) -> AutoResolveDecision:
    """Resolve once ``target_state['decision'] == 'resolved'`` (ambiguous ER)."""
    decision = target_state.get("decision")
    if decision == "resolved":
        return AutoResolveDecision(task_id, True, "ambiguous_er: decision resolved")
    return AutoResolveDecision(task_id, False, f"ambiguous_er: decision {decision!r} != 'resolved'")


def evaluate_task(task: Mapping[str, Any], target_state: Mapping[str, Any]) -> AutoResolveDecision:
    """Decide whether ``task``'s defect has cleared given its ``target_state``.

    Dispatches on ``task['task_type']``; unknown types never auto-resolve. The
    task id is read from ``task['task_id']`` (falling back to ``task['id']``).
    """
    task_id = str(task.get("task_id") or task.get("id") or "")
    task_type = task.get("task_type", "")
    payload: Mapping[str, Any] = task.get("payload") or {}

    if task_type == MISSING_CRITICAL_FIELD:
        return _eval_missing_critical_field(task_id, payload, target_state)
    if task_type == LOW_CONFIDENCE:
        return _eval_low_confidence(task_id, payload, target_state)
    if task_type == CONTRADICTION:
        return _eval_status_resolved(task_id, target_state, CONTRADICTION)
    if task_type == AMBIGUOUS_ER:
        return _eval_decision_resolved(task_id, target_state)
    return AutoResolveDecision(task_id, False, f"{task_type!r}: type is not auto-resolvable")


def scan(
    tasks: Sequence[Mapping[str, Any]], states: Mapping[str, Mapping[str, Any]]
) -> list[AutoResolveDecision]:
    """Sweep ``tasks``, returning only ``resolve=True`` decisions.

    Only tasks whose ``status`` is *open* / *in_review* are considered; a task
    already closed (``resolved`` / ``auto_resolved`` / ``dismissed``) is skipped.
    Each task's target state is looked up in ``states`` by task id; a task with
    no matching state is treated as having an empty state (never resolves).
    """
    decisions: list[AutoResolveDecision] = []
    for task in tasks:
        if task.get("status") not in OPEN_STATUSES:
            continue
        task_id = str(task.get("task_id") or task.get("id") or "")
        target_state = states.get(task_id, {})
        decision = evaluate_task(task, target_state)
        if decision.resolve:
            decisions.append(decision)
    return decisions
