"""Composition balance resolution + sum validation (§6.21).

Alloy/material compositions are often reported with one element given as
"balance" (Rus. «остальное») instead of a number — the reader is expected to
infer its fraction as ``100 - sum(other elements)``. This module resolves such
balance elements and validates that a composition's fractions sum to the
expected total (default 100 %).

- :func:`balance_composition` — replace each ``is_balance`` element's value
  with its share of the residual (``total - sum(fixed)``); a residual split
  evenly across multiple balance elements. Non-balance values pass through.
- :func:`validate_sums` — report ``{ok, total, residual}`` for a composition:
  ``total`` is the sum of the numeric fractions, ``residual = total_target -
  total``, and ``ok`` is true iff ``|residual|`` is within tolerance.

Разрешение элемента-остатка (100 - сумма) и проверка суммы долей (§6.21).

Pure python — no external dependency.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

# Default composition target (weight/atomic percent) and sum tolerance.
DEFAULT_TOTAL: float = 100.0
DEFAULT_TOLERANCE: float = 0.5

# Rounding used to tame binary-float noise on resolved shares / sums.
_ROUND = 9


@dataclass(frozen=True)
class Fraction:
    """One element's fraction in a composition (§6.21).

    ``value`` is ``None`` for an as-yet-unresolved balance element; after
    :func:`balance_composition` every balance element carries a numeric share.
    """

    element: str
    value: float | None
    is_balance: bool = False

    def as_dict(self) -> dict[str, object]:
        return {
            "element": self.element,
            "value": self.value,
            "is_balance": self.is_balance,
        }


def _coerce(fractions: list[dict | Fraction]) -> list[Fraction]:
    """Normalize dicts / :class:`Fraction` into a list of :class:`Fraction`."""
    out: list[Fraction] = []
    for f in fractions:
        if isinstance(f, Fraction):
            out.append(f)
            continue
        element = str(f["element"])
        raw = f.get("value")
        value = None if raw is None else float(raw)
        is_balance = bool(f.get("is_balance", False))
        out.append(Fraction(element, value, is_balance))
    return out


def _fixed_sum(parsed: list[Fraction]) -> float:
    """Sum of numeric values of the non-balance elements."""
    return sum(f.value or 0.0 for f in parsed if not f.is_balance)


def balance_composition(
    fractions: list[dict | Fraction], total: float = DEFAULT_TOTAL
) -> list[Fraction]:
    """Resolve balance elements to their share of ``total - sum(fixed)`` (§6.21).

    The residual (which may be negative when the fixed elements already exceed
    *total*) is split evenly across all ``is_balance`` elements. Input order is
    preserved; non-balance elements are returned unchanged. With no balance
    element the composition is returned parsed but otherwise untouched.
    """
    parsed = _coerce(fractions)
    balances = [f for f in parsed if f.is_balance]
    if not balances:
        return parsed
    residual = total - _fixed_sum(parsed)
    share = round(residual / len(balances), _ROUND)
    return [replace(f, value=share) if f.is_balance else f for f in parsed]


def validate_sums(
    fractions: list[dict | Fraction],
    total: float = DEFAULT_TOTAL,
    tolerance: float = DEFAULT_TOLERANCE,
) -> dict[str, object]:
    """Validate that fractions sum to *total* within *tolerance* (§6.21).

    Returns ``{"ok", "total", "residual"}`` where ``total`` is the summed
    numeric fractions (``None`` values counted as 0), ``residual = total_target
    - summed``, and ``ok`` is ``True`` iff ``|residual| <= tolerance``.
    """
    parsed = _coerce(fractions)
    summed = round(sum(f.value or 0.0 for f in parsed), _ROUND)
    residual = round(total - summed, _ROUND)
    return {"ok": abs(residual) <= tolerance, "total": summed, "residual": residual}
