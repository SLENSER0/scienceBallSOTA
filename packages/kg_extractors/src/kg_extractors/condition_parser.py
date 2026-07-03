"""Measurement-condition parser: free-text → structured context (§6.6).

``MeasurementExtract.condition`` (§6.6 property vocabulary) is a free-text
string such as «in air at 200 °C after 1000 cycles». Downstream ranking and
dedup need the measurement CONTEXT as structured fields, not prose. This rule
turns that free text (RU + EN cues) into a small frozen record:

* ``temperature_c`` — the test temperature in °C. Kelvin cues («300 K») are
  converted (``K − 273.15``, rounded to 2 dp); «room temperature»/«RT»/«комн»
  map to a nominal 25.0 °C; explicit «°C» is taken as-is.
* ``environment`` — ``air`` / ``vacuum`` / ``inert`` (argon, nitrogen and
  «инерт*» collapse to ``inert``).
* ``cycles`` — fatigue/thermal cycle count («after 1000 cycles»).
* ``n_samples`` — specimen count («n=5», «5 specimens», «5 образцов»).

Every field is ``None`` when its cue is absent, so an empty string yields an
all-``None`` record (``raw == ''``). Custom node props are read via
``get_node()`` — they are not Kuzu-queryable columns (§ Kuzu note).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Nominal room temperature in °C for «room temperature» / «RT» / «комнатн» cues.
_ROOM_TEMPERATURE_C = 25.0

# Absolute-zero offset for the Kelvin → Celsius conversion (K − 273.15).
_KELVIN_OFFSET = 273.15

# Explicit Celsius: a number followed by an optional degree sign and a literal
# uppercase «C» at a word boundary («200 °C», «200C»). Case-sensitive so that
# «1000 cycles» never reads the leading «c» of «cycles» as a unit.
_CELSIUS_RE = re.compile(r"(-?\d+(?:\.\d+)?)\s*°?\s*C\b")

# Kelvin: a number followed by a literal uppercase «K» at a word boundary.
_KELVIN_RE = re.compile(r"(-?\d+(?:\.\d+)?)\s*K\b")

# «room temperature» (EN) or «комнатн…» (RU); IGNORECASE for the prose form.
_ROOM_RE = re.compile(r"\broom\s+temperature\b|комнатн", re.IGNORECASE)

# «RT» as a standalone token — case-sensitive so it is not matched inside words.
_RT_RE = re.compile(r"\bRT\b")

# Environment cues (RU + EN) → canonical id. Order is irrelevant; each is a
# disjoint surface set. Argon / nitrogen / «инерт…» all collapse to ``inert``.
_ENVIRONMENT_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("vacuum", re.compile(r"\bvacuum\b|вакуум", re.IGNORECASE)),
    ("inert", re.compile(r"\binert\b|\bargon\b|\bnitrogen\b|инерт|аргон|азот", re.IGNORECASE)),
    ("air", re.compile(r"\bair\b|воздух", re.IGNORECASE)),
]

# «after 1000 cycles» / «1000 циклов» — captures the integer cycle count.
_CYCLES_RE = re.compile(r"(\d+)\s*(?:cycles?|цикл)", re.IGNORECASE)

# Specimen count: «n=5» / «N = 5» (case-insensitive «n») …
_N_EQUALS_RE = re.compile(r"\bn\s*=\s*(\d+)", re.IGNORECASE)
# … or «5 specimens» / «5 образц…» when no «n=» form is present.
_SPECIMENS_RE = re.compile(r"(\d+)\s*(?:specimens?|samples?|образц)", re.IGNORECASE)


@dataclass(frozen=True)
class MeasurementCondition:
    """Structured measurement context parsed from a free-text condition (§6.6).

    Each field is ``None`` when the corresponding cue is absent from ``raw``.
    ``temperature_c`` is always expressed in °C (Kelvin cues are converted).
    """

    temperature_c: float | None
    environment: str | None
    cycles: int | None
    n_samples: int | None
    raw: str

    def as_dict(self) -> dict[str, object]:
        return {
            "temperature_c": self.temperature_c,
            "environment": self.environment,
            "cycles": self.cycles,
            "n_samples": self.n_samples,
            "raw": self.raw,
        }


def _parse_temperature(text: str) -> float | None:
    """Return the test temperature in °C, or ``None`` when no cue is present.

    Precedence: explicit «°C» → «K» (converted) → «room temperature»/«RT».
    """
    m = _CELSIUS_RE.search(text)
    if m is not None:
        return float(m.group(1))
    m = _KELVIN_RE.search(text)
    if m is not None:
        return round(float(m.group(1)) - _KELVIN_OFFSET, 2)
    if _ROOM_RE.search(text) or _RT_RE.search(text):
        return _ROOM_TEMPERATURE_C
    return None


def _parse_environment(text: str) -> str | None:
    """Return the canonical environment (``air``/``vacuum``/``inert``) or ``None``."""
    for name, pattern in _ENVIRONMENT_PATTERNS:
        if pattern.search(text):
            return name
    return None


def _parse_int(pattern: re.Pattern[str], text: str) -> int | None:
    """Return the first integer captured by ``pattern`` in ``text``, or ``None``."""
    m = pattern.search(text)
    return int(m.group(1)) if m is not None else None


def parse_condition(text: str) -> MeasurementCondition:
    """Parse a free-text measurement condition (RU + EN) into structured fields.

    An empty / cue-less string yields an all-``None`` record whose ``raw``
    echoes the input (``''`` for empty). See the module docstring for the
    recognised cue surfaces.
    """
    raw = text or ""
    n_samples = _parse_int(_N_EQUALS_RE, raw)
    if n_samples is None:
        n_samples = _parse_int(_SPECIMENS_RE, raw)
    return MeasurementCondition(
        temperature_c=_parse_temperature(raw),
        environment=_parse_environment(raw),
        cycles=_parse_int(_CYCLES_RE, raw),
        n_samples=n_samples,
        raw=raw,
    )
