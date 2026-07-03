"""Password strength policy validator — валидатор надёжности паролей (§19.2 Auth).

A :class:`PasswordPolicy` declares the minimum requirements a password must
satisfy: a minimum length plus mandatory character classes (upper, lower, digit,
symbol) and an optional exact-match ``blocklist`` of forbidden passwords. The
policy is a *frozen* dataclass — immutable «неизменяемая политика».

:func:`check_password` evaluates a candidate password against a policy and returns
a frozen :class:`PasswordCheck` carrying:

* ``ok`` — whether the password satisfied every enabled rule «прошёл проверку»;
* ``violations`` — an ordered tuple of violation *codes*
  (``'min_len'``, ``'require_upper'``, ``'require_lower'``, ``'require_digit'``,
  ``'require_symbol'``, ``'blocklisted'``);
* ``strength`` — an integer ``0..4`` derived from character-class diversity
  plus a length bonus «оценка стойкости».

Pure-python, no third-party dependency.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Violation codes emitted by :func:`check_password` («коды нарушений»).
CODE_MIN_LEN = "min_len"
CODE_REQUIRE_UPPER = "require_upper"
CODE_REQUIRE_LOWER = "require_lower"
CODE_REQUIRE_DIGIT = "require_digit"
CODE_REQUIRE_SYMBOL = "require_symbol"
CODE_BLOCKLISTED = "blocklisted"

# Length at/above which the strength score earns its length bonus («бонус длины»).
_LENGTH_BONUS_THRESHOLD = 12

# Maximum strength score («максимальная оценка»).
_MAX_STRENGTH = 4


def _has_upper(pw: str) -> bool:
    """True if *pw* contains an uppercase letter («есть заглавная буква»)."""
    return any(c.isupper() for c in pw)


def _has_lower(pw: str) -> bool:
    """True if *pw* contains a lowercase letter («есть строчная буква»)."""
    return any(c.islower() for c in pw)


def _has_digit(pw: str) -> bool:
    """True if *pw* contains a decimal digit («есть цифра»)."""
    return any(c.isdigit() for c in pw)


def _has_symbol(pw: str) -> bool:
    """True if *pw* contains a non-alphanumeric, non-space symbol («есть символ»)."""
    return any((not c.isalnum()) and (not c.isspace()) for c in pw)


@dataclass(frozen=True)
class PasswordPolicy:
    """Immutable password strength policy (§19.2 Auth).

    ``min_len`` is the minimum acceptable length; the ``require_*`` flags toggle
    the mandatory character classes; ``blocklist`` is a set of exact passwords that
    are always rejected («запрещённые пароли»).
    """

    min_len: int = 12
    require_upper: bool = True
    require_lower: bool = True
    require_digit: bool = True
    require_symbol: bool = True
    blocklist: frozenset[str] = frozenset()

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly view of the policy («словарь для сериализации»)."""
        return {
            "min_len": self.min_len,
            "require_upper": self.require_upper,
            "require_lower": self.require_lower,
            "require_digit": self.require_digit,
            "require_symbol": self.require_symbol,
            "blocklist": sorted(self.blocklist),
        }


@dataclass(frozen=True)
class PasswordCheck:
    """Outcome of checking one password against a policy (§19.2 Auth).

    ``ok`` is ``True`` only when ``violations`` is empty; ``violations`` lists the
    failed rule codes in evaluation order; ``strength`` is a ``0..4`` score derived
    from character-class diversity and a length bonus «оценка стойкости».
    """

    ok: bool
    violations: tuple[str, ...] = ()
    strength: int = 0

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly view of the check («словарь для сериализации»)."""
        return {
            "ok": self.ok,
            "violations": list(self.violations),
            "strength": self.strength,
        }


def _password_strength(pw: str) -> int:
    """Score *pw* on ``0..4`` from class diversity plus a length bonus (§19.2).

    Diversity counts how many of the four character classes (upper, lower, digit,
    symbol) appear; a password of at least :data:`_LENGTH_BONUS_THRESHOLD`
    characters earns one bonus point. The result is clamped to ``0..4``.
    """
    if not pw:
        return 0
    diversity = sum((_has_upper(pw), _has_lower(pw), _has_digit(pw), _has_symbol(pw)))
    bonus = 1 if len(pw) >= _LENGTH_BONUS_THRESHOLD else 0
    return min(_MAX_STRENGTH, diversity + bonus)


def check_password(policy: PasswordPolicy, pw: str) -> PasswordCheck:
    """Evaluate *pw* against *policy*, returning a frozen :class:`PasswordCheck`.

    Violation codes are collected in a stable order: ``'min_len'`` first, then the
    enabled ``require_*`` classes, then ``'blocklisted'`` for an exact blocklist hit.
    ``ok`` is ``True`` only when no rule was violated «пароль прошёл все правила».
    The ``strength`` score is independent of the pass/fail verdict.
    """
    violations: list[str] = []

    if len(pw) < policy.min_len:
        violations.append(CODE_MIN_LEN)
    if policy.require_upper and not _has_upper(pw):
        violations.append(CODE_REQUIRE_UPPER)
    if policy.require_lower and not _has_lower(pw):
        violations.append(CODE_REQUIRE_LOWER)
    if policy.require_digit and not _has_digit(pw):
        violations.append(CODE_REQUIRE_DIGIT)
    if policy.require_symbol and not _has_symbol(pw):
        violations.append(CODE_REQUIRE_SYMBOL)
    if pw in policy.blocklist:
        violations.append(CODE_BLOCKLISTED)

    return PasswordCheck(
        ok=not violations,
        violations=tuple(violations),
        strength=_password_strength(pw),
    )
