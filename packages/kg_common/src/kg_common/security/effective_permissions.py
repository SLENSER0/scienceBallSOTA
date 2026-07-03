"""Multi-role effective permissions and RBAC invariants (§19.1 authorization).

Fine-grained scope model («модель ролей»): each role maps to a
:class:`frozenset` of scope strings (e.g. ``chat:read``, ``entities:merge``).
A principal usually holds several roles at once, so their *effective*
permission set is the **union** of the scopes granted by every known role
(«эффективные права — объединение прав всех ролей»).

* :data:`ROLE_MATRIX` — the single source of truth mapping role -> scopes.
* :func:`effective_permissions` — union over the given roles; an unknown role
  contributes nothing («неизвестная роль игнорируется»).
* :func:`has_permission` — membership check against the effective set.
* :func:`write_scopes` — every mutating scope across all roles (suffixes such
  as ``:write`` / ``:merge`` / ``:upload`` / ``:review`` / ``:delete`` /
  ``:approve`` / ``:manage`` / ``:ingest``).
* :func:`every_permission_assigned` — invariant: each scope is granted to at
  least one role («каждое право закреплено хотя бы за одной ролью»).
* :func:`viewer_has_no_write` — invariant: the read-only ``viewer`` role holds
  no mutating scope («роль viewer — только чтение»).

Pure-python, no third-party dependency; the matrix is frozen at import time.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

# Suffixes that mark a scope as *mutating* («изменяющие права — суффиксы»).
_WRITE_SUFFIXES: frozenset[str] = frozenset(
    {
        ":write",
        ":merge",
        ":upload",
        ":review",
        ":delete",
        ":approve",
        ":manage",
        ":ingest",
    }
)

# Single source of truth: role -> granted fine scopes («матрица ролей»).
ROLE_MATRIX: Mapping[str, frozenset[str]] = {
    "admin": frozenset(
        {
            "chat:read",
            "chat:write",
            "graph:read",
            "graph:write",
            "entities:read",
            "entities:merge",
            "entities:delete",
            "sources:read",
            "sources:upload",
            "sources:ingest",
            "review:read",
            "review:review",
            "review:approve",
            "users:manage",
        }
    ),
    "curator": frozenset(
        {
            "chat:read",
            "chat:write",
            "graph:read",
            "graph:write",
            "entities:read",
            "entities:merge",
            "sources:read",
            "sources:upload",
            "review:read",
            "review:review",
            "review:approve",
        }
    ),
    "researcher": frozenset(
        {
            "chat:read",
            "chat:write",
            "graph:read",
            "entities:read",
            "sources:read",
            "sources:upload",
            "review:read",
        }
    ),
    "viewer": frozenset(
        {
            "chat:read",
            "graph:read",
            "entities:read",
            "sources:read",
            "review:read",
        }
    ),
    "ingest_operator": frozenset(
        {
            "sources:read",
            "sources:upload",
            "sources:ingest",
            "graph:read",
        }
    ),
    "service": frozenset(
        {
            "chat:read",
            "graph:read",
            "graph:write",
            "entities:read",
            "sources:read",
            "sources:ingest",
        }
    ),
}


@dataclass(frozen=True, slots=True)
class RoleGrant:
    """A single role together with the scopes it grants («грант роли»)."""

    role: str
    permissions: frozenset[str]

    def as_dict(self) -> dict[str, Any]:
        """Serialise to a plain dict with sorted scopes («в словарь»)."""
        return {"role": self.role, "permissions": sorted(self.permissions)}


def role_grant(role: str) -> RoleGrant:
    """Build a :class:`RoleGrant` for ``role`` («грант для роли»).

    An unknown role yields an empty scope set rather than raising, so callers
    can compose grants defensively («неизвестная роль — пустой набор»).
    """
    return RoleGrant(role=role, permissions=ROLE_MATRIX.get(role, frozenset()))


def effective_permissions(roles: Iterable[str]) -> frozenset[str]:
    """Union of scopes granted by every *known* role in ``roles`` («объединение»).

    Unknown roles contribute nothing to the union («неизвестная роль — ничего»).
    """
    granted: set[str] = set()
    for role in roles:
        granted |= ROLE_MATRIX.get(role, frozenset())
    return frozenset(granted)


def has_permission(roles: Iterable[str], perm: str) -> bool:
    """True if ``perm`` is in the effective set of ``roles`` («есть право»)."""
    return perm in effective_permissions(roles)


def _is_write_scope(scope: str) -> bool:
    """True if ``scope`` ends with any mutating suffix («изменяющий scope»)."""
    return any(scope.endswith(suffix) for suffix in _WRITE_SUFFIXES)


def all_scopes() -> frozenset[str]:
    """Every scope assigned to any role in the matrix («все права»)."""
    return effective_permissions(ROLE_MATRIX.keys())


def write_scopes() -> frozenset[str]:
    """All mutating scopes across every role («все изменяющие права»)."""
    return frozenset(scope for scope in all_scopes() if _is_write_scope(scope))


def every_permission_assigned() -> bool:
    """Invariant: each known scope is granted to >=1 role («каждое право закреплено»).

    Trivially true by construction (:func:`all_scopes` is derived from the
    matrix), but kept as an explicit, hand-checkable guard against a role whose
    scopes silently drop out of the union.
    """
    assigned = all_scopes()
    return all(any(scope in perms for perms in ROLE_MATRIX.values()) for scope in assigned)


def viewer_has_no_write(role: str = "viewer") -> bool:
    """Invariant: ``role`` holds no mutating scope («роль без права записи»)."""
    return not (ROLE_MATRIX.get(role, frozenset()) & write_scopes())
