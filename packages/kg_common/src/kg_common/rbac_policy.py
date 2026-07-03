"""Role-based access-control policy — политика ролевого доступа (§19.12).

Every privileged operation must be gated by an explicit role→action table, and
that table must be the single source of truth («единая таблица прав»). This
module defines a small, deterministic RBAC model with five roles and a fixed set
of coarse-grained actions, plus helpers to *ask* (:func:`can`), *enforce*
(:func:`require`) and *project* (:func:`visible_fields`) that policy.

The roles form a rough capability ladder:

* ``admin``            — everything, including user/role administration.
* ``curator``          — reviews and *merges* entities, edits the graph.
* ``researcher``       — reads and *writes* (ingests / annotates) data.
* ``analyst``          — read-only analytics over the graph.
* ``external_partner`` — read-only, and *restricted fields are hidden* from them
  (§19.12 «внешним партнёрам скрываются служебные поля»).

Everything here is pure and side-effect free: no I/O, no wall-clock, no globals
mutated at call time. The permission table is a frozen mapping of frozensets, so
callers cannot accidentally widen anyone's rights.

Public API:

* :data:`ROLE_PERMISSIONS`  — ``role → frozenset[action]`` policy table.
* :data:`RESTRICTED_FIELDS` — field names hidden from ``external_partner``.
* :class:`AccessDecision`   — frozen ``{role, action, allowed}`` record.
* :func:`can`               — does ``role`` have ``action``? → ``bool``.
* :func:`require`           — enforce ``action``, raising :class:`PermissionError`.
* :func:`decide`            — build an :class:`AccessDecision` for ``(role, action)``.
* :func:`visible_fields`    — the fields ``role`` may see, given a full field set.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

__all__ = [
    "ACTIONS",
    "ROLES",
    "ROLE_PERMISSIONS",
    "RESTRICTED_FIELDS",
    "AccessDecision",
    "can",
    "decide",
    "require",
    "visible_fields",
]


# --------------------------------------------------------------------------- #
# Policy tables — таблицы политики                                            #
# --------------------------------------------------------------------------- #

#: The full universe of coarse-grained actions guarded by this policy.
ACTIONS: frozenset[str] = frozenset(
    {
        "read",
        "write",
        "merge",
        "delete",
        "curate",
        "export",
        "admin",
    }
)

#: The five known roles, in descending capability order.
ROLES: tuple[str, ...] = (
    "admin",
    "curator",
    "researcher",
    "analyst",
    "external_partner",
)

#: Field names considered *restricted* / internal — hidden from external partners
#: («служебные поля», §19.12): provenance, ACLs, internal notes and raw sources.
RESTRICTED_FIELDS: frozenset[str] = frozenset(
    {
        "internal_notes",
        "provenance",
        "acl",
        "owner_id",
        "raw_source",
    }
)

#: The single source of truth: ``role → frozenset[action]``. ``admin`` holds the
#: whole :data:`ACTIONS` universe; the rest are explicit subsets so that adding a
#: new action never silently grants it to a non-admin role.
ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "admin": frozenset(ACTIONS),
    "curator": frozenset({"read", "write", "merge", "curate", "export"}),
    "researcher": frozenset({"read", "write", "export"}),
    "analyst": frozenset({"read", "export"}),
    "external_partner": frozenset({"read"}),
}


# --------------------------------------------------------------------------- #
# Decision record — запись решения                                            #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class AccessDecision:
    """An immutable ``(role, action) → allowed`` verdict — решение доступа (§19.12).

    ``role`` and ``action`` are echoed back so a decision can be logged or passed
    around on its own, and ``allowed`` is the boolean outcome. The dataclass is
    frozen so a decision is a stable, hashable value object.
    """

    role: str
    action: str
    allowed: bool

    def as_dict(self) -> dict[str, Any]:
        """JSON-friendly view — ``{role, action, allowed}`` (§19.12)."""
        return {"role": self.role, "action": self.action, "allowed": self.allowed}


# --------------------------------------------------------------------------- #
# Queries + enforcement — запросы и принуждение                               #
# --------------------------------------------------------------------------- #


def can(role: str, action: str) -> bool:
    """Return whether ``role`` is granted ``action`` — проверка права (§19.12).

    An unknown role has *no* permissions (fail-closed): its lookup yields an empty
    set, so :func:`can` returns ``False`` rather than raising. Unknown actions are
    likewise simply absent from every role and return ``False``.
    """
    return action in ROLE_PERMISSIONS.get(role, frozenset())


def decide(role: str, action: str) -> AccessDecision:
    """Build an :class:`AccessDecision` for ``(role, action)`` — решение (§19.12)."""
    return AccessDecision(role=role, action=action, allowed=can(role, action))


def require(role: str, action: str) -> None:
    """Enforce ``action`` for ``role`` — принудительная проверка (§19.12).

    Returns ``None`` when the action is permitted; otherwise raises
    :class:`PermissionError` with a stable, human-readable message. This is the
    guard privileged call sites should use instead of a bare :func:`can` check.
    """
    if not can(role, action):
        raise PermissionError(f"role {role!r} may not perform action {action!r}")


def visible_fields(role: str, fields: Iterable[str] | None = None) -> set[str]:
    """The fields ``role`` may see — видимые поля (§19.12).

    With no ``fields`` argument the *policy* view is returned: every known field
    for a privileged role, or all known fields minus :data:`RESTRICTED_FIELDS`
    for ``external_partner`` (and for unknown roles, which are treated as external
    / fail-closed). When ``fields`` is given, that concrete set is filtered the
    same way, so callers can project an actual record.

    The "known field" universe used for the no-argument case is
    :data:`RESTRICTED_FIELDS` (there are no non-restricted fixed fields to
    enumerate), so a privileged role sees exactly those and an external partner
    sees none of them.
    """
    universe = set(RESTRICTED_FIELDS) if fields is None else set(fields)
    if _hides_restricted(role):
        return universe - RESTRICTED_FIELDS
    return universe


def _hides_restricted(role: str) -> bool:
    """Whether restricted fields are hidden from ``role`` — скрытие полей (§19.12).

    ``external_partner`` always hides them; any unknown role is treated the same
    way (fail-closed). Every other known role sees restricted fields.
    """
    return role == "external_partner" or role not in ROLE_PERMISSIONS
