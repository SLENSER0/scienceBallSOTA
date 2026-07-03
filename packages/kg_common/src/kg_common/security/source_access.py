"""Source-level access decision and row filtering (§19.3 access policy).

Deny-by-default authorization for knowledge sources («доступ запрещён по
умолчанию»). A :class:`Principal` (the acting user, their roles and lab
memberships) is checked against a :class:`SourceAcl` (per-source access
policy) by :func:`can_access_source`. Supported policies:

* ``public`` — accessible to any principal («публичный источник виден всем»).
* ``private`` — only the owner or an ``admin`` role.
* ``lab_restricted`` — owner, ``admin``, or a principal whose labs intersect
  the source's ``allowed_lab_ids``.

Any unknown or empty ``access_policy`` falls back to *private* semantics, so a
misconfigured source is denied to every non-admin («неизвестная политика —
запрещаем»). :func:`filter_sources` keeps only the accessible ACLs, preserving
input order. Pure-python, no third-party dependency.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

# Role that bypasses per-source checks («роль администратора»).
_ADMIN_ROLE = "admin"

# Access policies with explicit handling; everything else -> private semantics.
_POLICY_PUBLIC = "public"
_POLICY_PRIVATE = "private"
_POLICY_LAB_RESTRICTED = "lab_restricted"


@dataclass(frozen=True, slots=True)
class Principal:
    """Acting user with their roles and lab memberships («субъект доступа»)."""

    user_id: str
    roles: frozenset[str] = field(default_factory=frozenset)
    labs: frozenset[str] = field(default_factory=frozenset)

    def as_dict(self) -> dict[str, Any]:
        """Serialise to a plain dict with sorted, list-typed sets («в словарь»)."""
        return {
            "user_id": self.user_id,
            "roles": sorted(self.roles),
            "labs": sorted(self.labs),
        }


@dataclass(frozen=True, slots=True)
class SourceAcl:
    """Per-source access control entry («список доступа источника»)."""

    source_id: str
    access_policy: str
    owner_id: str | None = None
    allowed_lab_ids: frozenset[str] = field(default_factory=frozenset)

    def as_dict(self) -> dict[str, Any]:
        """Serialise to a plain dict with sorted lab ids («в словарь»)."""
        return {
            "source_id": self.source_id,
            "access_policy": self.access_policy,
            "owner_id": self.owner_id,
            "allowed_lab_ids": sorted(self.allowed_lab_ids),
        }


def _is_admin(principal: Principal) -> bool:
    """True if the principal holds the admin role («является админом»)."""
    return _ADMIN_ROLE in principal.roles


def _is_owner(principal: Principal, acl: SourceAcl) -> bool:
    """True if the principal owns the source («является владельцем»)."""
    return acl.owner_id is not None and acl.owner_id == principal.user_id


def can_access_source(principal: Principal, acl: SourceAcl) -> bool:
    """Decide whether ``principal`` may access the source described by ``acl``.

    Deny-by-default («запрет по умолчанию»): only the rules below grant access.
    """
    if acl.access_policy == _POLICY_PUBLIC:
        return True
    # Owner and admin always pass for private / lab_restricted / unknown.
    if _is_owner(principal, acl) or _is_admin(principal):
        return True
    if acl.access_policy == _POLICY_LAB_RESTRICTED:
        return bool(principal.labs & acl.allowed_lab_ids)
    # private, empty or unknown policy -> denied for non-owner, non-admin.
    return False


def filter_sources(principal: Principal, acls: Iterable[SourceAcl]) -> tuple[SourceAcl, ...]:
    """Keep only ACLs accessible to ``principal``, preserving order («фильтр»)."""
    return tuple(acl for acl in acls if can_access_source(principal, acl))
