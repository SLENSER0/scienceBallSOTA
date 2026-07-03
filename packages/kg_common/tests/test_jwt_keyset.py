"""Tests for JWT signing keyset / kid rotation resolver (§19.2 auth)."""

from __future__ import annotations

import pytest

from kg_common.security.jwt_keyset import (
    JwtKeyset,
    KeyRef,
    active_signing_key,
    valid_kids,
    verification_key,
)


def _keyset() -> JwtKeyset:
    """k1 signs [0,100), k2 signs [50,200) — overlapping windows («перекрытие»)."""
    k1 = KeyRef(kid="k1", alg="RS256", not_before=0.0, not_after=100.0, is_signing=True)
    k2 = KeyRef(kid="k2", alg="RS256", not_before=50.0, not_after=200.0, is_signing=True)
    return JwtKeyset(keys=(k1, k2))


def test_active_signing_newer_wins_on_overlap() -> None:
    # At now=60 both windows cover it; the newer not_before (k2=50) wins.
    assert active_signing_key(_keyset(), 60).kid == "k2"


def test_active_signing_only_k1_in_early_window() -> None:
    # At now=10 only k1's window is open.
    assert active_signing_key(_keyset(), 10).kid == "k1"


def test_verification_key_hit_and_miss() -> None:
    ks = _keyset()
    got = verification_key(ks, "k1")
    assert got is not None
    assert got.kid == "k1"
    assert verification_key(ks, "nope") is None


def test_valid_kids_overlap() -> None:
    assert valid_kids(_keyset(), 60) == {"k1", "k2"}


def test_valid_kids_after_k1_expired() -> None:
    # At now=150 k1 (ends 100) is expired; only k2 remains.
    assert valid_kids(_keyset(), 150) == {"k2"}


def test_active_signing_none_raises() -> None:
    with pytest.raises(LookupError):
        active_signing_key(_keyset(), 500)


def test_roundtrip_from_dict() -> None:
    ks = _keyset()
    assert JwtKeyset.from_dict(ks.as_dict()) == ks


def test_keyref_roundtrip() -> None:
    k = KeyRef(kid="kx", alg="ES256", not_before=1.0, not_after=2.0, is_signing=False)
    assert KeyRef.from_dict(k.as_dict()) == k


def test_valid_kids_returns_frozenset() -> None:
    result = valid_kids(_keyset(), 60)
    assert isinstance(result, frozenset)


def test_non_signing_key_excluded_from_signing() -> None:
    # A verify-only key covering now must not be selected for signing.
    vonly = KeyRef(kid="v", alg="RS256", not_before=0.0, not_after=1000.0, is_signing=False)
    ks = JwtKeyset(keys=(vonly,))
    with pytest.raises(LookupError):
        active_signing_key(ks, 10)
    # ...but it is still a valid verification key and a valid kid.
    assert verification_key(ks, "v") is vonly
    assert valid_kids(ks, 10) == {"v"}


def test_half_open_window_boundaries() -> None:
    ks = _keyset()
    # not_after is exclusive: at now=100 k1 is no longer valid.
    assert "k1" not in valid_kids(ks, 100)
    # not_before is inclusive: at now=50 k2 becomes valid.
    assert "k2" in valid_kids(ks, 50)
