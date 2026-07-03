"""Tests for stdlib PBKDF2 password hashing (§19.2 auth)."""

from __future__ import annotations

import base64

from kg_common.security.password_hash import (
    HashParams,
    hash_password,
    needs_rehash,
    verify_password,
)


def test_encoded_shape_has_four_fields() -> None:
    parts = hash_password("pw").split("$")
    assert len(parts) == 4
    assert parts[0] == "pbkdf2_sha256"


def test_verify_accepts_matching_password() -> None:
    assert verify_password("pw", hash_password("pw")) is True


def test_verify_rejects_wrong_password() -> None:
    h = hash_password("pw")
    assert verify_password("wrong", h) is False


def test_random_salt_makes_hashes_differ() -> None:
    assert hash_password("pw") != hash_password("pw")


def test_needs_rehash_true_for_weaker_iterations() -> None:
    weak = hash_password("pw", HashParams(iterations=1_000))
    assert needs_rehash(weak, HashParams(iterations=200_000)) is True


def test_needs_rehash_false_for_matching_params() -> None:
    params = HashParams(iterations=200_000, salt_bytes=16)
    h = hash_password("pw", params)
    assert needs_rehash(h, params) is False


def test_tampered_hash_segment_fails_verify() -> None:
    h = hash_password("pw")
    algorithm, iterations, salt_b64, hash_b64 = h.split("$")
    flipped = "A" if hash_b64[-1] != "A" else "B"
    tampered = "$".join((algorithm, iterations, salt_b64, hash_b64[:-1] + flipped))
    assert verify_password("pw", tampered) is False


def test_decoded_salt_length_matches_params() -> None:
    params = HashParams(salt_bytes=16)
    salt_b64 = hash_password("pw", params).split("$")[2]
    assert len(base64.b64decode(salt_b64)) == params.salt_bytes
