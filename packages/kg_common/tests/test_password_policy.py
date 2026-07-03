"""Tests for the password strength policy validator (§19.2 Auth).

Тесты валидатора надёжности паролей — hand-checkable, no fixtures.
"""

from __future__ import annotations

import pytest

from kg_common.security.password_policy import (
    PasswordCheck,
    PasswordPolicy,
    check_password,
)


def test_short_password_fails_min_len() -> None:
    """A too-short password fails and reports 'min_len' — короткий пароль."""
    result = check_password(PasswordPolicy(), "short")
    assert result.ok is False
    assert "min_len" in result.violations


def test_all_lowercase_reports_upper_and_symbol() -> None:
    """A long lowercase+digit password lacks upper and symbol classes."""
    result = check_password(PasswordPolicy(), "alllowercase12345")
    assert "require_upper" in result.violations
    assert "require_symbol" in result.violations
    # It does have lowercase and digits, so those are not reported.
    assert "require_lower" not in result.violations
    assert "require_digit" not in result.violations


def test_strong_passphrase_passes_cleanly() -> None:
    """A strong passphrase satisfies every rule with an empty violations tuple."""
    result = check_password(PasswordPolicy(), "Str0ng!Passphrase")
    assert result.ok is True
    assert result.violations == ()


def test_blocklisted_password_is_rejected() -> None:
    """An exact blocklist hit reports 'blocklisted' — пароль в чёрном списке."""
    policy = PasswordPolicy(blocklist=frozenset({"Password123!"}))
    result = check_password(policy, "Password123!")
    assert "blocklisted" in result.violations
    assert result.ok is False


def test_missing_digit_reports_require_digit() -> None:
    """A password lacking digits reports 'require_digit' — нет цифры."""
    result = check_password(PasswordPolicy(), "NoDigitsHere!")
    assert "require_digit" in result.violations
    assert result.ok is False


def test_strong_passphrase_strength_at_least_three() -> None:
    """The strong passphrase scores >= 3 on the 0..4 strength scale."""
    result = check_password(PasswordPolicy(), "Str0ng!Passphrase")
    assert result.strength >= 3
    assert 0 <= result.strength <= 4


def test_policy_as_dict_reports_min_len_default() -> None:
    """PasswordPolicy().as_dict()['min_len'] is the default 12."""
    d = PasswordPolicy().as_dict()
    assert d["min_len"] == 12
    assert d["require_upper"] is True
    assert d["blocklist"] == []


def test_check_as_dict_round_trips_fields() -> None:
    """PasswordCheck.as_dict() exposes ok, violations (list) and strength."""
    result = check_password(PasswordPolicy(), "short")
    d = result.as_dict()
    assert d["ok"] is False
    assert isinstance(d["violations"], list)
    assert "min_len" in d["violations"]
    assert d["strength"] == result.strength


def test_violation_order_is_stable() -> None:
    """Violations are collected in rule order: min_len before class rules."""
    # 'ab' is short, lacks upper/digit/symbol — several rules fail at once.
    result = check_password(PasswordPolicy(), "ab")
    assert result.violations[0] == "min_len"
    assert list(result.violations) == [
        "min_len",
        "require_upper",
        "require_digit",
        "require_symbol",
    ]


def test_empty_password_has_zero_strength() -> None:
    """An empty password scores 0 strength and fails min_len — пустой пароль."""
    result = check_password(PasswordPolicy(), "")
    assert result.strength == 0
    assert "min_len" in result.violations


def test_disabled_requirements_are_not_reported() -> None:
    """Disabling a require_* flag drops its violation — правило отключено."""
    policy = PasswordPolicy(
        require_upper=False,
        require_digit=False,
        require_symbol=False,
    )
    result = check_password(policy, "justlowercaseletters")
    assert result.ok is True
    assert result.violations == ()


def test_check_and_policy_are_frozen() -> None:
    """PasswordPolicy and PasswordCheck are immutable — заморожены."""
    policy = PasswordPolicy()
    result = check_password(policy, "Str0ng!Passphrase")
    with pytest.raises(AttributeError):
        policy.min_len = 4  # type: ignore[misc]
    with pytest.raises(AttributeError):
        result.ok = False  # type: ignore[misc]


def test_result_is_password_check_instance() -> None:
    """check_password returns a PasswordCheck — тип результата."""
    result = check_password(PasswordPolicy(), "Str0ng!Passphrase")
    assert isinstance(result, PasswordCheck)
