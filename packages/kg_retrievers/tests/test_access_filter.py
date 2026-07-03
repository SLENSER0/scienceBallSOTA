"""Tests for §19.3 retriever access-filter param builder (hand-checkable)."""

from __future__ import annotations

from kg_retrievers.access_filter import (
    AccessScope,
    SourceMeta,
    cypher_access_params,
    qdrant_access_filter,
    visible_source_ids,
)


def _pub(source_id: str = "pub1", owner: str = "alice") -> SourceMeta:
    return SourceMeta(source_id, "public", frozenset(), owner)


def _lab(
    source_id: str = "lab1",
    labs: frozenset[str] = frozenset({"lab-a"}),
    owner: str = "alice",
) -> SourceMeta:
    return SourceMeta(source_id, "lab_restricted", labs, owner)


def _priv(source_id: str = "priv1", owner: str = "alice") -> SourceMeta:
    return SourceMeta(source_id, "private", frozenset(), owner)


def _scope(
    user_id: str = "bob",
    labs: frozenset[str] = frozenset(),
    owned: frozenset[str] = frozenset(),
    is_admin: bool = False,
) -> AccessScope:
    return AccessScope(user_id, labs, owned, is_admin)


# (1) admin sees every source id and qdrant_access_filter == {}.
def test_admin_sees_all_and_empty_qdrant_filter() -> None:
    sources = [_pub("s1"), _lab("s2"), _priv("s3")]
    admin = _scope("root", is_admin=True)
    assert visible_source_ids(admin, sources) == frozenset({"s1", "s2", "s3"})
    assert qdrant_access_filter(admin, sources) == {}


# (2) a public source is visible to a non-owner different-lab scope.
def test_public_visible_to_non_owner_different_lab() -> None:
    src = _pub("pub1", owner="alice")
    bob = _scope("bob", labs=frozenset({"lab-z"}))
    assert "pub1" in visible_source_ids(bob, [src])


# (3) lab_restricted visible only when scope.labs intersects allowed_lab_ids.
def test_lab_restricted_requires_lab_overlap() -> None:
    src = _lab("lab1", labs=frozenset({"lab-a"}), owner="alice")
    in_lab = _scope("bob", labs=frozenset({"lab-a", "lab-b"}))
    out_lab = _scope("carol", labs=frozenset({"lab-x"}))
    assert "lab1" in visible_source_ids(in_lab, [src])
    assert "lab1" not in visible_source_ids(out_lab, [src])


def test_lab_restricted_owner_sees_without_lab_overlap() -> None:
    src = _lab("lab1", labs=frozenset({"lab-a"}), owner="alice")
    owner = _scope("alice", labs=frozenset({"lab-x"}))
    assert "lab1" in visible_source_ids(owner, [src])


# (4) private visible only to owner_id.
def test_private_visible_only_to_owner() -> None:
    src = _priv("priv1", owner="alice")
    other = _scope("bob", labs=frozenset({"lab-a"}))
    assert "priv1" not in visible_source_ids(other, [src])


# (7) owner sees their own private source.
def test_owner_sees_own_private_source() -> None:
    src = _priv("priv1", owner="alice")
    owner = _scope("alice")
    assert "priv1" in visible_source_ids(owner, [src])


def test_private_visible_via_owned_source_ids() -> None:
    # Ownership can also be asserted via the scope's owned_source_ids set.
    src = _priv("priv1", owner="alice")
    delegate = _scope("bob", owned=frozenset({"priv1"}))
    assert "priv1" in visible_source_ids(delegate, [src])


# (5) cypher_access_params['allowed_source_ids'] is sorted and deterministic.
def test_cypher_params_allowed_ids_sorted_deterministic() -> None:
    sources = [_pub("z9"), _pub("a1"), _pub("m5")]
    scope = _scope("bob")
    params = cypher_access_params(scope, sources)
    assert params["allowed_source_ids"] == ["a1", "m5", "z9"]
    # Deterministic across re-invocation regardless of input order.
    shuffled = [_pub("m5"), _pub("z9"), _pub("a1")]
    assert cypher_access_params(scope, shuffled) == params


def test_cypher_params_labs_sorted() -> None:
    scope = _scope("bob", labs=frozenset({"lab-c", "lab-a", "lab-b"}))
    params = cypher_access_params(scope, [_pub("s1")])
    assert params["labs"] == ["lab-a", "lab-b", "lab-c"]


def test_cypher_params_excludes_invisible_sources() -> None:
    sources = [_pub("p1"), _priv("secret", owner="alice")]
    bob = _scope("bob")
    params = cypher_access_params(bob, sources)
    assert params["allowed_source_ids"] == ["p1"]


# (6) qdrant filter's match.any equals sorted visible ids.
def test_qdrant_filter_match_any_equals_sorted_visible_ids() -> None:
    sources = [_pub("z9"), _pub("a1"), _lab("m5", labs=frozenset({"lab-a"}))]
    bob = _scope("bob", labs=frozenset({"lab-a"}))
    flt = qdrant_access_filter(bob, sources)
    clause = flt["must"][0]
    assert clause["key"] == "source_id"
    assert clause["match"]["any"] == ["a1", "m5", "z9"]


def test_qdrant_filter_excludes_invisible_sources() -> None:
    sources = [_pub("p1"), _priv("secret", owner="alice"), _lab("l1", frozenset({"x"}))]
    bob = _scope("bob", labs=frozenset({"y"}))
    flt = qdrant_access_filter(bob, sources)
    assert flt["must"][0]["match"]["any"] == ["p1"]


def test_qdrant_filter_empty_visible_yields_empty_any() -> None:
    src = _priv("secret", owner="alice")
    bob = _scope("bob")
    flt = qdrant_access_filter(bob, [src])
    assert flt["must"][0]["match"]["any"] == []


def test_as_dict_scope_round_trip() -> None:
    scope = AccessScope("bob", frozenset({"lab-b", "lab-a"}), frozenset({"s2", "s1"}), False)
    d = scope.as_dict()
    assert d == {
        "user_id": "bob",
        "labs": ["lab-a", "lab-b"],
        "owned_source_ids": ["s1", "s2"],
        "is_admin": False,
    }


def test_as_dict_source_round_trip() -> None:
    src = SourceMeta("s1", "lab_restricted", frozenset({"lab-b", "lab-a"}), "alice")
    d = src.as_dict()
    assert d == {
        "source_id": "s1",
        "access_policy": "lab_restricted",
        "allowed_lab_ids": ["lab-a", "lab-b"],
        "owner_id": "alice",
    }


def test_scope_and_source_are_frozen() -> None:
    scope = _scope("bob")
    src = _pub("s1")
    for obj, attr, val in [(scope, "user_id", "x"), (src, "source_id", "y")]:
        try:
            setattr(obj, attr, val)  # type: ignore[misc]
        except AttributeError:
            pass
        else:  # pragma: no cover - frozen dataclasses must reject assignment
            raise AssertionError("dataclass must be frozen")


def test_unknown_policy_fails_closed_to_owner() -> None:
    src = SourceMeta("s1", "weird_policy", frozenset({"lab-a"}), "alice")
    owner = _scope("alice", labs=frozenset({"lab-a"}))
    stranger = _scope("bob", labs=frozenset({"lab-a"}))
    assert "s1" in visible_source_ids(owner, [src])
    assert "s1" not in visible_source_ids(stranger, [src])
