"""Cross-unit measurement comparison & agreement — сравнение измерений (§7.5/§7.7).

Contradiction detection (§11, «conflicting measurements») needs to decide whether
two measurements *agree* even when they are expressed in **different units** — e.g.
``100 °C`` vs ``373.15 K`` or ``1 MPa`` vs ``1000 kPa``. The existing pieces do not
cover this: :mod:`kg_common.measurement_dedup` collapses only exact-identity
duplicates and ``solution_compare`` is a retriever-side table. This module fills the
gap by converting the second measurement into the first one's unit via
:func:`kg_common.units.conversions.convert` and classifying the outcome.

Public API:

* :class:`MeasurementComparison` — frozen verdict with :meth:`~MeasurementComparison.as_dict`.
* :func:`compare_values`         — compare two (value, unit) pairs within a relative tolerance.
* :func:`intervals_overlap`      — do two closed intervals share any point?
* :func:`agreement_with_uncertainty` — do the ``value ± uncertainty`` bands overlap?

``relation`` is one of ``{"equal", "greater", "less", "incomparable"}`` and is read
from *a*'s perspective (``greater`` means ``a > b``). When the two units belong to
different physical dimensions (or one is unknown) the pair is **incomparable** and
``method == "incompatible"``. Pure Python, no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass

from kg_common.units.conversions import (
    IncompatibleUnitsError,
    UnknownUnitError,
    convert,
)

# relation values --------------------------------------------------------------
EQUAL = "equal"
GREATER = "greater"
LESS = "less"
INCOMPARABLE = "incomparable"

RELATIONS: tuple[str, ...] = (EQUAL, GREATER, LESS, INCOMPARABLE)

# method values ----------------------------------------------------------------
METHOD_RATIO = "ratio"  # compared numerically after unit conversion
METHOD_DELTA = "delta"  # ratio undefined (b == 0), fell back to absolute delta
METHOD_INCOMPATIBLE = "incompatible"  # different dimensions / unknown unit


@dataclass(frozen=True)
class MeasurementComparison:
    """Immutable verdict of comparing two measurements — результат сравнения (§7.5).

    ``ratio``/``delta``/``common_unit`` are ``None`` when the measurements are
    incomparable (different dimensions or an unknown unit). ``ratio`` is the
    dimensionless ``a / b`` (in the common unit) and ``delta`` the signed
    ``a − b``; both are expressed in ``common_unit`` (which equals *a*'s unit).
    """

    agree: bool
    relation: str
    ratio: float | None
    delta: float | None
    common_unit: str | None
    method: str

    def as_dict(self) -> dict[str, object]:
        """JSON-friendly view — строка результата сравнения (§7.5)."""
        return {
            "agree": self.agree,
            "relation": self.relation,
            "ratio": self.ratio,
            "delta": self.delta,
            "common_unit": self.common_unit,
            "method": self.method,
        }


def compare_values(
    a_value: float,
    a_unit: str,
    b_value: float,
    b_unit: str,
    rel_tol: float = 0.05,
) -> MeasurementComparison:
    """Compare ``(a_value, a_unit)`` with ``(b_value, b_unit)`` — сравнение (§7.5/§7.7).

    *b* is converted into *a*'s unit; the two are said to **agree** when the
    relative difference ``|ratio − 1| <= rel_tol`` (with ``ratio = a / b``). The
    ``relation`` is read from *a*'s side: ``greater`` when ``a > b`` beyond the
    tolerance, ``less`` when ``a < b``, ``equal`` when they agree.

    If the units belong to different physical dimensions — or either is unknown —
    the result is ``relation == "incomparable"`` with ``method == "incompatible"``
    and ``agree is False`` (raised as :class:`IncompatibleUnitsError` /
    :class:`UnknownUnitError` by the converter, caught here).
    """
    try:
        b_in_a = convert(float(b_value), b_unit, a_unit)
    except (IncompatibleUnitsError, UnknownUnitError):
        return MeasurementComparison(
            agree=False,
            relation=INCOMPARABLE,
            ratio=None,
            delta=None,
            common_unit=None,
            method=METHOD_INCOMPATIBLE,
        )

    a = float(a_value)
    delta = a - b_in_a

    # Ratio is the primary agreement signal, but is undefined when b == 0; there
    # fall back to an absolute-delta check (both zero ⇒ agree).
    if b_in_a == 0.0:
        ratio: float | None = None
        agree = a == 0.0
        method = METHOD_DELTA
    else:
        ratio = a / b_in_a
        agree = abs(ratio - 1.0) <= rel_tol
        method = METHOD_RATIO

    if agree:
        relation = EQUAL
    elif a > b_in_a:
        relation = GREATER
    else:
        relation = LESS

    return MeasurementComparison(
        agree=agree,
        relation=relation,
        ratio=ratio,
        delta=delta,
        common_unit=a_unit,
        method=method,
    )


def intervals_overlap(a: tuple[float, float], b: tuple[float, float]) -> bool:
    """True iff two closed intervals share at least one point — пересечение (§7.7).

    Endpoints are order-insensitive: ``(20, 10)`` is treated the same as
    ``(10, 20)``. Touching at a single endpoint counts as overlap.
    """
    a_lo, a_hi = (a[0], a[1]) if a[0] <= a[1] else (a[1], a[0])
    b_lo, b_hi = (b[0], b[1]) if b[0] <= b[1] else (b[1], b[0])
    return a_lo <= b_hi and b_lo <= a_hi


def agreement_with_uncertainty(a: float, ua: float, b: float, ub: float) -> bool:
    """True iff the ``a ± ua`` and ``b ± ub`` bands overlap — согласие с погрешностью (§7.7).

    Uncertainties are taken as non-negative half-widths (their magnitude is used,
    so a stray negative sign is tolerated). Two measurements are considered to
    agree when their symmetric uncertainty intervals share any point.
    """
    ua, ub = abs(ua), abs(ub)
    return intervals_overlap((a - ua, a + ua), (b - ub, b + ub))


__all__ = [
    "EQUAL",
    "GREATER",
    "INCOMPARABLE",
    "LESS",
    "METHOD_DELTA",
    "METHOD_INCOMPATIBLE",
    "METHOD_RATIO",
    "RELATIONS",
    "MeasurementComparison",
    "agreement_with_uncertainty",
    "compare_values",
    "intervals_overlap",
]
