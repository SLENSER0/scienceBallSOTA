"""Tests for retention policy — тесты политики хранения (§10.11)."""

from __future__ import annotations

from kg_common.metadata.retention_policy import (
    DEFAULT_POLICIES,
    RetentionPolicy,
    expiry_day,
    is_expired,
    policy_for,
)


def test_audit_policy_is_keep_forever() -> None:
    audit = policy_for("audit")
    assert audit is not None
    assert audit.retain_days == 0
    assert audit.store == "kg-audit"
    assert is_expired(audit, 9999) is False
    assert expiry_day(audit, 5) is None


def test_finite_policy_expiry_boundary() -> None:
    p = RetentionPolicy("raw", 30, "kg-raw")
    assert is_expired(p, 31) is True
    assert is_expired(p, 30) is False
    assert is_expired(p, 29) is False
    assert expiry_day(p, 10) == 40
    assert expiry_day(p, 0) == 30


def test_default_policies_membership_and_stores() -> None:
    assert "raw" in DEFAULT_POLICIES
    assert "parsed" in DEFAULT_POLICIES
    assert "audit" in DEFAULT_POLICIES
    assert DEFAULT_POLICIES["raw"].store == "kg-raw"
    assert DEFAULT_POLICIES["parsed"].store == "kg-parsed"
    assert DEFAULT_POLICIES["audit"].store == "kg-audit"


def test_policy_for_unknown_returns_none() -> None:
    assert policy_for("unknown") is None


def test_policy_for_matches_default_policies() -> None:
    raw = policy_for("raw")
    assert raw is DEFAULT_POLICIES["raw"]
    assert raw is not None
    assert raw.source_type == "raw"
    assert raw.retain_days == 30


def test_as_dict_round_trip_shape() -> None:
    p = RetentionPolicy("raw", 30, "kg-raw")
    assert p.as_dict() == {
        "source_type": "raw",
        "retain_days": 30,
        "store": "kg-raw",
    }


def test_policy_is_frozen() -> None:
    import dataclasses

    p = RetentionPolicy("raw", 30, "kg-raw")
    try:
        p.retain_days = 99  # type: ignore[misc]
    except dataclasses.FrozenInstanceError:
        pass
    else:  # pragma: no cover - guard against non-frozen regression
        raise AssertionError("RetentionPolicy must be frozen")


def test_parsed_policy_finite_expiry() -> None:
    parsed = policy_for("parsed")
    assert parsed is not None
    assert parsed.retain_days == 90
    assert is_expired(parsed, 91) is True
    assert is_expired(parsed, 90) is False
    assert expiry_day(parsed, 1) == 91
