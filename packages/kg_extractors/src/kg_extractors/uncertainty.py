"""§7.9 measurement uncertainty — parsing + standard error propagation (RU & EN).

Parses a measured value with an attached uncertainty into a frozen
:class:`Uncertainty` record and combines such records under the standard
(Gaussian, uncorrelated) error-propagation rules.

Recognized surface forms (``±`` is U+00B1; ASCII spellings ``+/-`` / ``+-`` are
accepted; a trailing ``%`` marks a *relative* uncertainty)::

    «148 ± 5»       -> value 148, ±5 absolute        (lower 143, upper 153)
    «148 +/- 5»     -> value 148, ±5 absolute        (ASCII half-width)
    «148 ± 2%»      -> value 148, ±2 % relative       (± 2.96 absolute)
    «148 (±3%)»     -> value 148, ±3 % relative       (± 4.44 absolute)
    «148»           -> value 148, exact (±0)          (bare value)

Both an absolute half-width (:attr:`Uncertainty.plus_minus`) and a relative
percentage (:attr:`Uncertainty.rel_pct`) are always populated: whichever the raw
string states is kept verbatim and the other is derived from it.

Propagation (:func:`propagate_sum`, :func:`propagate_product`) follows the usual
first-order rules — **absolute** errors add in quadrature for a sum, **relative**
errors add in quadrature for a product — each returning a *new* frozen
:class:`Uncertainty`. Pure-python / regex + :mod:`math` only.
"""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Uncertainty record (§7.9)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Uncertainty:
    """A measured value with its uncertainty (§7.9).

    ``value`` is the central magnitude, ``plus_minus`` the absolute half-width
    (``±``), ``rel_pct`` the equivalent relative uncertainty in percent, and
    ``lower`` / ``upper`` the ``value ∓ plus_minus`` interval endpoints. All
    fields are always populated; the absolute and relative errors are kept
    mutually consistent by the :meth:`from_abs` / :meth:`from_rel` builders.
    """

    value: float
    plus_minus: float
    rel_pct: float
    lower: float
    upper: float

    @classmethod
    def from_abs(cls, value: float, plus_minus: float) -> Uncertainty:
        """Build from a central value and an absolute half-width ``± plus_minus``."""
        rel_pct = (plus_minus / abs(value) * 100.0) if value != 0.0 else 0.0
        return cls(
            value=value,
            plus_minus=plus_minus,
            rel_pct=rel_pct,
            lower=value - plus_minus,
            upper=value + plus_minus,
        )

    @classmethod
    def from_rel(cls, value: float, rel_pct: float) -> Uncertainty:
        """Build from a central value and a relative uncertainty ``± rel_pct`` (%)."""
        plus_minus = abs(value) * rel_pct / 100.0
        return cls(
            value=value,
            plus_minus=plus_minus,
            rel_pct=rel_pct,
            lower=value - plus_minus,
            upper=value + plus_minus,
        )

    def as_dict(self) -> dict[str, float]:
        """Serialize to a plain dict of all five fields."""
        return {
            "value": self.value,
            "plus_minus": self.plus_minus,
            "rel_pct": self.rel_pct,
            "lower": self.lower,
            "upper": self.upper,
        }


# ---------------------------------------------------------------------------
# Parsing patterns
# ---------------------------------------------------------------------------

# A signed decimal token (decimal comma «2,5» accepted, folded to a dot).
_NUM = r"[-+]?\d+(?:[.,]\d+)?"
# ``±`` symbol and its ASCII spellings.
_PM = r"±|\+/-|\+-"

# «148», «148 ± 5», «148 +/- 5», «148 ± 2%», «148 (±3%)».
_RE = re.compile(
    rf"^\s*(?P<value>{_NUM})"
    rf"(?:\s*\(?\s*(?:{_PM})\s*(?P<unc>{_NUM})\s*(?P<pct>%)?\s*\)?)?"
    rf"\s*$"
)


def _to_float(token: str) -> float:
    """Parse a numeric token, folding a decimal comma to a dot."""
    return float(token.strip().replace(",", "."))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse_uncertainty(raw: str) -> Uncertainty | None:
    """Parse a value-with-uncertainty string into :class:`Uncertainty`, else ``None``.

    A bare value («148») yields an exact record (``plus_minus == 0``). A trailing
    ``%`` marks a relative uncertainty. A string with no leading number, or a
    *negative* uncertainty half-width (not physical), returns ``None``.
    """
    if not raw or not raw.strip():
        return None
    text = unicodedata.normalize("NFKC", raw).strip()
    m = _RE.match(text)
    if not m:
        return None

    value = _to_float(m.group("value"))
    unc = m.group("unc")
    if unc is None:
        return Uncertainty.from_abs(value, 0.0)  # bare value / bare — exact

    unc_val = _to_float(unc)
    if unc_val < 0.0:
        return None  # a ± half-width cannot be negative / отрицательная погрешность
    if m.group("pct"):
        return Uncertainty.from_rel(value, unc_val)
    return Uncertainty.from_abs(value, unc_val)


def propagate_sum(a: Uncertainty, b: Uncertainty) -> Uncertainty:
    """Combine ``a + b``: absolute errors add in quadrature (``√(σa² + σb²)``)."""
    value = a.value + b.value
    plus_minus = math.hypot(a.plus_minus, b.plus_minus)
    return Uncertainty.from_abs(value, plus_minus)


def propagate_product(a: Uncertainty, b: Uncertainty) -> Uncertainty:
    """Combine ``a * b``: relative errors add in quadrature (``√(ra² + rb²)``)."""
    value = a.value * b.value
    rel_pct = math.hypot(a.rel_pct, b.rel_pct)
    return Uncertainty.from_rel(value, rel_pct)
