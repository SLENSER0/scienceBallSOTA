"""Tests for offline breached-password detection (§19.2 Auth).

Hand-checkable assertions over :mod:`kg_common.security.password_breach_check`:
the SHA-1 k-anonymity split, the range/blocklist/clean verdicts, and the
``BreachResult.as_dict()`` round-trip. No network I/O «без сети».
"""

from __future__ import annotations

import hashlib

from kg_common.security.password_breach_check import (
    COMMON_PASSWORDS,
    SOURCE_BLOCKLIST,
    SOURCE_CLEAN,
    SOURCE_RANGE,
    BreachResult,
    check_password,
    is_common,
    sha1_prefix,
)

_HEX_UPPER = set("0123456789ABCDEF")


def test_sha1_prefix_known_value_and_lengths() -> None:
    """'password' → prefix '5BAA6'; parts have lengths 5 and 35 (assertion 1)."""
    prefix, suffix = sha1_prefix("password")
    assert prefix == "5BAA6"
    assert len(prefix) == 5
    assert len(suffix) == 35


def test_sha1_prefix_full_digest_is_uppercase_hex() -> None:
    """prefix+suffix has length 40 and is uppercase hex (assertion 2)."""
    prefix, suffix = sha1_prefix("hunter2")
    full = prefix + suffix
    assert len(full) == 40
    assert set(full) <= _HEX_UPPER
    # Cross-check against a fresh SHA-1 computed independently.
    assert full == hashlib.sha1(b"hunter2").hexdigest().upper()


def test_range_hit_returns_breached_with_count() -> None:
    """A matching suffix → breached True, count 42, source 'range' (assertion 3)."""
    _prefix, suffix = sha1_prefix("correcthorse")
    result = check_password("correcthorse", {suffix: 42})
    assert result.breached is True
    assert result.count == 42
    assert result.source == SOURCE_RANGE


def test_range_miss_returns_clean() -> None:
    """Suffix absent from the mapping → breached False, count 0, 'clean' (assertion 4)."""
    result = check_password("correcthorse", {"DEADBEEF" * 4 + "DEA": 7})
    assert result.breached is False
    assert result.count == 0
    assert result.source == SOURCE_CLEAN


def test_is_common_true_for_blocklisted() -> None:
    """'password' is in the local blocklist (assertion 5)."""
    assert is_common("password") is True
    assert "password" in COMMON_PASSWORDS


def test_blocklist_short_circuits_before_range() -> None:
    """'password' with empty mapping → breached True, source 'blocklist' (assertion 6)."""
    result = check_password("password", {})
    assert result.breached is True
    assert result.source == SOURCE_BLOCKLIST
    assert result.count == 0


def test_blocklist_wins_even_when_suffix_present() -> None:
    """Blocklist short-circuits even if the suffix would also match the range."""
    _prefix, suffix = sha1_prefix("password")
    result = check_password("password", {suffix: 999})
    assert result.source == SOURCE_BLOCKLIST


def test_strong_password_empty_mapping_is_clean() -> None:
    """A strong non-blocklisted password with empty mapping → 'clean' (assertion 7)."""
    strong = "Tr0ub4dour&3-Xq9zL!"
    assert is_common(strong) is False
    result = check_password(strong, {})
    assert result.breached is False
    assert result.count == 0
    assert result.source == SOURCE_CLEAN


def test_as_dict_round_trips_count_and_source() -> None:
    """as_dict() carries breached, count and source verbatim (assertion 8)."""
    result = BreachResult(breached=True, count=123, source=SOURCE_RANGE)
    d = result.as_dict()
    assert d == {"breached": True, "count": 123, "source": SOURCE_RANGE}
    assert d["count"] == 123
    assert d["source"] == SOURCE_RANGE


def test_is_common_is_case_insensitive() -> None:
    """The blocklist match ignores case «без учёта регистра»."""
    assert is_common("PASSWORD") is True
    assert check_password("PaSsWoRd", {}).source == SOURCE_BLOCKLIST
