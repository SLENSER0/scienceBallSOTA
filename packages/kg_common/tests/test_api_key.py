"""Tests for API-key generation, hashing & verification (§19.2 auth)."""

from __future__ import annotations

import hashlib
from dataclasses import replace

from kg_common.security.api_key import (
    ApiKeyRecord,
    generate_api_key,
    is_expired,
    verify_api_key,
)

_RAW = b"\x00" * 20


def _mint() -> tuple[str, ApiKeyRecord]:
    return generate_api_key(_RAW, key_id="k1", scopes=frozenset({"graph:read"}), created_at=0.0)


def test_generate_is_deterministic() -> None:
    pt1, rec1 = _mint()
    pt2, rec2 = _mint()
    assert pt1 == pt2
    assert rec1.key_hash == rec2.key_hash


def test_plaintext_shape_and_hash() -> None:
    pt, rec = _mint()
    # base32 of 20 zero bytes is 32 uppercase 'A' characters, no padding.
    assert pt == "sk_" + "A" * 32
    assert pt.startswith("sk_")
    assert rec.key_hash == hashlib.sha256(pt.encode()).hexdigest()


def test_verify_accepts_matching_plaintext() -> None:
    pt, rec = _mint()
    assert verify_api_key(pt, rec) is True


def test_verify_rejects_tampered_plaintext() -> None:
    pt, rec = _mint()
    assert verify_api_key(pt + "x", rec) is False


def test_verify_rejects_key_from_different_entropy() -> None:
    _, rec = _mint()
    other_pt, _ = generate_api_key(
        b"\x01" * 20, key_id="k2", scopes=frozenset({"graph:read"}), created_at=0.0
    )
    assert verify_api_key(other_pt, rec) is False


def test_record_never_carries_plaintext() -> None:
    pt, rec = _mint()
    data = rec.as_dict()
    assert "plaintext" not in data
    assert pt not in str(data)


def test_scopes_preserved() -> None:
    _, rec = _mint()
    assert rec.scopes == {"graph:read"}


def test_is_expired_boundaries() -> None:
    _, rec = _mint()
    bounded = replace(rec, expires_at=100.0)
    assert is_expired(bounded, 50.0) is False
    assert is_expired(bounded, 150.0) is True
    # Exactly at the boundary is treated as expired.
    assert is_expired(bounded, 100.0) is True


def test_is_expired_none_never_expires() -> None:
    _, rec = _mint()
    assert rec.expires_at is None
    assert is_expired(rec, 1e18) is False
