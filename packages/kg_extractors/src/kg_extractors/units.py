"""Unit normalization + numeric-constraint parsing (§7 / §24.4).

Handles the mining/metallurgy unit zoo in RU & EN (мг/л, мг/дм³, м³/ч, м/с, т/сут,
кВт·ч/т, А/м², мА/см², %, ppm, …), maps them to canonical SI-ish units via pint,
and parses conditions like «≤1000 мг/дм³», «200–300 мг/л», «<200 мг/л»,
«от 100 т/сут», «0.1–0.3 м/с».
"""

from __future__ import annotations

import functools
import re
import unicodedata
from dataclasses import dataclass

import pint

# Raw (lowercased, NFKC) unit token -> pint-parseable unit string.
UNIT_ALIASES: dict[str, str] = {
    # concentration (mg per volume): dm^3 == L
    "мг/л": "mg/L",
    "mg/l": "mg/L",
    "мг/дм3": "mg/L",
    "мг/дм³": "mg/L",
    "mg/dm3": "mg/L",
    "mg/dm^3": "mg/L",
    "г/л": "g/L",
    "g/l": "g/L",
    "мг/м3": "mg/m^3",
    "mg/m3": "mg/m^3",
    "мг/нм3": "mg/m^3",
    "mg/nm3": "mg/m^3",
    "мг/нм³": "mg/m^3",
    "г/дм3": "g/L",
    "kg/m3": "kg/m^3",
    "кг/м3": "kg/m^3",
    # flow rate
    "м3/ч": "m^3/hour",
    "m3/h": "m^3/hour",
    "м³/ч": "m^3/hour",
    "m3/hr": "m^3/hour",
    "л/мин": "L/min",
    "l/min": "L/min",
    "л/с": "L/s",
    "l/s": "L/s",
    # velocity
    "м/с": "m/s",
    "m/s": "m/s",
    "см/с": "cm/s",
    "cm/s": "cm/s",
    "м/сут": "m/day",
    # throughput
    "т/сут": "t/day",
    "t/day": "t/day",
    "т/ч": "t/hour",
    "t/h": "t/hour",
    "т/год": "t/year",
    "t/year": "t/year",
    "kg/t": "kg/t",
    "кг/т": "kg/t",
    # energy
    "квт·ч/т": "kW*hour/t",
    "квтч/т": "kW*hour/t",
    "kwh/t": "kW*hour/t",
    "квт·ч": "kW*hour",
    "kwh": "kW*hour",
    # current density
    "а/м2": "A/m^2",
    "a/m2": "A/m^2",
    "а/м²": "A/m^2",
    "a/m^2": "A/m^2",
    "ма/см2": "mA/cm^2",
    "ma/cm2": "mA/cm^2",
    "ма/см²": "mA/cm^2",
    # voltage
    "в": "V",
    "v": "V",
    "мв": "mV",
    "mv": "mV",
    # pressure
    "атм": "atm",
    "atm": "atm",
    "бар": "bar",
    "bar": "bar",
    "мпа": "MPa",
    "mpa": "MPa",
    "кпа": "kPa",
    "па": "Pa",
    # temperature
    "°c": "degC",
    "c": "degC",
    "°с": "degC",
    "к": "K",
    # dimensionless
    "%": "percent",
    "об.%": "percent",
    "%vol": "percent",
    "%об": "percent",
    "ppm": "ppm",
    "ppb": "ppb",
    "ratio": "ratio",
    "доли": "ratio",
    # length
    "м": "m",
    "mm": "mm",
    "мм": "mm",
    "мкм": "um",
    "нм": "nm",
}

# canonical unit for each pint dimensionality signature -> target
CANONICAL_BY_KIND: dict[str, str] = {
    "concentration_mass_vol": "mg/L",
    "flow_rate": "m^3/hour",
    "velocity": "m/s",
    "throughput": "t/day",
    "current_density": "A/m^2",
    "voltage": "V",
    "pressure": "bar",
    "temperature": "degC",
    "energy_intensity": "kW*hour/t",
    # NB: no 'fraction' entry — keep %, ppm, ppb, ratio as-is so ppm/ppb
    # magnitudes are preserved (100 ppm must not become 0.01 percent).
}

_NUM = r"[-+]?\d+(?:[.,]\d+)?"
_OPS = {
    "≤": "<=",
    "⩽": "<=",
    "≥": ">=",
    "⩾": ">=",
    "<": "<",
    ">": ">",
    "≈": "approx",
    "~": "approx",
}


@functools.lru_cache(maxsize=1)
def _registry() -> pint.UnitRegistry:
    ureg = pint.UnitRegistry()
    ureg.define("percent = 0.01 = %")
    ureg.define("ppm = 1e-6")
    ureg.define("ppb = 1e-9")
    ureg.define("ratio = []")
    ureg.define("ton = 1000 * kilogram = t")
    return ureg


def normalize_unit_token(raw: str) -> str | None:
    """Map a raw unit token to a pint-parseable unit string (or None)."""
    if not raw:
        return None
    s = unicodedata.normalize("NFKC", raw).strip().lower()
    s = s.replace(" ", "").replace("·", "·")
    if s in UNIT_ALIASES:
        return UNIT_ALIASES[s]
    # try pint directly
    try:
        _registry().Unit(raw)
        return raw
    except Exception:
        return None


def _kind(unit_str: str) -> str | None:
    ureg = _registry()
    try:
        q = ureg.Quantity(1, unit_str)
    except Exception:
        return None
    dim = q.dimensionality
    checks = {
        "concentration_mass_vol": "[mass] / [length] ** 3",
        "flow_rate": "[length] ** 3 / [time]",
        "velocity": "[length] / [time]",
        "current_density": "[current] / [length] ** 2",
        # volt = M·L²·T⁻³·I⁻¹ (current in the DENOMINATOR)
        "voltage": "[mass] * [length] ** 2 / [current] / [time] ** 3",
        "pressure": "[mass] / [length] / [time] ** 2",
        "temperature": "[temperature]",
    }
    for kind, sig in checks.items():
        try:
            if dim == ureg.get_dimensionality(sig):
                return kind
        except Exception:
            continue
    if "t/day" in unit_str or "t/hour" in unit_str or "t/year" in unit_str:
        return "throughput"
    if str(unit_str) in {"percent", "ppm", "ppb", "ratio"}:
        return "fraction"
    if "kW" in unit_str and "/t" in unit_str:
        return "energy_intensity"
    return None


@dataclass
class Normalized:
    value: float
    unit: str
    method: str = "pint"


def to_canonical(value: float, raw_unit: str | None) -> Normalized | None:
    """Normalize a value+unit to its canonical unit; None if unit unknown."""
    if raw_unit is None:
        return None
    pu = normalize_unit_token(raw_unit)
    if pu is None:
        return None
    kind = _kind(pu)
    target = CANONICAL_BY_KIND.get(kind) if kind else None
    ureg = _registry()
    try:
        q = ureg.Quantity(value, pu)
        if target:
            q = q.to(target)
            return Normalized(float(q.magnitude), target)
        return Normalized(float(q.magnitude), str(q.units))
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Numeric-constraint parsing
# ---------------------------------------------------------------------------
_UNIT_RE = (
    r"(мг/дм³|мг/дм3|мг/л|мг/нм³|мг/нм3|мг/м3|г/л|г/дм3|м³/ч|м3/ч|м/с|см/с|л/мин|л/с|"
    r"т/сут|т/ч|т/год|кг/т|квт·ч/т|квтч/т|а/м²|а/м2|ма/см²|ма/см2|°c|°с|мпа|бар|атм|"
    r"мв|мм|мкм|нм|%об|%|ppm|ppb|mg/l|mg/dm3|g/l|m3/h|m/s|cm/s|t/day|kg/t|kwh/t|"
    r"a/m2|ma/cm2|degc|mpa|bar|atm|mv)"
)
# A unit token must not be the prefix of a longer word (e.g. "к" of "кг",
# "м" of "минут"): require a non-word char after it. Fixes fabricated measurements.
_UNIT_BOUNDARY = r"(?![а-яёa-zа-я0-9])"


@dataclass
class ParsedConstraint:
    operator: str
    value: float | None = None
    min: float | None = None
    max: float | None = None
    unit: str | None = None
    normalized_value: float | None = None
    normalized_min: float | None = None
    normalized_max: float | None = None
    normalized_unit: str | None = None
    source_span: str = ""

    def as_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v is not None}


def _f(x: str) -> float:
    return float(x.replace(",", ".").replace("+", ""))


def parse_numeric_constraints(text: str) -> list[ParsedConstraint]:
    """Extract numeric conditions (ranges / inequalities / single values)."""
    if not text:
        return []
    t = unicodedata.normalize("NFKC", text)
    out: list[ParsedConstraint] = []
    seen: set[str] = set()
    covered: list[tuple[int, int]] = []  # char spans already consumed by range/ineq

    def add(pc: ParsedConstraint, span: tuple[int, int] | None = None) -> None:
        key = pc.source_span.strip().lower()
        if key and key not in seen:
            seen.add(key)
            _attach_norm(pc)
            out.append(pc)
            if span:
                covered.append(span)

    def overlaps(a: int, b: int) -> bool:
        return any(not (b <= s or a >= e) for s, e in covered)

    # range: "200–300 мг/л" / "0.1-0.3 м/с" / "от 100 до 300 т/сут".
    # Unit is REQUIRED so hyphenated year pairs ("2015-2020") are not parsed as ranges.
    range_re = re.compile(
        rf"(?:от\s*)?({_NUM})\s*(?:–|—|-|\.\.|до|to)\s*({_NUM})\s*{_UNIT_RE}{_UNIT_BOUNDARY}",
        re.IGNORECASE,
    )
    for m in range_re.finditer(t):
        lo, hi = _f(m.group(1)), _f(m.group(2))
        add(
            ParsedConstraint(
                "range",
                min=min(lo, hi),
                max=max(lo, hi),
                unit=m.group(3),
                source_span=m.group(0).strip(),
            ),
            m.span(),
        )

    # inequality: "≤1000 мг/дм³", "<200 мг/л", "от 100 т/сут"
    ineq_re = re.compile(
        rf"(≤|⩽|≥|⩾|<|>|≈|~|не более|не менее|от|до|менее|более)\s*({_NUM})\s*{_UNIT_RE}?",
        re.IGNORECASE,
    )
    ru_ops = {
        "не более": "<=",
        "менее": "<",
        "до": "<=",
        "не менее": ">=",
        "более": ">",
        "от": ">=",
    }
    for m in ineq_re.finditer(t):
        if overlaps(*m.span()):
            continue
        raw_op = m.group(1).lower()
        op = _OPS.get(raw_op) or ru_ops.get(raw_op)
        if not op:
            continue
        add(
            ParsedConstraint(
                op, value=_f(m.group(2)), unit=m.group(3), source_span=m.group(0).strip()
            ),
            m.span(),
        )

    # bare "value + unit": "250 А/м²", "0.2 м/с", "95%" (unit REQUIRED + boundary)
    bare_re = re.compile(rf"({_NUM})\s*{_UNIT_RE}{_UNIT_BOUNDARY}", re.IGNORECASE)
    for m in bare_re.finditer(t):
        if overlaps(*m.span()):
            continue
        add(
            ParsedConstraint(
                "=", value=_f(m.group(1)), unit=m.group(2), source_span=m.group(0).strip()
            ),
            m.span(),
        )

    return out


def _attach_norm(pc: ParsedConstraint) -> None:
    if not pc.unit:
        return
    if pc.value is not None:
        norm = to_canonical(pc.value, pc.unit)
        if norm:
            pc.normalized_value, pc.normalized_unit = norm.value, norm.unit
    if pc.min is not None:
        lo = to_canonical(pc.min, pc.unit)
        hi = to_canonical(pc.max or pc.min, pc.unit)
        if lo and hi:
            pc.normalized_min, pc.normalized_max = lo.value, hi.value
            pc.normalized_unit = lo.unit
