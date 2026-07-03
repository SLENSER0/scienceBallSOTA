"""§16.4 review-task dedup key + collision-merge reconciliation (pure python).

RU: Канонический ключ дедупликации задач проверки (§16.4). Ключ =
``sha256(task_type, target_type, target_id, канонизированный-JSON payload)`` —
богаче ключа ``target_id:kind`` из ``review_gen`` (§16.5) и отличается от
``gap_dedup_key`` (§15.2). :func:`dedup_key` строит стабильный хеш: payload
сериализуется в JSON с **отсортированными ключами**, поэтому разный порядок
ключей payload даёт один и тот же ключ. :func:`reconcile` применяет политику
коллизий: при совпадении ключа с *открытой* задачей payload сливается, а
priority берётся максимальный (``updated``); для *закрытой* (resolved/dismissed)
задачи — ``skipped``; при отсутствии существующей — ``created``.
EN: Canonical dedup key for review tasks (§16.4). The key is
``sha256(task_type, target_type, target_id, canonicalized-JSON payload)`` —
richer than ``review_gen``'s ``target_id:kind`` key (§16.5) and distinct from
``gap_dedup_key`` (§15.2). :func:`dedup_key` builds a stable digest: the payload
is JSON-serialized with **sorted keys**, so payload key-order does not change the
key. :func:`reconcile` applies the collision policy: a key clash with an *open*
task merges payloads and takes the max priority (``updated``); a *closed*
(resolved/dismissed) task yields ``skipped``; no existing task yields ``created``.

Pure python — no store/graph/DB access: callers pass already-read task ``dict``s.
Kuzu note: custom node props are NOT queryable columns — RETURN base columns and
read the rest via ``get_node()`` before assembling the task dicts fed here.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

# §16.4: task fields that identify *what* is being reviewed (the dedup tuple).
_TASK_TYPE_KEY = "task_type"
_TARGET_TYPE_KEY = "target_type"
_TARGET_ID_KEY = "target_id"
_PAYLOAD_KEY = "payload"
_PRIORITY_KEY = "priority"
_STATUS_KEY = "status"

# §16.4: lifecycle states that keep a task *open* to updates vs. *closed*.
_OPEN_STATES: frozenset[str] = frozenset({"open", "in_review"})
_CLOSED_STATES: frozenset[str] = frozenset({"resolved", "dismissed"})

# §16.4: reconcile actions.
ACTION_CREATED = "created"
ACTION_UPDATED = "updated"
ACTION_SKIPPED = "skipped"


@dataclass(frozen=True)
class DedupOutcome:
    """Frozen result of :func:`reconcile` (§16.4).

    ``dedup_key`` — 64-символьный hex-дайджест sha256; ``action`` ∈
    {``created``, ``updated``, ``skipped``}; ``priority`` — итоговый приоритет
    (для ``updated`` — максимум из нового и существующего); ``payload`` —
    итоговый payload (для ``updated`` — слитый, существующий обновлён новым).
    """

    dedup_key: str
    action: str
    priority: int
    payload: Mapping[str, Any]

    def as_dict(self) -> dict[str, Any]:
        """Plain-dict projection for trace / round-trip (§16.4, house style)."""
        return {
            "dedup_key": self.dedup_key,
            "action": self.action,
            "priority": self.priority,
            "payload": dict(self.payload),
        }


def _canonical_payload(payload: Any) -> str:
    """Canonical JSON of a payload with sorted keys, stable across key-order (§16.4).

    ``sort_keys=True`` нормализует порядок ключей на любой глубине, а компактные
    разделители убирают незначащие пробелы, поэтому семантически равные payload'ы
    дают идентичную строку (и, значит, идентичный дайджест). ``None`` → ``"null"``.
    """
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def dedup_key(task: Mapping[str, Any]) -> str:
    """Stable sha256 hex dedup key for a review task (§16.4).

    Хеширует кортеж ``(task_type, target_type, target_id, канонический payload)``:
    поля идентификации берутся как строки, payload канонизируется через
    :func:`_canonical_payload` (сортировка ключей), поэтому разный порядок ключей
    payload не меняет ключ, а разный ``target_id`` (или тип/тип-цели) — меняет.
    Части соединяются ``\\x00`` (разделитель, невозможный внутри значений), чтобы
    исключить склейку-коллизию. Возвращает 64-символьный hex sha256.
    """
    parts = (
        str(task.get(_TASK_TYPE_KEY, "")),
        str(task.get(_TARGET_TYPE_KEY, "")),
        str(task.get(_TARGET_ID_KEY, "")),
        _canonical_payload(task.get(_PAYLOAD_KEY)),
    )
    blob = "\x00".join(parts).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def _priority_of(task: Mapping[str, Any]) -> int:
    """Read a task's integer priority, defaulting to 0 if absent/non-numeric (§16.4)."""
    try:
        return int(task.get(_PRIORITY_KEY, 0))
    except (TypeError, ValueError):
        return 0


def _merge_payloads(existing: Any, new: Any) -> dict[str, Any]:
    """Shallow merge of two payloads, new keys overriding existing ones (§16.4)."""
    merged: dict[str, Any] = {}
    if isinstance(existing, Mapping):
        merged.update(existing)
    if isinstance(new, Mapping):
        merged.update(new)
    return merged


def reconcile(new_task: Mapping[str, Any], existing: Mapping[str, Any] | None) -> DedupOutcome:
    """Apply the §16.4 collision policy for a minted review task.

    * ``existing is None`` → ``created``: the new task's own key/priority/payload.
    * existing shares the key and is *open* (``open`` / ``in_review``) → ``updated``:
      payloads are merged (new keys win) and ``priority = max(new, existing)`` — the
      open task is enriched in place instead of duplicating it.
    * existing is *closed* (``resolved`` / ``dismissed``) → ``skipped``: the new task
      is dropped, carrying the existing key/priority/payload so callers can trace it.

    The dedup key is computed from ``new_task`` and returned on every outcome.
    """
    key = dedup_key(new_task)
    new_priority = _priority_of(new_task)
    if existing is None:
        return DedupOutcome(
            dedup_key=key,
            action=ACTION_CREATED,
            priority=new_priority,
            payload=dict(new_task.get(_PAYLOAD_KEY) or {}),
        )
    status = str(existing.get(_STATUS_KEY, "")).strip().lower()
    if status in _CLOSED_STATES:
        return DedupOutcome(
            dedup_key=key,
            action=ACTION_SKIPPED,
            priority=_priority_of(existing),
            payload=dict(existing.get(_PAYLOAD_KEY) or {}),
        )
    # Open / in_review (or any non-closed state): enrich the existing task.
    merged = _merge_payloads(existing.get(_PAYLOAD_KEY), new_task.get(_PAYLOAD_KEY))
    return DedupOutcome(
        dedup_key=key,
        action=ACTION_UPDATED,
        priority=max(new_priority, _priority_of(existing)),
        payload=merged,
    )
