"""Measurement linker → MeasurementExtract (§6.6).

Ties each controlled ``property_id`` mention (see
:mod:`kg_extractors.property_extractor`) to its measured value + unit, the
baseline it was compared against, the effect direction implied by cue words,
and the measurement method — producing one :class:`MeasurementExtract` per
mention (связывание свойства со значением, единицей, эффектом и методом).

Association is proximity-based: a mention is linked to the **nearest** numeric
value+unit (excluding any value that reads as a baseline, e.g. «from 90 HV»).
Units are checked against the property's ``allowed_units`` (§7.2) — reusing
:mod:`kg_extractors.property_vocab` and :mod:`kg_extractors.units` — and a
``unit_property_mismatch`` flag is raised when they disagree (напр. твёрдость
в МПа). No numeric value nearby ⇒ ``value``/``unit`` stay ``None``.

Pure python + the read-only vocab/units modules — no other dependency.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass

from kg_extractors.property_extractor import PropertyMention
from kg_extractors.property_vocab import default_property_vocab
from kg_extractors.units import UNIT_ALIASES, normalize_unit_token

# Effect-direction tokens (§6.6): the controlled set stored on the extract.
EFFECT_INCREASE = "increase"
EFFECT_DECREASE = "decrease"
EFFECT_NO_CHANGE = "no_change"

_NUMBER = re.compile(r"[-+]?\d+(?:[.,]\d+)?")

# Effect cues — RU/EN. Russian verbs matched by stem (повыс\w* → повысил/повысилась).
_INCREASE_RE = re.compile(
    r"\b(?:increase[ds]?|increasing|rose|risen|grew|повыс\w*|увелич\w*|возрос\w*|вырос\w*)\b",
    re.IGNORECASE,
)
_DECREASE_RE = re.compile(
    r"\b(?:decrease[ds]?|decreasing|drop(?:ped|s)?|f[ae]ll|reduc\w*|сниз\w*|пониз\w*|уменьш\w*|упал\w*)\b",
    re.IGNORECASE,
)
_NO_CHANGE_RE = re.compile(
    r"(?:no\s+change|unchanged|no\s+effect|remained\s+(?:the\s+same|unchanged)|"
    r"без\s+изменен\w*|не\s+измен\w*)",
    re.IGNORECASE,
)

# Baseline cues — the value the measurement was compared *from* (§6.6). Kept
# strong/explicit only: a bare «was» is not a baseline («hardness was 148 HV»).
_BASELINE_RE = re.compile(
    r"(?:\bfrom\b|\bот\b|\bбыло\b|\binitially\b)\s*([-+]?\d+(?:[.,]\d+)?)",
    re.IGNORECASE,
)

# Measurement-method vocabulary (§6.6). HRTEM is listed before TEM so the more
# specific instrument wins; each surface (RU/EN) maps to its canonical name.
_METHOD_RE: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bhr-?tem\b", re.IGNORECASE), "HRTEM"),
    (re.compile(r"\bvickers\b|виккерс\w*", re.IGNORECASE), "Vickers"),
    (re.compile(r"\bxrd\b|\bрфа\b|рентгенофазов\w*|рентгеноструктур\w*", re.IGNORECASE), "XRD"),
    (re.compile(r"\bsem\b|\bрэм\b", re.IGNORECASE), "SEM"),
    (re.compile(r"\btem\b", re.IGNORECASE), "TEM"),
    (re.compile(r"\btensile\b|растяжен\w*", re.IGNORECASE), "tensile"),
]


def _fold(s: object) -> str:
    """Fold a unit token for comparison: NFKC + strip + lowercase."""
    return unicodedata.normalize("NFKC", str(s)).strip().lower()


def _build_known_units() -> frozenset[str]:
    """Recognized unit surfaces (folded): vocab ``allowed_units`` + raw unit aliases."""
    known: set[str] = {"hv", "hb", "hrc"}
    vocab = default_property_vocab()
    for pid in vocab.all_ids():
        for unit in vocab.allowed_units(pid):
            known.add(_fold(unit))
    for alias in UNIT_ALIASES:
        known.add(_fold(alias))
    return frozenset(known)


_KNOWN_UNITS = _build_known_units()


@dataclass(frozen=True)
class MeasurementExtract:
    """One property↔value↔unit link with baseline/effect/method (§6.6).

    Fields
    ------
    property_id
        Canonical ``prop:*`` id the measurement describes.
    value
        Nearest numeric value linked to the mention (``None`` if none nearby).
    unit
        Raw unit surface for that value (``None`` ⇒ unitless / not found).
    baseline_value
        The «from …» value the measurement was compared against (or ``None``).
    effect_direction
        One of ``increase`` / ``decrease`` / ``no_change`` — or ``None`` when no
        cue word is present (направление эффекта).
    method
        Canonical measurement method (``Vickers`` / ``XRD`` / ``SEM`` / ``TEM`` /
        ``HRTEM`` / ``tensile``) or ``None``.
    source_span
        The text slice spanning the mention and its linked value/baseline.
    unit_property_mismatch
        ``True`` when *unit* is not among the property's ``allowed_units`` (§7.2).
    """

    property_id: str | None
    value: float | None
    unit: str | None
    baseline_value: float | None
    effect_direction: str | None
    method: str | None
    source_span: str
    unit_property_mismatch: bool = False

    def as_dict(self) -> dict[str, object]:
        """Full structured view (all fields, including ``None``)."""
        return {
            "property_id": self.property_id,
            "value": self.value,
            "unit": self.unit,
            "baseline_value": self.baseline_value,
            "effect_direction": self.effect_direction,
            "method": self.method,
            "source_span": self.source_span,
            "unit_property_mismatch": self.unit_property_mismatch,
        }


def _unit_after(text: str, num_end: int) -> tuple[str | None, int]:
    """Recognize a unit token right after a number; return ``(surface, end)``.

    ``surface`` is the original-case token (``None`` when the following token is
    not a known unit); ``end`` is the absolute offset past the token (или
    ``num_end`` when nothing was consumed).
    """
    m = re.match(r"\s*(\S+)", text[num_end:])
    if not m:
        return None, num_end
    surface = m.group(1).strip("()[]{}.,;:")
    if surface and _fold(surface) in _KNOWN_UNITS:
        return surface, num_end + m.end(1)
    return None, num_end


def _scan_numbers(text: str) -> list[tuple[float, int, int, str | None]]:
    """Return ``(value, start, end, unit)`` for each number+unit in *text*.

    Digits that belong to a unit exponent (``m^2``, ``N/mm2``) — i.e. preceded by
    a letter / ``^`` / ``/`` / ``·`` — are skipped so they are not read as values.
    ``end`` spans the unit when one is attached.
    """
    out: list[tuple[float, int, int, str | None]] = []
    for m in _NUMBER.finditer(text):
        start, end = m.span()
        if start > 0 and (text[start - 1] in "^/·" or text[start - 1].isalpha()):
            continue
        value = float(m.group(0).replace(",", ".").replace("+", ""))
        unit, full_end = _unit_after(text, end)
        out.append((value, start, full_end, unit))
    return out


def _interval_distance(a: tuple[int, int], b: tuple[int, int]) -> int:
    """Character gap between two ``[start, end)`` intervals (0 if they overlap)."""
    (a0, a1), (b0, b1) = a, b
    if a1 <= b0:
        return b0 - a1
    if b1 <= a0:
        return a0 - b1
    return 0


def _find_baseline(text: str, span: tuple[int, int]) -> tuple[float, int] | None:
    """Nearest «from …» baseline value to *span*; ``(value, num_start)`` or ``None``."""
    best: tuple[float, int] | None = None
    best_d: int | None = None
    for m in _BASELINE_RE.finditer(text):
        num_span = m.span(1)
        d = _interval_distance(span, num_span)
        if d <= 200 and (best_d is None or d < best_d):
            best_d = d
            best = (float(m.group(1).replace(",", ".").replace("+", "")), num_span[0])
    return best


def _detect_direction(text: str, span: tuple[int, int]) -> str | None:
    """Effect direction from cue words in a window around *span* (earliest wins)."""
    lo = max(0, span[0] - 60)
    hi = min(len(text), span[1] + 140)
    window = text[lo:hi]
    hits: list[tuple[int, str]] = []
    for pat, direction in (
        (_NO_CHANGE_RE, EFFECT_NO_CHANGE),
        (_INCREASE_RE, EFFECT_INCREASE),
        (_DECREASE_RE, EFFECT_DECREASE),
    ):
        m = pat.search(window)
        if m:
            hits.append((m.start(), direction))
    if not hits:
        return None
    hits.sort()
    return hits[0][1]


def _detect_method(text: str) -> str | None:
    """Canonical measurement method named in *text* (HRTEM before TEM), or ``None``."""
    for pat, name in _METHOD_RE:
        if pat.search(text):
            return name
    return None


def _unit_mismatch(property_id: str | None, unit: str | None) -> bool:
    """``True`` when *unit* is not allowed for *property_id* (§7.2).

    A fold (NFKC/lower) match is tried first; a pint-normalized comparison is the
    fallback so ``А/м²`` matches ``A/m^2``. Unknown property or absent unit ⇒
    never a mismatch.
    """
    if not unit or not property_id:
        return False
    allowed = default_property_vocab().allowed_units(property_id)
    if not allowed:
        return False
    if _fold(unit) in {_fold(a) for a in allowed}:
        return False
    norm = normalize_unit_token(unit)
    if norm is not None:
        for a in allowed:
            na = normalize_unit_token(a)
            if na is not None and na == norm:
                return False
    return True


def link_measurements(
    text: str,
    property_mentions: Sequence[PropertyMention],
) -> list[MeasurementExtract]:
    """Link each property mention to its measurement, in mention order (§6.6).

    For every mention in *property_mentions* the nearest numeric value+unit in
    *text* is attached (excluding a value read as a baseline), together with the
    baseline value, the effect direction (cue words), the method (small vocab)
    and a ``unit_property_mismatch`` flag. Mentions expose ``property_id`` and a
    ``span`` ``(start, end)`` — as produced by
    :func:`kg_extractors.property_extractor.extract_properties`.
    """
    if not text or not property_mentions:
        return []

    numbers = _scan_numbers(text)
    method = _detect_method(text)
    out: list[MeasurementExtract] = []

    for mention in property_mentions:
        span = getattr(mention, "span", None)
        if span is None:
            continue
        property_id = getattr(mention, "property_id", None)

        base = _find_baseline(text, span)
        baseline_value = base[0] if base else None
        baseline_start = base[1] if base else None

        # nearest value+unit, never the baseline number itself.
        best: tuple[float, int, int, str | None] | None = None
        best_d: int | None = None
        for value, start, end, unit in numbers:
            if baseline_start is not None and start == baseline_start:
                continue
            d = _interval_distance(span, (start, end))
            if best_d is None or d < best_d:
                best_d = d
                best = (value, start, end, unit)

        if best is not None:
            value, v_start, v_end, unit = best
            spans = [span, (v_start, v_end)]
        else:
            value, unit = None, None
            spans = [span]
        if base is not None:
            spans.append((baseline_start, baseline_start))

        lo = min(s for s, _ in spans)
        hi = max(e for _, e in spans)
        out.append(
            MeasurementExtract(
                property_id=property_id,
                value=value,
                unit=unit,
                baseline_value=baseline_value,
                effect_direction=_detect_direction(text, span),
                method=method,
                source_span=text[lo:hi],
                unit_property_mismatch=_unit_mismatch(property_id, unit),
            )
        )
    return out
