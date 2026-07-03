"""Before/after diff builder for the audit_log jsonb payload (§19.5 audit logs).

The audit_log schema stores a ``before``/``after`` jsonb pair per mutation, yet
``audit_formatter`` / ``audit_query`` only render and filter rows — nothing
computes the actual field-level delta («никто не считает дельту полей»). This
module fills that gap: :func:`compute_diff` walks two mappings and returns a
frozen :class:`AuditDiff` describing exactly which fields changed (added /
removed / modified), redacting secret-bearing keys so passwords or tokens never
land in the audit trail. :meth:`AuditDiff.as_dict` yields the compact
``{'before': …, 'after': …, 'changed': […]}`` payload — ``before``/``after``
contain **only** the changed keys, not the untouched ones. Pure-python, no
third-party dependency; inputs are never mutated («вход не мутируем»).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

# Redaction marker («маска») substituted for a secret value on either side.
_MASK = "***"

# Keys whose values are secret-bearing and must be masked in the diff payload.
DEFAULT_REDACT_KEYS: frozenset[str] = frozenset({"password", "token", "secret", "password_hash"})


@dataclass(frozen=True, slots=True)
class FieldChange:
    """A single field's before/after values («изменение одного поля»).

    ``before`` is ``None`` for an added key, ``after`` is ``None`` for a removed
    key; secret-bearing values are already redacted by :func:`compute_diff`.
    """

    field: str
    before: Any
    after: Any

    def as_dict(self) -> dict[str, Any]:
        """Return this change as a plain ``{'field','before','after'}`` dict."""
        return {"field": self.field, "before": self.before, "after": self.after}


@dataclass(frozen=True, slots=True)
class AuditDiff:
    """An ordered set of :class:`FieldChange` rows for one mutation (§19.5)."""

    changes: tuple[FieldChange, ...]

    def as_dict(self) -> dict[str, Any]:
        """Return the audit_log jsonb payload («полезная нагрузка audit_log»).

        ``before``/``after`` map each changed field to its respective value and
        contain **only** changed keys; ``changed`` is the ordered field list.
        """
        before: dict[str, Any] = {}
        after: dict[str, Any] = {}
        changed: list[str] = []
        for change in self.changes:
            before[change.field] = change.before
            after[change.field] = change.after
            changed.append(change.field)
        return {"before": before, "after": after, "changed": changed}


def _redact(value: Any, *, is_secret: bool) -> Any:
    """Return *value*, masked to :data:`_MASK` when *is_secret* and not ``None``."""
    if not is_secret:
        return value
    return None if value is None else _MASK


def compute_diff(
    before: Mapping[str, Any],
    after: Mapping[str, Any],
    *,
    redact_keys: frozenset[str] = DEFAULT_REDACT_KEYS,
) -> AuditDiff:
    """Compute the field-level diff between *before* and *after* (§19.5).

    A key present on only one side yields a :class:`FieldChange` with the missing
    side set to ``None`` (added ⇒ ``before=None``, removed ⇒ ``after=None``). A
    key present on both sides is emitted only when its values differ. Values
    under a *redact_keys* field are masked on both sides. Keys are ordered by
    first appearance in *before* then any *after*-only keys («порядок ключей»).
    """
    changes: list[FieldChange] = []
    seen: set[str] = set()
    keys: list[str] = list(before)
    for key in after:
        if key not in before:
            keys.append(key)
    for key in keys:
        if key in seen:
            continue
        seen.add(key)
        in_before = key in before
        in_after = key in after
        raw_before = before.get(key)
        raw_after = after.get(key)
        if in_before and in_after and raw_before == raw_after:
            continue
        is_secret = key in redact_keys
        changes.append(
            FieldChange(
                field=key,
                before=_redact(raw_before, is_secret=is_secret) if in_before else None,
                after=_redact(raw_after, is_secret=is_secret) if in_after else None,
            )
        )
    return AuditDiff(changes=tuple(changes))


def changed_fields(diff: AuditDiff) -> tuple[str, ...]:
    """Return the tuple of changed field names in diff order («изменённые поля»)."""
    return tuple(change.field for change in diff.changes)
