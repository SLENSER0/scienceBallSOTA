"""Multi-step processing-regime decomposition (§6.5).

Splits a prose processing description (RU/EN) into ORDERED, individually
parameterized steps. A single sentence like «solution treated at 500 °C then
aged at 180 °C for 2 h» / «плавка при 1200 °C, затем электроэкстракция при
60 °C» is broken on sequence markers ("затем"/"then"/"после"/","/"->"/…) into
:class:`ProcessingStep` records — each carrying its own operation keyword and the
temperature / time / atmosphere / cooling-rate stated nearest to it, with a
contiguous ``step_index`` (0..n) and an evidence ``source_span``.

Reuse (nothing here is edited): the operation surfaces come from
``processing_extractor._METHODS`` + ``processing_vocab.default_processing_vocab``;
the temperature regex + number parser from ``processing_extractor`` and the
number token ``units._NUM`` drive parameter capture. Feeds the ordered
``ProcessingRegime`` → ``ProcessingStep`` graph shape (§3.5). Custom step props
are read via ``get_node()`` — they are not Kuzu-queryable columns.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

from kg_extractors.processing_extractor import _METHODS, _PARAM_PATTERNS, _num
from kg_extractors.processing_vocab import default_processing_vocab
from kg_extractors.units import _NUM

# Reused temperature detector (number + °C / град / deg C, RU+EN) from §6.5.
_TEMP_RE = dict(_PARAM_PATTERNS)["temperature_c"]

# Sequence markers that separate ORDERED processing steps (RU + EN). The bare
# comma is guarded by ``(?<!\d)`` so decimal commas ("2,5 ч") never split a step.
_MARKER_RE = re.compile(
    r"->|→|;|(?<!\d),|\bзатем\b|\bпотом\b|\bпосле\s+чего\b|\bпосле\b|"
    r"\bс\s+последующ\w*|\bthen\b|\bfollowed\s+by\b|\bthereafter\b|"
    r"\bsubsequently\b|\bafter\s+which\b",
    re.IGNORECASE,
)

# Duration with a captured unit so we can normalize to hours (RU + EN).
_TIME_RE = re.compile(
    rf"({_NUM})\s*(ч\b|час\w*|h\b|hours?\b|hrs?\b|мин\b|минут\w*|min\b|minutes?\b)",
    re.IGNORECASE,
)

# Cooling rate: "2 °C/min" / "5 K/s" / "10 °C/мин" (value + per-time unit).
_COOL_RE = re.compile(
    rf"({_NUM})\s*°?\s*(?:C|С|K|К)\s*/\s*(мин|min|sec|s\b|с\b|h\b|ч\b)",
    re.IGNORECASE,
)

# Operation surfaces absent from the vocab/stems: participles + heat-treatment
# verbs common in multi-step regimes. Canonical ids extend the vocab set (§6.5).
_EXTRA_OP_KEYWORDS: dict[str, str] = {
    "solution treated": "solution_treatment",
    "solution-treated": "solution_treatment",
    "solution treatment": "solution_treatment",
    "solutionizing": "solution_treatment",
    "solutionising": "solution_treatment",
    "закалка на твёрдый раствор": "solution_treatment",
    "закалка на твердый раствор": "solution_treatment",
    "обработка на твёрдый раствор": "solution_treatment",
    "aged": "aging",
    "ageing": "aging",
    "состарен": "aging",
    "annealed": "annealing",
    "quenched": "quenching",
    "quench": "quenching",
    "roasted": "roasting",
    "smelted": "smelting",
    "leached": "leaching",
    "homogenized": "homogenization",
    "homogenised": "homogenization",
    "homogenization": "homogenization",
    "homogenisation": "homogenization",
    "гомогенизац": "homogenization",
    "tempered": "tempering",
    "tempering": "tempering",
    "отпуск": "tempering",
}

# Atmosphere surfaces -> canonical gas (RU stems + EN words).
_ATMOSPHERE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("argon", re.compile(r"\bargon\b|аргон", re.IGNORECASE)),
    ("nitrogen", re.compile(r"\bnitrogen\b|азот", re.IGNORECASE)),
    ("hydrogen", re.compile(r"\bhydrogen\b|водород", re.IGNORECASE)),
    ("vacuum", re.compile(r"\bvacuum\b|вакуум", re.IGNORECASE)),
    ("oxygen", re.compile(r"\boxygen\b|кислород", re.IGNORECASE)),
    ("air", re.compile(r"\bair\b|воздух", re.IGNORECASE)),
    ("inert", re.compile(r"\binert\b|инертн", re.IGNORECASE)),
]

_CYRILLIC = set("абвгдеёжзийклмнопрстуфхцчшщъыьэюя")

# (operation, temperature_c, time_h, atmosphere, cooling_rate) parsed from a step.
_Parsed = tuple[str | None, float | None, float | None, str | None, float | None]
# ``_Parsed`` plus the step's source span.
_Collected = tuple[str | None, float | None, float | None, str | None, float | None, str]


@dataclass(frozen=True)
class ProcessingStep:
    """One ordered step of a decomposed processing regime (§6.5).

    ``temperature_c`` is °C, ``time_h`` is hours, ``cooling_rate`` is °C/min.
    ``operation`` is a canonical operation id (or ``None`` if none is stated).
    """

    step_index: int
    operation: str | None
    temperature_c: float | None
    time_h: float | None
    atmosphere: str | None
    cooling_rate: float | None
    source_span: str

    def as_dict(self) -> dict[str, object]:
        return {
            "step_index": self.step_index,
            "operation": self.operation,
            "temperature_c": self.temperature_c,
            "time_h": self.time_h,
            "atmosphere": self.atmosphere,
            "cooling_rate": self.cooling_rate,
            "source_span": self.source_span,
        }


@lru_cache(maxsize=1)
def _op_keywords() -> tuple[tuple[str, str], ...]:
    """Operation surface -> canonical id, reusing stems + vocab + extras (§6.5)."""
    kw: dict[str, str] = {}
    for stem, canon in _METHODS.items():
        kw.setdefault(stem.lower(), canon)
    vocab = default_processing_vocab()
    for oid in vocab.all_ids():
        entry = vocab.entry(oid)
        if entry is None:
            continue
        for surface in (entry.canonical_ru, entry.canonical_en, *entry.synonyms):
            key = surface.strip().lower()
            if len(key) >= 3:  # skip 2-char acronyms (EW/RO/NF/ЭД) to avoid noise
                kw.setdefault(key, oid)
    for key, oid in _EXTRA_OP_KEYWORDS.items():
        kw[key.lower()] = oid
    return tuple(kw.items())


def _is_cyrillic(s: str) -> bool:
    return any(c in _CYRILLIC for c in s)


def _kw_index(low: str, kw: str) -> int | None:
    """First index of *kw* in lowercased *low* (cyr = stem substring; lat = word)."""
    if _is_cyrillic(kw):
        i = low.find(kw)
        return i if i >= 0 else None
    m = re.search(rf"(?<![a-z0-9]){re.escape(kw)}(?![a-z0-9])", low)
    return m.start() if m else None


def _find_operation(segment: str) -> str | None:
    """Leftmost operation keyword in *segment* (longest wins on a tie)."""
    low = segment.lower()
    best: tuple[int, int, str] | None = None
    for kw, oid in _op_keywords():
        i = _kw_index(low, kw)
        if i is None:
            continue
        cand = (i, -len(kw), oid)
        if best is None or cand[:2] < best[:2]:
            best = cand
    return best[2] if best else None


def _find_atmosphere(segment: str) -> str | None:
    """Leftmost gas/atmosphere mentioned in *segment*, or ``None``."""
    best: tuple[int, str] | None = None
    for gas, pat in _ATMOSPHERE_PATTERNS:
        m = pat.search(segment)
        if m and (best is None or m.start() < best[0]):
            best = (m.start(), gas)
    return best[1] if best else None


def _first_temperature(text: str) -> float | None:
    m = _TEMP_RE.search(text)
    return _num(m.group(1)) if m else None


def _parse_time_h(text: str) -> float | None:
    """First duration in *text*, normalized to hours (minutes -> /60)."""
    m = _TIME_RE.search(text)
    if not m:
        return None
    val = _num(m.group(1))
    unit = m.group(2).lower()
    if unit.startswith(("мин", "min")):
        return val / 60.0
    return val


def _parse_cooling(text: str) -> tuple[float | None, list[tuple[int, int]]]:
    """First cooling rate in *text* as °C/min, plus its span(s) to mask."""
    m = _COOL_RE.search(text)
    if not m:
        return None, []
    val = _num(m.group(1))
    per = m.group(2).lower()
    if per in ("s", "с", "sec"):
        val *= 60.0  # per second -> per minute
    elif per in ("h", "ч"):
        val /= 60.0  # per hour -> per minute
    return val, [m.span()]


def _mask_spans(text: str, spans: list[tuple[int, int]]) -> str:
    """Blank out *spans* so a cooling rate's "°C" is not read as a temperature."""
    if not spans:
        return text
    chars = list(text)
    for s, e in spans:
        for i in range(s, e):
            chars[i] = " "
    return "".join(chars)


def _segments(text: str) -> list[tuple[int, int]]:
    """Non-empty ``(start, end)`` slices of *text* split on sequence markers."""
    out: list[tuple[int, int]] = []
    prev = 0
    for m in _MARKER_RE.finditer(text):
        out.append((prev, m.start()))
        prev = m.end()
    out.append((prev, len(text)))
    return [(s, e) for s, e in out if text[s:e].strip()]


def _group(text: str, segments: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Group segments into steps: each operation starts one; param-only clauses
    merge into the current step."""
    groups: list[list[int]] = []
    for s, e in segments:
        if _find_operation(text[s:e]) is not None:
            groups.append([s, e])
        elif groups:
            groups[-1][1] = e  # parameter-only clause -> extend current step
        else:
            groups.append([s, e])  # leading param-only clause (kept only if content)
    return [(s, e) for s, e in groups]


def _extract_step(span_text: str) -> _Parsed:
    cooling, cool_spans = _parse_cooling(span_text)
    masked = _mask_spans(span_text, cool_spans)
    operation = _find_operation(span_text)
    temperature_c = _first_temperature(masked)
    time_h = _parse_time_h(masked)
    atmosphere = _find_atmosphere(span_text)
    return operation, temperature_c, time_h, atmosphere, cooling


def decompose_processing(text: str) -> list[ProcessingStep]:
    """Decompose a multi-step processing description into ORDERED steps (§6.5).

    Empty / process-free text yields ``[]``. Each returned :class:`ProcessingStep`
    carries a contiguous ``step_index`` (0..n) and the temperature / time /
    atmosphere / cooling-rate stated nearest its operation keyword.
    """
    if not text or not text.strip():
        return []
    groups = _group(text, _segments(text))
    collected: list[_Collected] = []
    for start, end in groups:
        span_text = text[start:end]
        operation, temperature_c, time_h, atmosphere, cooling = _extract_step(span_text)
        has_param = any(x is not None for x in (temperature_c, time_h, atmosphere, cooling))
        if operation is None and not has_param:
            continue  # stray clause with neither an operation nor a parameter
        collected.append((operation, temperature_c, time_h, atmosphere, cooling, span_text.strip()))
    return [
        ProcessingStep(
            step_index=i,
            operation=operation,
            temperature_c=temperature_c,
            time_h=time_h,
            atmosphere=atmosphere,
            cooling_rate=cooling,
            source_span=span,
        )
        for i, (operation, temperature_c, time_h, atmosphere, cooling, span) in enumerate(collected)
    ]
