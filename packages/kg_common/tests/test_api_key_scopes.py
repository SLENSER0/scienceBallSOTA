"""Tests for API-key scope → permission resolution (§19.2 authentication).

Hand-checkable cases over a fixed universe
``{chat:read, chat:write, graph:read}`` covering plain scopes, ``domain:*`` and
``*`` wildcards, single-permission checks, and required-set resolution.
"""

from __future__ import annotations

from kg_common.security.api_key_scopes import (
    ScopeResolution,
    expand_scopes,
    key_can,
    resolve,
)

U: frozenset[str] = frozenset({"chat:read", "chat:write", "graph:read"})


def test_expand_plain_scope_is_identity() -> None:
    """(1) A plain in-universe scope expands to itself only."""
    assert expand_scopes({"chat:read"}, U) == frozenset({"chat:read"})


def test_expand_domain_wildcard() -> None:
    """(2) ``chat:*`` expands to every ``chat:`` permission in the universe."""
    assert expand_scopes({"chat:*"}, U) == frozenset({"chat:read", "chat:write"})


def test_expand_full_wildcard() -> None:
    """(3) ``*`` expands to the whole universe."""
    assert expand_scopes({"*"}, U) == U


def test_key_can_denies_unheld_permission() -> None:
    """(4) chat:read alone cannot chat:write."""
    assert key_can({"chat:read"}, "chat:write", U) is False


def test_key_can_via_domain_wildcard() -> None:
    """(5) chat:* grants chat:write."""
    assert key_can({"chat:*"}, "chat:write", U) is True


def test_resolve_partial_denies_missing() -> None:
    """(6) chat:read against {read, write} → denied=(write,), granted={read}."""
    res = resolve({"chat:read"}, {"chat:read", "chat:write"}, U)
    assert isinstance(res, ScopeResolution)
    assert res.denied == ("chat:write",)
    assert res.granted == frozenset({"chat:read"})
    assert res.ok is False


def test_resolve_wildcard_grants_all() -> None:
    """(7) chat:* against {chat:write} → nothing denied."""
    res = resolve({"chat:*"}, {"chat:write"}, U)
    assert res.denied == ()
    assert res.granted == frozenset({"chat:write"})
    assert res.ok is True


def test_unknown_scope_grants_nothing() -> None:
    """A scope naming a permission outside the universe contributes nothing."""
    assert expand_scopes({"admin:root", "billing:*"}, U) == frozenset()


def test_empty_scopes_grant_nothing() -> None:
    """No scopes → no permissions, and every required perm is denied in order."""
    res = resolve([], ["graph:read", "chat:read"], U)
    assert res.granted == frozenset()
    assert res.denied == ("graph:read", "chat:read")


def test_resolve_dedupes_required_preserving_order() -> None:
    """Duplicate required permissions collapse to their first occurrence."""
    res = resolve({"chat:read"}, ["chat:write", "chat:write", "graph:read"], U)
    assert res.denied == ("chat:write", "graph:read")


def test_resolution_as_dict_is_log_safe() -> None:
    """as_dict yields sorted, JSON-friendly primitives."""
    res = resolve({"chat:read"}, {"chat:write", "chat:read"}, U)
    assert res.as_dict() == {
        "granted": ["chat:read"],
        "denied": ["chat:write"],
        "ok": False,
    }
