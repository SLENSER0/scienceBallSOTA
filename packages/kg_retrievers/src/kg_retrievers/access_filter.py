"""Retriever access-filter parameter builder (§19.3).

RU: Построитель параметров фильтра доступа для ретриверов (§19.3). По области
видимости пользователя (:class:`AccessScope`) и метаданным источников
(:class:`SourceMeta`) вычисляет множество видимых ``source_id`` и формирует
готовые параметры для Cypher (:func:`cypher_access_params`) и фильтр Qdrant
(:func:`qdrant_access_filter`). Политики доступа источника:

* ``public`` — виден любому аутентифицированному пользователю;
* ``lab_restricted`` — виден при пересечении лабораторий области с
  ``allowed_lab_ids`` источника либо владельцу;
* ``private`` — виден только владельцу (``owner_id``).

Администратор (``is_admin``) видит все источники, и Qdrant-фильтр для него пуст
(``{}`` == без ограничений).

EN: Access-filter parameter builder for retrievers (§19.3). Given a user's scope
(:class:`AccessScope`) and per-source metadata (:class:`SourceMeta`), it computes
the set of visible ``source_id`` values and emits ready-to-use parameters for
Cypher (:func:`cypher_access_params`) and a Qdrant must-clause filter
(:func:`qdrant_access_filter`). Source access policies:

* ``public`` — visible to any authenticated user;
* ``lab_restricted`` — visible when the scope's labs overlap the source's
  ``allowed_lab_ids`` or the caller is the owner;
* ``private`` — visible only to the owner (``owner_id``).

An admin (``is_admin``) sees every source, and their Qdrant filter is empty
(``{}`` meaning unrestricted).

Pure python — no store access. Kuzu note: custom node props are NOT queryable
columns; callers RETURN base columns and read policy/owner via ``get_node()``
before constructing :class:`SourceMeta`.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

# §19.3 access policies recognised by :func:`visible_source_ids`.
POLICY_PUBLIC = "public"
POLICY_LAB_RESTRICTED = "lab_restricted"
POLICY_PRIVATE = "private"

# Qdrant payload key holding a point's owning source id (§19.3).
QDRANT_SOURCE_KEY = "source_id"


@dataclass(frozen=True)
class AccessScope:
    """Frozen access scope of the requesting user (§19.3).

    ``user_id`` identifies the caller; ``labs`` are the lab ids they belong to;
    ``owned_source_ids`` are the sources they own; ``is_admin`` grants
    unrestricted visibility across all sources.
    """

    user_id: str
    labs: frozenset[str]
    owned_source_ids: frozenset[str]
    is_admin: bool

    def as_dict(self) -> dict[str, Any]:
        """Plain-dict projection for trace / round-trip (§19.3, house style)."""
        return {
            "user_id": self.user_id,
            "labs": sorted(self.labs),
            "owned_source_ids": sorted(self.owned_source_ids),
            "is_admin": self.is_admin,
        }


@dataclass(frozen=True)
class SourceMeta:
    """Frozen access metadata for a single source (§19.3).

    ``source_id`` is the source key; ``access_policy`` is one of ``public`` /
    ``lab_restricted`` / ``private``; ``allowed_lab_ids`` lists labs permitted
    under ``lab_restricted``; ``owner_id`` is the owning user id.
    """

    source_id: str
    access_policy: str
    allowed_lab_ids: frozenset[str]
    owner_id: str

    def as_dict(self) -> dict[str, Any]:
        """Plain-dict projection for trace / round-trip (§19.3, house style)."""
        return {
            "source_id": self.source_id,
            "access_policy": self.access_policy,
            "allowed_lab_ids": sorted(self.allowed_lab_ids),
            "owner_id": self.owner_id,
        }


def _is_owner(scope: AccessScope, source: SourceMeta) -> bool:
    """True if ``scope`` owns ``source`` by user id or explicit ownership set."""
    return scope.user_id == source.owner_id or source.source_id in scope.owned_source_ids


def _source_visible(scope: AccessScope, source: SourceMeta) -> bool:
    """Decide visibility of one ``source`` for ``scope`` per §19.3 policy rules."""
    if scope.is_admin:
        return True
    if source.access_policy == POLICY_PUBLIC:
        return True  # Any authenticated user may see public sources.
    if source.access_policy == POLICY_LAB_RESTRICTED:
        return bool(scope.labs & source.allowed_lab_ids) or _is_owner(scope, source)
    if source.access_policy == POLICY_PRIVATE:
        return _is_owner(scope, source)
    # Unknown policy -> fail closed: owner only.
    return _is_owner(scope, source)


def visible_source_ids(
    scope: AccessScope,
    sources: Iterable[SourceMeta],
) -> frozenset[str]:
    """Return the set of ``source_id`` values visible to ``scope`` (§19.3).

    Admins see every source id. Otherwise a source is visible when its policy
    permits the caller: ``public`` for all authenticated users, ``lab_restricted``
    on lab overlap or ownership, ``private`` for the owner only. An unknown policy
    fails closed to owner-only visibility.
    """
    return frozenset(s.source_id for s in sources if _source_visible(scope, s))


def cypher_access_params(
    scope: AccessScope,
    sources: Iterable[SourceMeta],
) -> dict[str, list[str]]:
    """Build deterministic Cypher access params for ``scope`` (§19.3).

    Returns ``{'allowed_source_ids': <sorted visible ids>, 'labs': <sorted labs>}``.
    Both lists are sorted so the produced query parameters are deterministic and
    cache-friendly.
    """
    return {
        "allowed_source_ids": sorted(visible_source_ids(scope, sources)),
        "labs": sorted(scope.labs),
    }


def qdrant_access_filter(
    scope: AccessScope,
    sources: Iterable[SourceMeta],
) -> dict[str, Any]:
    """Build a Qdrant filter restricting points to visible sources (§19.3).

    For an admin the filter is ``{}`` (unrestricted). Otherwise it is a single
    ``must`` clause matching ``source_id`` against the sorted visible ids via
    ``match.any``, so a point is returned only if its source is visible.
    """
    if scope.is_admin:
        return {}
    return {
        "must": [
            {
                "key": QDRANT_SOURCE_KEY,
                "match": {"any": sorted(visible_source_ids(scope, sources))},
            }
        ]
    }
