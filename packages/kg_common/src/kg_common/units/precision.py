"""Significant-figure & precision tracking for canonical numeric values (§7.4/§7.5).

Отслеживание значащих цифр — records how precise a *raw* numeric string was so a
normalized value is neither over- nor under-reported. ``numeric_normalize`` only
yields the ``float`` and throws away how many digits the source actually
committed to; this module recovers that from the original string.

Two questions are answered here:

* **§7.4 parsing** — how many significant figures did the source write?
  ``significant_figures("0.00320")`` is ``3`` (leading zeros никогда не считаются,
  trailing zeros count only когда a decimal point is present).
* **§7.5 canonical value / comparison tolerance** — round a value to that
  precision (:func:`round_to_sigfigs`) or express a value±uncertainty pair with a
  matching number of decimals (:func:`round_to_uncertainty`), so two measurements
  are compared at the coarser of their two precisions.

Pure stdlib — :class:`~decimal.Decimal` is used only to read a value's decimal
exponent robustly (``log10`` floating-point drift would mis-round powers of ten).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from math import isfinite
from typing import Any


@dataclass(frozen=True)
class PrecisionInfo:
    """Precision of a raw numeric token (§7.4/§7.5).

    ``sig_figs`` — number of significant figures read from the raw string.
    ``decimals`` — decimal place of the least significant figure (position after
    the point; negative means the last certain digit is left of the point, e.g.
    ``1500`` → ``-2``). ``rounded`` — value re-rounded to ``sig_figs`` figures.
    """

    sig_figs: int
    decimals: int
    rounded: float

    def as_dict(self) -> dict[str, Any]:
        """JSON-ready mapping of the three fields."""
        return {
            "sig_figs": self.sig_figs,
            "decimals": self.decimals,
            "rounded": self.rounded,
        }


def _split_mantissa(raw: str) -> str:
    """Return the mantissa part of *raw*, dropping any ``e``/``E`` exponent.

    Exponent digits describe magnitude, not precision, so they never count toward
    significant figures (``"1.5e3"`` has the same 2 figures as ``"1.5"``).
    """
    low = raw.lower()
    idx = low.find("e")
    return raw if idx < 0 else raw[:idx]


def significant_figures(raw: str) -> int:
    """Count significant figures in the raw numeric string *raw* (§7.4).

    Rules: leading zeros never count; trailing zeros count **only** when a decimal
    point is present; the ``e``/``E`` exponent is ignored. Examples::

        significant_figures("0.00320") == 3
        significant_figures("1.200")   == 4
        significant_figures("1500")    == 2   # no point → trailing zeros drop
        significant_figures("100.")    == 3   # point → trailing zeros count
        significant_figures("1.5e3")   == 2

    Raises :class:`ValueError` on an empty or non-numeric mantissa.
    """
    token = _split_mantissa(raw).strip()
    if not token:
        raise ValueError(f"empty numeric token: {raw!r}")
    core = token.lstrip("+-")
    has_dot = "." in core
    int_part, _, frac_part = core.partition(".")
    digits = int_part + frac_part
    if not digits or not digits.isdigit():
        raise ValueError(f"non-numeric token: {raw!r}")

    if has_dot:
        # Trailing zeros are significant; strip only the leading zeros.
        stripped = digits.lstrip("0")
        if not stripped:  # pure zero, e.g. "0.00" — the frac zeros are the figures
            return max(len(frac_part), 1)
        return len(stripped)

    # Integer with no point: neither leading nor trailing zeros are significant.
    stripped = digits.lstrip("0").rstrip("0")
    return len(stripped) if stripped else 1


def round_to_sigfigs(value: float, sig: int) -> float:
    """Round *value* to *sig* significant figures (§7.5).

    Examples::

        round_to_sigfigs(123456, 3)   == 123000.0
        round_to_sigfigs(0.0034567, 2) == 0.0035

    Raises :class:`ValueError` if ``sig < 1``.
    """
    if sig < 1:
        raise ValueError(f"sig must be >= 1, got {sig}")
    if value == 0 or not isfinite(value):
        return float(value)
    ndigits = sig - 1 - _adjusted(value)
    return float(round(value, ndigits))


def round_to_uncertainty(value: float, uncertainty: float) -> tuple[float, float]:
    """Round *value* to match a 1-sig-fig *uncertainty* (§7.5).

    The uncertainty is rounded to a single significant figure, then the value is
    rounded to that same decimal place — the reporting convention for a
    measurement ``value ± uncertainty``. Example::

        round_to_uncertainty(1.827, 0.12) == (1.8, 0.1)
    """
    unc = abs(uncertainty)
    if unc == 0 or not isfinite(unc) or not isfinite(value):
        return (float(value), float(uncertainty))
    unc_rounded = round_to_sigfigs(unc, 1)
    place = -_adjusted(unc_rounded)
    value_rounded = float(round(value, place))
    unc_final = float(round(unc_rounded, place))
    return (value_rounded, unc_final)


def describe(raw: str, sig: int | None = None) -> PrecisionInfo:
    """Build a :class:`PrecisionInfo` for the raw token *raw* (§7.4/§7.5).

    ``sig`` overrides the counted significant figures when the caller already
    knows the intended precision. Example::

        describe("1.200").as_dict()["sig_figs"] == 4
    """
    value = float(raw)
    figs = significant_figures(raw) if sig is None else sig
    if figs < 1:
        raise ValueError(f"sig must be >= 1, got {figs}")
    rounded = round_to_sigfigs(value, figs)
    decimals = 0 if value == 0 else figs - 1 - _adjusted(value)
    return PrecisionInfo(sig_figs=figs, decimals=decimals, rounded=rounded)


def _adjusted(value: float) -> int:
    """Decimal exponent of *value*'s most significant digit (``floor(log10|v|)``).

    ``Decimal(repr(v)).adjusted()`` reads it exactly, avoiding ``log10`` drift on
    powers of ten (``adjusted(123456) == 5``, ``adjusted(0.0034) == -3``).
    """
    return Decimal(repr(value)).adjusted()
