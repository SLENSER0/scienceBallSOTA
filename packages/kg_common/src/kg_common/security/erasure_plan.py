"""Right-to-erasure cascade planner across stores (§19.5 audit/privacy).

GDPR-style «право на забвение» requires erasing a data subject's records from
every store, yet the immutable audit trail must survive for compliance —
nothing here deletes it, it is **anonymized** instead of removed («аудит не
удаляем, а обезличиваем»). :func:`plan_erasure` maps each store to an
:class:`ErasureAction`: stores in *immutable_stores* get op ``'anonymize'``,
all others get op ``'delete'``. The resulting :class:`ErasurePlan` holds the
actions sorted by store name so callers can execute them deterministically;
:func:`actions_for` filters a plan down to a single op. Pure-python, no
third-party dependency; inputs are never mutated («вход не мутируем»).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

# The two erasure operations («операции стирания»): hard delete vs anonymize.
OP_DELETE = "delete"
OP_ANONYMIZE = "anonymize"

# Stores whose rows are immutable audit records — anonymize, never delete.
DEFAULT_IMMUTABLE_STORES: frozenset[str] = frozenset({"audit_log"})


@dataclass(frozen=True, slots=True)
class ErasureAction:
    """One store's erasure step for a subject («шаг стирания в одном сторе»).

    ``store`` is the store name, ``target`` is the subject id being erased and
    ``op`` is either :data:`OP_DELETE` or :data:`OP_ANONYMIZE`.
    """

    store: str
    target: str
    op: str

    def as_dict(self) -> dict[str, Any]:
        """Return this action as a plain ``{'store','target','op'}`` dict."""
        return {"store": self.store, "target": self.target, "op": self.op}


@dataclass(frozen=True, slots=True)
class ErasurePlan:
    """An ordered cascade of :class:`ErasureAction` for one subject (§19.5)."""

    subject_id: str
    actions: tuple[ErasureAction, ...]

    def as_dict(self) -> dict[str, Any]:
        """Return the plan as ``{'subject_id': …, 'actions': [<action dict>…]}``."""
        return {
            "subject_id": self.subject_id,
            "actions": [action.as_dict() for action in self.actions],
        }


def plan_erasure(
    subject_id: str,
    stores: Iterable[str],
    *,
    immutable_stores: frozenset[str] = DEFAULT_IMMUTABLE_STORES,
) -> ErasurePlan:
    """Plan erasure of *subject_id* across *stores* (§19.5 right-to-erasure).

    Each store yields one :class:`ErasureAction` whose ``target`` is
    *subject_id*. Stores listed in *immutable_stores* get op
    :data:`OP_ANONYMIZE` (audit records are preserved but obscured), every
    other store gets op :data:`OP_DELETE`. Actions are sorted by store name so
    execution order is deterministic («порядок по имени стора»). An empty
    *stores* yields an empty action tuple.
    """
    actions = [
        ErasureAction(
            store=store,
            target=subject_id,
            op=OP_ANONYMIZE if store in immutable_stores else OP_DELETE,
        )
        for store in stores
    ]
    actions.sort(key=lambda action: action.store)
    return ErasurePlan(subject_id=subject_id, actions=tuple(actions))


def actions_for(plan: ErasurePlan, op: str) -> tuple[ErasureAction, ...]:
    """Return *plan*'s actions whose ``op`` equals *op* («действия по op»)."""
    return tuple(action for action in plan.actions if action.op == op)
