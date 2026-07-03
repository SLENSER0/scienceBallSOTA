"""Tests for the data-retention policy resolver — тесты резолвера (§10.11)."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import date, timedelta

import pytest

from kg_common.retention_policy import (
    DEFAULT_RULES,
    RetentionRule,
    expired_ids,
    expiry_date,
    is_expired,
    rule_for,
)


def test_default_rules_values() -> None:
    assert rule_for("kg-raw").retention_days == 3650
    assert rule_for("kg-raw").archive is True
    assert rule_for("kg-parsed").retention_days == 730
    assert rule_for("kg-parsed").archive is True
    assert rule_for("kg-audit").retention_days == 3650
    assert rule_for("kg-audit").archive is False


def test_rule_for_unknown_raises() -> None:
    with pytest.raises(KeyError):
        rule_for("nope")


def test_rule_for_custom_rules() -> None:
    custom = {"kg-tmp": RetentionRule("kg-tmp", 7, False)}
    assert rule_for("kg-tmp", custom).retention_days == 7
    with pytest.raises(KeyError):
        rule_for("kg-raw", custom)


def test_expiry_date_parsed_730_days() -> None:
    # 730 days from 2020-01-01: 2020 is a leap year (366d), so +730 lands on
    # 2021-12-31 (366 + 364). Reaching 2022-01-01 would take 731 days.
    assert expiry_date(date(2020, 1, 1), "kg-parsed") == date(2021, 12, 31)
    assert expiry_date(date(2020, 1, 1), "kg-parsed") == date(2020, 1, 1) + timedelta(days=730)


def test_expiry_date_raw_3650_days() -> None:
    assert expiry_date(date(2010, 1, 1), "kg-raw") == date(2010, 1, 1) + timedelta(days=3650)


def test_is_expired_parsed_true() -> None:
    assert is_expired(date(2020, 1, 1), date(2026, 1, 1), "kg-parsed") is True


def test_is_expired_raw_false() -> None:
    assert is_expired(date(2025, 1, 1), date(2026, 1, 1), "kg-raw") is False


def test_is_expired_boundary_exact_day() -> None:
    # Expiry for a 2020-01-01 kg-parsed object is 2021-12-31 (730d, leap year).
    # Exactly on the expiry date counts as expired.
    assert is_expired(date(2020, 1, 1), date(2021, 12, 31), "kg-parsed") is True
    # One day before is still live.
    assert is_expired(date(2020, 1, 1), date(2021, 12, 30), "kg-parsed") is False


def test_expired_ids_filters_by_bucket() -> None:
    items = [
        ("a", "kg-raw", date(2010, 1, 1)),
        ("b", "kg-raw", date(2026, 7, 1)),
    ]
    # 'a' created 2010 (>10y ago, kg-raw 3650d) is expired; 'b' is fresh.
    assert expired_ids(items, date(2026, 7, 3)) == ["a"]


def test_expired_ids_mixed_buckets_preserves_order() -> None:
    items = [
        ("p", "kg-parsed", date(2020, 1, 1)),  # expired (730d)
        ("r", "kg-raw", date(2025, 1, 1)),  # live (3650d)
        ("au", "kg-audit", date(2000, 1, 1)),  # expired (3650d)
    ]
    assert expired_ids(items, date(2026, 1, 1)) == ["p", "au"]


def test_expired_ids_empty() -> None:
    assert expired_ids([], date(2026, 1, 1)) == []


def test_as_dict_roundtrip_view() -> None:
    rule = RetentionRule("kg-audit", 3650, False)
    assert rule.as_dict() == {
        "bucket": "kg-audit",
        "retention_days": 3650,
        "archive": False,
    }
    assert rule.as_dict()["archive"] is False


def test_default_rules_immutable() -> None:
    with pytest.raises(TypeError):
        DEFAULT_RULES["kg-raw"] = RetentionRule("kg-raw", 1, False)  # type: ignore[index]


def test_rule_frozen() -> None:
    rule = rule_for("kg-raw")
    with pytest.raises(FrozenInstanceError):
        rule.retention_days = 1  # type: ignore[misc]
