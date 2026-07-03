"""Range / bound canonicalization into target units (§7.5).

Канонизация интервалов — normalize ``value_min`` / ``value_max`` / bounds into a
single canonical unit together with a representative scalar ``value`` so that a
range ("12–28 %") or an inequality (">= 320 MPa") can be indexed, compared, and
rendered like an ordinary measurement.

``measurement_normalizer`` only handles a *scalar* ``value`` + ``unit`` pair; it
cannot describe an extracted attribute that arrived as two endpoints or as a
one-sided bound. This module fills that gap:

* **range** — both endpoints present; ``value`` is the midpoint
  ``(value_min + value_max) / 2`` and ``representative_source == "midpoint"``.
* **bound** — exactly one endpoint present with an ``operator`` (``>=``/``<=``/
  ``>``/``<``); ``value`` is the bound itself and ``representative_source`` names
  which endpoint it came from (``"lower_bound"`` / ``"upper_bound"``).
* **scalar** — exactly one endpoint present *without* an operator; treated as a
  plain point value (``representative_source == "value"``).

Both endpoints are converted through the injected ``converter`` (defaults to
:func:`kg_common.units.conversions.convert`), so ``value_min`` / ``value_max`` /
``value`` are always expressed in ``target`` units.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Any

from kg_common.units.conversions import convert

Converter = Callable[[float, str, str], float]


@dataclass(frozen=True)
class NormalizedInterval:
    """A canonicalized interval / bound / scalar (§7.5).

    ``kind`` — one of ``"range"`` / ``"bound"`` / ``"scalar"``.
    ``unit`` — canonical target unit (``None`` only when no unit applies).
    ``value`` — representative scalar in ``unit`` (midpoint for a range, the
    bound itself for an inequality, the point value for a scalar).
    ``value_min`` / ``value_max`` — converted endpoints in ``unit`` (``None`` for
    the missing side of a one-sided bound / scalar).
    ``operator`` — comparison operator for a bound (``None`` otherwise).
    ``representative_source`` — how ``value`` was derived: ``"midpoint"`` /
    ``"lower_bound"`` / ``"upper_bound"`` / ``"value"``.
    """

    kind: str
    unit: str | None
    value: float | None
    value_min: float | None
    value_max: float | None
    operator: str | None
    representative_source: str

    def as_dict(self) -> dict[str, Any]:
        """Return a plain dict (JSON-friendly) of all fields."""
        return asdict(self)


def normalize_interval(
    value_min: float | None,
    value_max: float | None,
    unit: str,
    target: str,
    *,
    operator: str | None = None,
    converter: Converter = convert,
) -> NormalizedInterval:
    """Canonicalize a ``[value_min, value_max]`` interval / bound into *target* (§7.5).

    Оба конца конвертируются через ``converter`` (value → target). The ``kind``
    is inferred from which endpoints are present:

    * both endpoints → ``"range"`` with ``value`` = midpoint.
    * one endpoint + ``operator`` → ``"bound"`` with ``value`` = that endpoint.
    * one endpoint, no ``operator`` → ``"scalar"`` with ``value`` = that endpoint.

    Raises :class:`ValueError` if neither endpoint is supplied.
    """
    lo = None if value_min is None else float(converter(float(value_min), unit, target))
    hi = None if value_max is None else float(converter(float(value_max), unit, target))

    if lo is not None and hi is not None:
        return NormalizedInterval(
            kind="range",
            unit=target,
            value=(lo + hi) / 2.0,
            value_min=lo,
            value_max=hi,
            operator=operator,
            representative_source="midpoint",
        )

    if lo is None and hi is None:
        raise ValueError("normalize_interval requires at least one of value_min/value_max")

    present = lo if lo is not None else hi
    source = "lower_bound" if lo is not None else "upper_bound"

    if operator is not None:
        return NormalizedInterval(
            kind="bound",
            unit=target,
            value=present,
            value_min=lo,
            value_max=hi,
            operator=operator,
            representative_source=source,
        )

    return NormalizedInterval(
        kind="scalar",
        unit=target,
        value=present,
        value_min=lo,
        value_max=hi,
        operator=None,
        representative_source="value",
    )
