"""Role → source-access clearance — уровень допуска роли к источникам (§17.1/§19.3).

Complements two existing primitives:

* :mod:`kg_common.security.source_access` decides *per-source* access for a
  :class:`~kg_common.security.source_access.Principal` (owner / admin /
  lab-restricted);
* :mod:`kg_common.governance_tags` defines the ``access`` facet whose values —
  ``public`` / ``internal`` / ``restricted`` — tag how sensitive a fact/source is.

What was missing is the bridge: **which access levels a role is cleared to see**.
This module is that policy, so the graph/retrieval layer can drop any fact whose
source is above the caller's clearance — «модель графа знает, что роль не имеет
доступа к источнику, и не отдаёт из него данные».

The clearance ladder (fail-closed — an unknown role sees only ``public``):

* ``external_partner`` → public only;
* ``analyst`` / ``researcher`` → public + internal;
* ``curator`` / ``project_manager`` / ``admin`` → public + internal + restricted.

Pure, side-effect free.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from kg_common.security.source_access import Principal

# Sensitivity rank of each access level (higher = more sensitive). ``commercial_secret``
# is a legacy synonym for the top tier, kept so old data still filters correctly.
ACCESS_RANK: dict[str, int] = {
    "public": 0,
    "internal": 1,
    "restricted": 2,
    "commercial_secret": 2,
}

# Role → the HIGHEST access level it may read. Unknown roles fall to ``public``.
ROLE_MAX_CLEARANCE: dict[str, str] = {
    "external_partner": "public",
    "analyst": "internal",
    "researcher": "internal",
    "curator": "restricted",
    "project_manager": "restricted",
    "admin": "restricted",
}
_DEFAULT_MAX = "public"

# Node/row fields that may carry the source's sensitivity, checked in order.
_LEVEL_KEYS = ("confidentiality_level", "access_level")


def allowed_access_levels(role: str) -> frozenset[str]:
    """The access-level values ``role`` is cleared to read (fail-closed)."""
    ceiling = ACCESS_RANK[ROLE_MAX_CLEARANCE.get(role, _DEFAULT_MAX)]
    return frozenset(lvl for lvl, rank in ACCESS_RANK.items() if rank <= ceiling)


def can_view(role: str, level: Any) -> bool:
    """Whether ``role`` may see data whose source access level is ``level``.

    A missing / empty level is treated as ``public`` (visible) — most graph nodes
    carry no sensitivity tag. A **known** level must be within the role's clearance.
    An **unknown, non-empty** label is treated as top-tier restricted (fail-closed),
    so a mis-tagged source is hidden from anyone below full clearance.
    """
    if not level:
        return True
    lvl = str(level).strip().lower()
    if lvl not in ACCESS_RANK:
        return ACCESS_RANK[ROLE_MAX_CLEARANCE.get(role, _DEFAULT_MAX)] >= ACCESS_RANK["restricted"]
    return lvl in allowed_access_levels(role)


def row_level(row: Mapping[str, Any]) -> Any:
    """Read a row's source access level from either supported field."""
    for k in _LEVEL_KEYS:
        v = row.get(k)
        if v:
            return v
    return None


def filter_by_clearance(
    role: str, rows: Iterable[Mapping[str, Any]], *, key: str | None = None
) -> list[Any]:
    """Keep only the rows ``role`` is cleared to see (order preserved).

    ``key`` overrides which field holds the access level; otherwise both
    ``confidentiality_level`` and ``access_level`` are checked. Rows the caller may
    not see are dropped entirely, so downstream (answer synthesis, search results)
    never even observes a disallowed source — «данные из запрещённого источника не
    попадают в ответ».
    """
    out: list[Any] = []
    for r in rows:
        level = r.get(key) if key else row_level(r)
        if can_view(role, level):
            out.append(r)
    return out


def principal_from(user_id: str, role: str, labs: Iterable[str] = ()) -> Principal:
    """Build a :class:`Principal` for per-source ACL checks from the request identity."""
    return Principal(user_id=user_id, roles=frozenset({role}), labs=frozenset(labs))
