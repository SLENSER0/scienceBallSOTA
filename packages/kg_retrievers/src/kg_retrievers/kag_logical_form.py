"""KAG-style logical-form decomposition of a natural-language query (§11/§12).

Implements the *logical-form* front end of KAG (Knowledge Augmented Generation,
OpenSPG / Ant Group): a query is decomposed into a small **symbolic plan** of
typed retrieval operations that a knowledge-graph executor can bind and run,
rather than being answered by free-text RAG alone. This mirrors KAG's
"logical-form-guided reasoning", where a question is rewritten into ordered
retrieval / filter / compare / aggregate steps over the KG.

    KAG — github.com/OpenSPG/KAG  (arXiv:2409.13731, "KAG: Boosting LLMs in
    Professional Domains via Knowledge Augmented Generation").

:func:`decompose` turns a query into a frozen :class:`LogicalForm` holding an
ordered tuple of :class:`Op` (``retrieval`` -> ``filter`` -> ``aggregate`` ->
``compare``), the resolved subject ``entities``, and the numeric
``constraints``. The numeric-constraint parsing is patterned after
:class:`kg_extractors.constraints.Constraint` (§24.4) but kept self-contained
and query-scoped. Pure-python / regex only; RU + EN surface forms.

Разбор запроса в символический план (логическую форму) в стиле KAG: операции
retrieval/filter/compare/aggregate с сущностями и числовыми ограничениями.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Op-type vocabulary + canonical execution order
# ---------------------------------------------------------------------------

RETRIEVAL = "retrieval"
FILTER = "filter"
AGGREGATE = "aggregate"
COMPARE = "compare"

# A KG executor runs the plan in this order: fetch candidates, prune by numeric
# constraints, aggregate over the survivors, then compare the results.
_OP_RANK: dict[str, int] = {RETRIEVAL: 0, FILTER: 1, AGGREGATE: 2, COMPARE: 3}


# ---------------------------------------------------------------------------
# Surface vocab (RU/EN). Matched over the lower-cased query; slices are read
# back from the original-case text so units/spans keep their casing.
# ---------------------------------------------------------------------------

# Property (parameter) mentions -> canonical property name. Multi-word phrases
# win over their substrings via longest-first matching.
_PROPERTY_TERMS: dict[str, str] = {
    "tensile strength": "tensile_strength",
    "yield strength": "yield_strength",
    "thermal conductivity": "thermal_conductivity",
    "melting point": "melting_point",
    "corrosion resistance": "corrosion_resistance",
    "hardness": "hardness",
    "density": "density",
    "conductivity": "conductivity",
    "elongation": "elongation",
    "toughness": "toughness",
    "modulus": "modulus",
    "temperature": "temperature",
    "strength": "strength",
    "предел прочности": "tensile_strength",
    "предел текучести": "yield_strength",
    "температура плавления": "melting_point",
    "теплопроводность": "thermal_conductivity",
    "твёрдость": "hardness",
    "твердость": "hardness",
    "плотность": "density",
    "проводимость": "conductivity",
    "прочность": "strength",
    "температура": "temperature",
}

# Aggregation surface -> function. Full words only (no stemming) for determinism.
_AGG_TERMS: dict[str, str] = {
    "average": "avg",
    "mean": "avg",
    "avg": "avg",
    "count": "count",
    "number of": "count",
    "how many": "count",
    "maximum": "max",
    "max": "max",
    "highest": "max",
    "largest": "max",
    "greatest": "max",
    "minimum": "min",
    "min": "min",
    "lowest": "min",
    "smallest": "min",
    "least": "min",
    "total": "sum",
    "sum": "sum",
    "среднее": "avg",
    "среднего": "avg",
    "количество": "count",
    "сколько": "count",
    "максимальное": "max",
    "максимум": "max",
    "наибольшее": "max",
    "минимальное": "min",
    "минимум": "min",
    "наименьшее": "min",
    "сумма": "sum",
}

# Explicit comparison cues -> compare intent.
_COMPARE_TERMS: dict[str, str] = {
    "compare": "compare",
    "comparison": "compare",
    "versus": "compare",
    "vs": "compare",
    "difference between": "compare",
    "better than": "compare",
    "worse than": "compare",
    "сравни": "compare",
    "сравнить": "compare",
    "сравнение": "compare",
    "сравните": "compare",
    "разница между": "compare",
    "лучше": "compare",
    "хуже": "compare",
}

# Numeric comparators -> operator. Symbols carry no word boundary; alphabetic
# phrases do (see :func:`_comparator_alt`).
_COMPARATORS: dict[str, str] = {
    "не менее": ">=",
    "не более": "<=",
    "не ниже": ">=",
    "не выше": "<=",
    "менее": "<",
    "более": ">",
    "ниже": "<",
    "выше": ">",
    "меньше": "<",
    "больше": ">",
    "от": ">=",
    "до": "<=",
    "равно": "=",
    "at least": ">=",
    "no less than": ">=",
    "greater than or equal to": ">=",
    "at most": "<=",
    "no more than": "<=",
    "less than or equal to": "<=",
    "greater than": ">",
    "more than": ">",
    "less than": "<",
    "above": ">",
    "over": ">",
    "below": "<",
    "under": "<",
    "exceeding": ">",
    "equal to": "=",
    "equals": "=",
    "<=": "<=",
    ">=": ">=",
    "≤": "<=",
    "≥": ">=",
    "⩽": "<=",
    "⩾": ">=",
    "<": "<",
    ">": ">",
    "=": "=",
}

# Alphabetic units accepted even though they carry no symbol/digit signal.
_KNOWN_UNITS: frozenset[str] = frozenset(
    {
        "mpa",
        "gpa",
        "kpa",
        "pa",
        "hb",
        "hbw",
        "hrc",
        "hrb",
        "hv",
        "k",
        "c",
        "f",
        "mm",
        "cm",
        "m",
        "nm",
        "um",
        "kg",
        "g",
        "mg",
        "t",
        "w",
        "kw",
        "mw",
        "ppm",
        "hz",
        "мпа",
        "гпа",
        "кпа",
        "па",
        "нм",
        "мм",
        "см",
        "кг",
        "гц",
    }
)

# Question / connector words that are never entities.
_STOPWORDS: frozenset[str] = frozenset(
    {
        "of",
        "the",
        "a",
        "an",
        "with",
        "and",
        "or",
        "for",
        "in",
        "on",
        "to",
        "at",
        "by",
        "is",
        "are",
        "be",
        "what",
        "which",
        "that",
        "than",
        "between",
        "from",
        "its",
        "their",
        "list",
        "show",
        "find",
        "give",
        "all",
        "any",
        "me",
        "do",
        "does",
        "has",
        "have",
        "having",
        "such",
        "materials",
        "material",
        "alloy",
        "alloys",
        "sample",
        "samples",
        "и",
        "или",
        "с",
        "со",
        "для",
        "в",
        "на",
        "у",
        "что",
        "какой",
        "какие",
        "каких",
        "между",
        "чем",
        "из",
        "по",
        "все",
        "всех",
        "это",
        "этот",
        "найти",
        "показать",
        "дай",
        "материал",
        "материалы",
        "материалов",
        "сплав",
        "сплавы",
        "образец",
        "образцы",
    }
)

_NUM = r"[-+]?\d+(?:[.,]\d+)?"
# A unit token: starts with a unit-ish char (never a digit, so numbers are not
# swallowed), may carry per-unit slashes / super-scripts.
_UNIT = r"[°%a-zа-яёμµ][°%a-zа-яёμµ0-9/·²³]*"


def _sorted_items(vocab: dict[str, str]) -> list[tuple[str, str]]:
    """Vocab items sorted longest-surface-first (greedy, non-overlapping)."""
    return sorted(vocab.items(), key=lambda kv: -len(kv[0]))


_PROPERTY_ITEMS = _sorted_items(_PROPERTY_TERMS)
_AGG_ITEMS = _sorted_items(_AGG_TERMS)
_COMPARE_ITEMS = _sorted_items(_COMPARE_TERMS)


def _comparator_alt() -> str:
    """Regex alternation for comparators, longest-first, ``\\b`` on words."""
    parts: list[str] = []
    for surface in sorted(_COMPARATORS, key=len, reverse=True):
        esc = re.escape(surface)
        if surface[0].isalpha():
            esc = rf"\b{esc}\b"
        parts.append(esc)
    return "|".join(parts)


_COMPARATOR_RE = re.compile(rf"(?P<op>{_comparator_alt()})\s*(?P<val>{_NUM})\s*(?P<unit>{_UNIT})?")
_RANGE_FRAMED = re.compile(
    rf"\b(?:between|от)\b\s+(?P<lo>{_NUM})\s+(?:\band\b|\bto\b|\bдо\b|-|–|—)\s+"
    rf"(?P<hi>{_NUM})\s*(?P<unit>{_UNIT})?"
)
_RANGE_DASH = re.compile(rf"(?P<lo>{_NUM})\s*(?:–|—|-|\.\.)\s*(?P<hi>{_NUM})\s*(?P<unit>{_UNIT})")
_ENTITY_TOKEN = re.compile(r"[a-zа-яё]+")


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NumericConstraint:
    """One numeric condition parsed from the query (§11/§12).

    Patterned after :class:`kg_extractors.constraints.Constraint` (§24.4):
    ``operator`` is ``<`` / ``<=`` / ``>`` / ``>=`` / ``=`` (single ``value``)
    or ``range`` (``min`` / ``max`` populated). ``parameter`` is the property
    the condition applies to (``None`` if none precedes it); ``source_span`` is
    the exact matched text for provenance.
    """

    parameter: str | None
    operator: str
    value: float | None = None
    min: float | None = None
    max: float | None = None
    unit: str | None = None
    source_span: str = ""

    def as_dict(self) -> dict[str, object]:
        """Serialize, dropping unset (``None``) numeric fields."""
        out: dict[str, object] = {"parameter": self.parameter, "operator": self.operator}
        for key in ("value", "min", "max", "unit"):
            val = getattr(self, key)
            if val is not None:
                out[key] = val
        out["source_span"] = self.source_span
        return out


@dataclass(frozen=True)
class Op:
    """One typed operation in a KAG logical form (§11/§12).

    ``op`` is one of ``retrieval`` / ``filter`` / ``aggregate`` / ``compare``.
    ``args`` carries the operation's bound arguments (entities, properties,
    operator, value, unit, function) that a KG executor consumes.
    """

    op: str
    args: dict[str, object] = field(default_factory=dict)

    def as_dict(self) -> dict[str, object]:
        args: dict[str, object] = {}
        for key, val in self.args.items():
            args[key] = list(val) if isinstance(val, list) else val
        return {"op": self.op, "args": args}


@dataclass(frozen=True)
class LogicalForm:
    """A query decomposed into a KAG symbolic plan (§11/§12).

    ``ops`` is the ordered tuple of :class:`Op` a KG executor runs (retrieve ->
    filter -> aggregate -> compare); ``entities`` are the resolved subject
    mentions in first-seen order; ``constraints`` are the numeric conditions.
    Frozen: build via :func:`decompose`.
    """

    ops: tuple[Op, ...]
    entities: tuple[str, ...]
    constraints: tuple[NumericConstraint, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "ops": [op.as_dict() for op in self.ops],
            "entities": list(self.entities),
            "constraints": [c.as_dict() for c in self.constraints],
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_float(raw: str) -> float:
    """Parse a numeric token, accepting a decimal comma and a leading sign."""
    return float(raw.replace(",", ".").lstrip("+"))


def _overlaps(covered: list[tuple[int, int]], start: int, end: int) -> bool:
    return any(not (end <= s or start >= e) for s, e in covered)


def _accept_unit(raw: str | None) -> str | None:
    """Return ``raw`` if it is a plausible unit, else ``None``.

    A unit is kept when it is a known alphabetic unit or carries a non-letter
    signal (``%``, ``°``, ``/``, digit, super-script). This rejects a following
    plain word (e.g. ``"apples"``) that the greedy unit pattern may capture.
    """
    if not raw:
        return None
    u = raw.strip()
    low = u.lower()
    if low in _KNOWN_UNITS or any(not ch.isalpha() for ch in low):
        return u
    return None


def _phrase_spans(text_lower: str, items: list[tuple[str, str]]) -> list[tuple[int, int, str]]:
    """Non-overlapping, longest-first spans of ``items`` surfaces over text.

    Returns ``(start, end, label)`` sorted by start. Word boundaries keep a
    surface from matching inside a larger word (e.g. ``от`` in ``поток``).
    """
    covered: list[tuple[int, int]] = []
    out: list[tuple[int, int, str]] = []
    for surface, label in items:
        for m in re.finditer(rf"\b{re.escape(surface)}\b", text_lower):
            s, e = m.span()
            if _overlaps(covered, s, e):
                continue
            covered.append((s, e))
            out.append((s, e, label))
    out.sort(key=lambda x: x[0])
    return out


def _param_before(prop_spans: list[tuple[int, int, str]], pos: int) -> str | None:
    """Canonical property whose mention starts latest *before* ``pos``."""
    best: str | None = None
    best_start = -1
    for s, _e, label in prop_spans:
        if s < pos and s > best_start:
            best_start = s
            best = label
    return best


def _nearest_property(prop_spans: list[tuple[int, int, str]], pos: int) -> str | None:
    """Canonical property whose mention starts closest to ``pos``."""
    best: str | None = None
    best_dist: int | None = None
    for s, _e, label in prop_spans:
        dist = abs(s - pos)
        if best_dist is None or dist < best_dist:
            best_dist = dist
            best = label
    return best


def _dedupe(values: Iterable[str]) -> tuple[str, ...]:
    """Order-preserving unique."""
    seen: set[str] = set()
    out: list[str] = []
    for v in values:
        if v not in seen:
            seen.add(v)
            out.append(v)
    return tuple(out)


def _add_range(
    m: re.Match[str],
    text: str,
    prop_spans: list[tuple[int, int, str]],
    found: list[tuple[int, int, NumericConstraint]],
    *,
    require_valid_unit: bool,
) -> tuple[int, int] | None:
    lo = _to_float(m.group("lo"))
    hi = _to_float(m.group("hi"))
    lo, hi = min(lo, hi), max(lo, hi)
    unit = _accept_unit(text[m.start("unit") : m.end("unit")]) if m.group("unit") else None
    if require_valid_unit and unit is None:
        return None
    start, end = m.start(), m.end()
    found.append(
        (
            start,
            end,
            NumericConstraint(
                parameter=_param_before(prop_spans, start),
                operator="range",
                min=lo,
                max=hi,
                unit=unit,
                source_span=text[start:end].strip(),
            ),
        )
    )
    return start, end


def _add_comparator(
    m: re.Match[str],
    text: str,
    prop_spans: list[tuple[int, int, str]],
    found: list[tuple[int, int, NumericConstraint]],
) -> tuple[int, int]:
    operator = _COMPARATORS[m.group("op")]
    value = _to_float(m.group("val"))
    end = m.end()
    unit: str | None = None
    if m.group("unit"):
        unit = _accept_unit(text[m.start("unit") : m.end("unit")])
        if unit is None:  # reject captured word; do not consume it
            end = m.start("unit")
    start = m.start()
    found.append(
        (
            start,
            end,
            NumericConstraint(
                parameter=_param_before(prop_spans, start),
                operator=operator,
                value=value,
                unit=unit,
                source_span=text[start:end].strip(),
            ),
        )
    )
    return start, end


def _parse_constraints(
    text: str, text_lower: str, prop_spans: list[tuple[int, int, str]]
) -> tuple[list[NumericConstraint], list[tuple[int, int]]]:
    """Parse ranges (framed, then dash+unit), then comparators; no overlaps."""
    found: list[tuple[int, int, NumericConstraint]] = []
    covered: list[tuple[int, int]] = []

    for m in _RANGE_FRAMED.finditer(text_lower):
        span = _add_range(m, text, prop_spans, found, require_valid_unit=False)
        if span:
            covered.append(span)
    for m in _RANGE_DASH.finditer(text_lower):
        if _overlaps(covered, *m.span()):
            continue
        span = _add_range(m, text, prop_spans, found, require_valid_unit=True)
        if span:
            covered.append(span)
    for m in _COMPARATOR_RE.finditer(text_lower):
        if _overlaps(covered, *m.span()):
            continue
        covered.append(_add_comparator(m, text, prop_spans, found))

    found.sort(key=lambda x: x[0])
    return [c for _s, _e, c in found], [(s, e) for s, e, _c in found]


def _extract_entities(text_lower: str, mask_spans: list[tuple[int, int]]) -> tuple[str, ...]:
    """Content tokens left after masking constraints / vocab spans."""
    chars = list(text_lower)
    for s, e in mask_spans:
        for i in range(s, min(e, len(chars))):
            chars[i] = " "
    masked = "".join(chars)
    tokens = (t for t in _ENTITY_TOKEN.findall(masked) if t not in _STOPWORDS)
    return _dedupe(tokens)


def _aggregation_ops(
    agg_spans: list[tuple[int, int, str]], prop_spans: list[tuple[int, int, str]]
) -> Iterator[tuple[str, str | None]]:
    seen: set[tuple[str, str | None]] = set()
    for s, _e, func in agg_spans:
        pair = (func, _nearest_property(prop_spans, s))
        if pair not in seen:
            seen.add(pair)
            yield pair


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def decompose(query: str) -> LogicalForm:
    """Decompose ``query`` into a KAG-style logical form (§11/§12).

    Detects property mentions, numeric constraints, aggregation and comparison
    cues, then emits an ordered plan: a ``retrieval`` op (when there is any
    entity or property to fetch), one ``filter`` op per numeric constraint, one
    ``aggregate`` op per aggregation cue, and a ``compare`` op when the query
    asks for a comparison. Ops are sorted into canonical execution order
    (retrieval -> filter -> aggregate -> compare). An empty / blank query
    yields an empty plan.
    """
    if not query or not query.strip():
        return LogicalForm(ops=(), entities=(), constraints=())

    text = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", query)).strip()
    text_lower = text.lower()

    prop_spans = _phrase_spans(text_lower, _PROPERTY_ITEMS)
    agg_spans = _phrase_spans(text_lower, _AGG_ITEMS)
    cmp_spans = _phrase_spans(text_lower, _COMPARE_ITEMS)
    constraints, cons_spans = _parse_constraints(text, text_lower, prop_spans)

    properties = _dedupe(label for _s, _e, label in prop_spans)
    aggregations = list(_aggregation_ops(agg_spans, prop_spans))
    compare_intent = bool(cmp_spans)

    mask_spans = (
        list(cons_spans)
        + [(s, e) for s, e, _ in prop_spans]
        + [(s, e) for s, e, _ in agg_spans]
        + [(s, e) for s, e, _ in cmp_spans]
    )
    entities = _extract_entities(text_lower, mask_spans)

    ops: list[Op] = []
    if entities or properties:
        ops.append(Op(RETRIEVAL, {"entities": list(entities), "properties": list(properties)}))
    for c in constraints:
        args = {k: v for k, v in c.as_dict().items() if k != "source_span"}
        ops.append(Op(FILTER, args))
    for func, prop in aggregations:
        ops.append(Op(AGGREGATE, {"function": func, "property": prop}))
    if compare_intent:
        ops.append(Op(COMPARE, {"entities": list(entities), "properties": list(properties)}))

    ops.sort(key=lambda o: _OP_RANK[o.op])
    return LogicalForm(ops=tuple(ops), entities=entities, constraints=tuple(constraints))
