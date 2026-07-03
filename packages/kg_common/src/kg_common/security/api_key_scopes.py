"""API-key scope → permission resolution (§19.2 authentication).

An :class:`~kg_common.security.api_key.ApiKeyRecord` carries a
:class:`frozenset` of *scope* strings, but the record itself never expands
wildcard scopes nor decides whether a key may perform a given action. This
module supplies that missing layer («разрешение областей доступа ключа»).

Scopes are matched against a caller-supplied *universe* — the full set of
fine-grained permissions the system recognises (e.g. ``chat:read``,
``chat:write``, ``graph:read``). Two wildcard forms are understood:

* ``"*"`` — the full universe («все права»).
* ``"<domain>:*"`` — every universe permission sharing the ``<domain>:``
  prefix (e.g. ``chat:*`` → ``chat:read`` + ``chat:write``).

A plain scope that is present in the universe expands to itself; a scope that
names a permission outside the universe simply contributes nothing, so an
unknown or stale scope can never grant an unrecognised permission
(«неизвестная область не даёт прав»).

* :func:`expand_scopes` — resolve raw scopes to concrete universe permissions.
* :func:`key_can` — does a key with these scopes hold ``perm``?
* :func:`resolve` — split a required set into granted vs. denied, returning a
  frozen :class:`ScopeResolution`.

Pure-python, no third-party dependency; every function is total and side-effect
free, which keeps the hand-checkable tests reproducible.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

_WILDCARD_ALL = "*"
_WILDCARD_SUFFIX = ":*"


@dataclass(frozen=True)
class ScopeResolution:
    """Outcome of checking required permissions against a key's scopes.

    :param granted: required permissions the key actually holds («предоставлено»).
    :param denied: required permissions the key lacks, in the caller's order and
        de-duplicated («отказано»); empty tuple means fully authorised.
    """

    granted: frozenset[str]
    denied: tuple[str, ...]

    @property
    def ok(self) -> bool:
        """True when nothing was denied («полный доступ»)."""
        return not self.denied

    def as_dict(self) -> dict[str, object]:
        """Return a serializable, log-safe view of this resolution."""
        return {
            "granted": sorted(self.granted),
            "denied": list(self.denied),
            "ok": self.ok,
        }


def expand_scopes(scopes: Iterable[str], universe: frozenset[str]) -> frozenset[str]:
    """Expand *scopes* to the concrete permissions they grant within *universe*.

    ``"*"`` yields the whole *universe*; a ``"<domain>:*"`` scope yields every
    universe permission with that ``<domain>:`` prefix; any other scope grants
    itself only if it is a member of *universe*.

    :param scopes: raw scope strings held by a key («области доступа ключа»).
    :param universe: full set of recognised fine-grained permissions.
    :returns: the granted permissions, always a subset of *universe*.
    """
    granted: set[str] = set()
    for scope in scopes:
        if scope == _WILDCARD_ALL:
            return frozenset(universe)
        if scope.endswith(_WILDCARD_SUFFIX):
            prefix = scope[: -len(_WILDCARD_ALL)]  # keep trailing ':' → "chat:"
            granted.update(perm for perm in universe if perm.startswith(prefix))
        elif scope in universe:
            granted.add(scope)
    return frozenset(granted)


def key_can(scopes: Iterable[str], perm: str, universe: frozenset[str]) -> bool:
    """Return whether a key holding *scopes* is granted *perm* within *universe*.

    :param scopes: raw scope strings held by the key.
    :param perm: the fine-grained permission being checked.
    :param universe: full set of recognised permissions.
    :returns: ``True`` iff *perm* is among the expanded scopes.
    """
    return perm in expand_scopes(scopes, universe)


def resolve(
    scopes: Iterable[str],
    required: Iterable[str],
    universe: frozenset[str],
) -> ScopeResolution:
    """Split *required* into granted vs. denied for a key holding *scopes*.

    Iteration order of *required* is preserved in :attr:`ScopeResolution.denied`
    and duplicates are dropped, so callers get a stable, minimal denial list.

    :param scopes: raw scope strings held by the key.
    :param required: permissions the current action demands («требуемые права»).
    :param universe: full set of recognised permissions.
    :returns: a frozen :class:`ScopeResolution`.
    """
    effective = expand_scopes(scopes, universe)
    granted: set[str] = set()
    denied: list[str] = []
    seen: set[str] = set()
    for perm in required:
        if perm in seen:
            continue
        seen.add(perm)
        if perm in effective:
            granted.add(perm)
        else:
            denied.append(perm)
    return ScopeResolution(granted=frozenset(granted), denied=tuple(denied))
