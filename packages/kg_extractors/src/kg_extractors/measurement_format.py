"""Canonical measurement string formatting + parse-back (§7.16).

Renders a numeric measurement into one canonical human string and parses it back
into its parts. The canonical forms (канонические формы) are:

* value + unit           → ``"148 HV"``
* value ± uncertainty     → ``"148 ± 5 HV"``
* range (кортеж/список)   → ``"200-300 MPa"``
* no unit                 → ``"7"`` / ``"7 ± 1"``

Numbers are rendered without trailing ``.0`` (целые как целые), so
``format_measurement(148.0, "HV") == "148 HV"``. :func:`parse_back` is the exact
inverse for every form :func:`format_measurement` can emit.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# ± sign used between value and uncertainty (знак неопределённости).
PLUS_MINUS = "±"

_NUM = r"[+-]?\d+(?:\.\d+)?"
_RANGE_RE = re.compile(rf"^\s*(?P<lo>{_NUM})\s*-\s*(?P<hi>{_NUM})\s*(?P<unit>\S.*)?$")
_UNCERTAIN_RE = re.compile(
    rf"^\s*(?P<value>{_NUM})\s*(?:{re.escape(PLUS_MINUS)}|\+/-)\s*"
    rf"(?P<unc>{_NUM})\s*(?P<unit>\S.*)?$"
)
_SIMPLE_RE = re.compile(rf"^\s*(?P<value>{_NUM})\s*(?P<unit>\S.*)?$")


def _fmt_number(value: float) -> str:
    """Render *value* without a trailing ``.0`` (целые как целые)."""
    as_float = float(value)
    if as_float.is_integer():
        return str(int(as_float))
    return repr(as_float)


@dataclass(frozen=True)
class ParsedMeasurement:
    """Parsed parts of a canonical measurement string (§7.16).

    Fields
    ------
    kind
        ``"value"`` (single value) or ``"range"`` (диапазон).
    value
        The single value, or ``None`` for a range.
    low, high
        Range bounds, or ``None`` for a single value.
    unit
        Unit token, or ``None`` when unitless (без единицы).
    uncertainty
        The ``±`` uncertainty, or ``None`` when absent.
    """

    kind: str
    value: float | None
    low: float | None
    high: float | None
    unit: str | None
    uncertainty: float | None

    def as_dict(self) -> dict[str, object]:
        """Full structured view (all fields, including ``None``)."""
        return {
            "kind": self.kind,
            "value": self.value,
            "low": self.low,
            "high": self.high,
            "unit": self.unit,
            "uncertainty": self.uncertainty,
        }


def format_measurement(
    value: float | tuple[float, float] | list[float],
    unit: str | None = None,
    *,
    uncertainty: float | None = None,
) -> str:
    """Format one measurement into its canonical string (§7.16).

    ``value`` may be a scalar (``148``) or a 2-item range (``(200, 300)``). A
    range renders as ``"lo-hi unit"`` and ignores *uncertainty*. A scalar renders
    as ``"value unit"``, or ``"value ± unc unit"`` when *uncertainty* is given.
    A missing / empty *unit* is simply omitted (без единицы).
    """
    unit_str = "" if unit is None or not str(unit).strip() else str(unit).strip()
    suffix = f" {unit_str}" if unit_str else ""

    if isinstance(value, (tuple, list)):
        if len(value) != 2:
            raise ValueError("range value must have exactly 2 items")
        lo, hi = float(value[0]), float(value[1])
        return f"{_fmt_number(lo)}-{_fmt_number(hi)}{suffix}"

    head = _fmt_number(float(value))
    if uncertainty is not None:
        head = f"{head} {PLUS_MINUS} {_fmt_number(float(uncertainty))}"
    return f"{head}{suffix}"


def parse_back(s: str) -> dict[str, object]:
    """Parse a canonical measurement string back into its parts (§7.16).

    The exact inverse of :func:`format_measurement`: recognizes ranges
    (``"200-300 MPa"``), ``±`` uncertainty (``"148 ± 5 HV"`` and the ``+/-``
    ASCII spelling), and plain ``"value unit"``. Returns the
    :meth:`ParsedMeasurement.as_dict` mapping. Raises :class:`ValueError` on an
    unrecognizable string.
    """
    text = s.strip()

    range_match = _RANGE_RE.match(text)
    if range_match:
        unit = range_match.group("unit")
        return ParsedMeasurement(
            kind="range",
            value=None,
            low=float(range_match.group("lo")),
            high=float(range_match.group("hi")),
            unit=unit.strip() if unit else None,
            uncertainty=None,
        ).as_dict()

    unc_match = _UNCERTAIN_RE.match(text)
    if unc_match:
        unit = unc_match.group("unit")
        return ParsedMeasurement(
            kind="value",
            value=float(unc_match.group("value")),
            low=None,
            high=None,
            unit=unit.strip() if unit else None,
            uncertainty=float(unc_match.group("unc")),
        ).as_dict()

    simple_match = _SIMPLE_RE.match(text)
    if simple_match:
        unit = simple_match.group("unit")
        return ParsedMeasurement(
            kind="value",
            value=float(simple_match.group("value")),
            low=None,
            high=None,
            unit=unit.strip() if unit else None,
            uncertainty=None,
        ).as_dict()

    raise ValueError(f"unparseable measurement string: {s!r}")
