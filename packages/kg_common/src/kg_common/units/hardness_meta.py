"""Hardness-conversion metadata + scale-spec parsing (§7.3).

Wraps :func:`kg_common.units.hardness.convert_hardness` with the provenance a
curator needs to trust (or distrust) a converted value: which *normalization
method* produced it (a rule/table, not a measurement), which *conversion
standard* the table follows (ASTM E140), and whether the input fell *outside*
the table domain — in which case the base converter clamps to the nearest
endpoint and we raise ``out_of_conversion_range`` so downstream logic can flag
the number as an extrapolation rather than a conversion.

Also parses free-text hardness designations (``"HBW 10/3000"``, ``"HV0.5"``,
``"HRC"``) into a structured scale + load — превращает строку-обозначение
твёрдости в разобранную шкалу и нагрузку.

Pure Python, no I/O. Builds **on** ``hardness`` (reuses ``convert_hardness`` and
its ASTM steel table) without modifying it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Reuse the base converter and its ASTM E140 steel table. The table constants are
# module-private in ``hardness`` but are the single source of truth for the
# conversion domain, so we derive the out-of-range check from them rather than
# duplicating the numbers here.
from kg_common.units.hardness import _COL, _TABLE, convert_hardness

CONVERSION_STANDARD = "ASTM E140"
NORMALIZATION_METHOD = "rule"

# Scale symbols that all denote Brinell (steel ball / tungsten-carbide ball).
_BRINELL_SYMBOLS = frozenset({"HB", "HBW", "HBS"})

# Leading letters = scale symbol; the remainder = optional load / indenter spec.
_SPEC_RE = re.compile(
    r"^\s*(?P<scale>H[A-Za-z]+)\s*(?P<load>[0-9][0-9.]*(?:/[0-9.]+)*)?\s*$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class HardnessConversion:
    """A hardness conversion with normalization provenance — §7.3.

    Distinct from ``hardness.HardnessConversion`` (which is the bare converted
    number): this record keeps *both* endpoints plus the metadata a reviewer
    needs — normalization method, conversion standard and the out-of-range flag.

    ``value_in``/``value_out`` are the numbers on ``from_scale``/``to_scale``;
    ``out_of_conversion_range`` is ``True`` when ``value_in`` lies outside the
    ASTM table domain for ``from_scale`` (the result is then clamped).
    """

    value_in: float
    from_scale: str
    to_scale: str
    value_out: float
    normalization_method: str = NORMALIZATION_METHOD
    conversion_standard: str = CONVERSION_STANDARD
    out_of_conversion_range: bool = False
    note: str = ""

    def as_dict(self) -> dict[str, object]:
        """JSON-friendly view — таблица «вход → выход + происхождение» (§7.3)."""
        return {
            "value_in": self.value_in,
            "from_scale": self.from_scale,
            "to_scale": self.to_scale,
            "value_out": self.value_out,
            "normalization_method": self.normalization_method,
            "conversion_standard": self.conversion_standard,
            "out_of_conversion_range": self.out_of_conversion_range,
            "note": self.note,
        }


@dataclass(frozen=True)
class HardnessSpec:
    """Parsed hardness designation — шкала и (опционально) нагрузка (§7.3).

    ``scale`` is the normalized scale (``"HV"``, ``"HB"``, ``"HRC"`` …).
    ``load`` is a numeric test load in kgf (Vickers/Knoop, e.g. ``0.5``);
    ``indenter_load`` is a Brinell-style ``ball/force`` string (e.g.
    ``"10/3000"``) that is not a single number. At most one of the two is set.
    """

    scale: str
    load: float | None = None
    indenter_load: str | None = None

    def as_dict(self) -> dict[str, object]:
        """Minimal view — только заданные поля (§7.3)."""
        out: dict[str, object] = {"scale": self.scale}
        if self.load is not None:
            out["load"] = self.load
        if self.indenter_load is not None:
            out["indenter_load"] = self.indenter_load
        return out


def _scale_domain(scale: str) -> tuple[float, float]:
    """Min/max value defined for *scale* in the ASTM steel table — область (§7.3)."""
    col = _COL[scale]
    vals = [row[col] for row in _TABLE if row[col] is not None]
    return min(vals), max(vals)  # type: ignore[type-var]


def convert_with_metadata(value: float, from_scale: str, to_scale: str) -> HardnessConversion:
    """Convert hardness and attach normalization metadata (§7.3).

    Delegates the arithmetic to :func:`convert_hardness` (steel, ASTM E140) and
    records where the number came from. Raises ``ValueError`` for unsupported
    scales (propagated from the base converter). Sets
    ``out_of_conversion_range=True`` when *value* is outside the table domain of
    *from_scale* — the returned ``value_out`` is then clamped to the endpoint.
    """
    base = convert_hardness(value, from_scale, to_scale)  # validates scales + converts
    fs = from_scale.upper()
    low, high = _scale_domain(fs)
    out_of_range = value < low or value > high
    return HardnessConversion(
        value_in=float(value),
        from_scale=fs,
        to_scale=to_scale.upper(),
        value_out=base.value,
        out_of_conversion_range=out_of_range,
        note=base.note,
    )


def _normalize_scale(symbol: str) -> str:
    """Fold scale synonyms — HBW/HBS/HB → HB, иначе как есть (§7.3)."""
    sym = symbol.upper()
    if sym in _BRINELL_SYMBOLS:
        return "HB"
    return sym


def parse_hardness_spec(text: str) -> HardnessSpec:
    """Parse a hardness designation string into scale + load (§7.3).

    ``"HBW 10/3000"`` → ``HardnessSpec("HB", indenter_load="10/3000")``,
    ``"HV0.5"`` → ``HardnessSpec("HV", load=0.5)``,
    ``"HRC"`` → ``HardnessSpec("HRC")``. A trailing token containing ``/`` is a
    Brinell-style ``ball/force`` designation; a plain number is a kgf test load.
    Raises ``ValueError`` when *text* is not a recognizable designation.
    """
    match = _SPEC_RE.match(text)
    if match is None:
        raise ValueError(f"unrecognized hardness spec: {text!r}")
    scale = _normalize_scale(match.group("scale"))
    raw_load = match.group("load")
    if not raw_load:
        return HardnessSpec(scale)
    if "/" in raw_load:
        return HardnessSpec(scale, indenter_load=raw_load)
    return HardnessSpec(scale, load=float(raw_load))
