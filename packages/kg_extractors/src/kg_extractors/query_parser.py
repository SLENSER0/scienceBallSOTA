"""Natural-language query parser (§24.9 / §24.8).

Turns a RU/EN question into a structured intent: resolved domain entities,
numeric constraints, geography/practice-type, time window, comparison flag, gap
flag and a coarse query type. Rule-first (deterministic, fast, RU+EN) so the four
acceptance queries parse without an LLM; an LLM hook can enrich unknown entities.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from kg_common.ids import canonical_key
from kg_extractors.units import ParsedConstraint, parse_numeric_constraints
from kg_schema.taxonomy import TaxonomyEntry, load_taxonomy

_LAST_N_YEARS = re.compile(r"(?:за\s+)?(?:последни[ей]|last)\s+(\d+)\s+(?:лет|years?|год)", re.I)
_YEAR = re.compile(r"\b(19|20)\d{2}\b")

_FOREIGN_MARKERS = [
    "за рубежом",
    "мировая практика",
    "мировой практике",
    "foreign",
    "world practice",
    "international",
    "за границей",
    "зарубежн",
]
_DOMESTIC_MARKERS = ["в россии", "отечественн", "российск", "в рф", "domestic", "in russia"]
_COMPARE_MARKERS = [" vs ", " против ", "сравн", "compare", "лучше", " или ", "vs.", "по сравнению"]
_GAP_MARKERS = [
    "нет эксперимент",
    "не изучен",
    "не освещ",
    "no experiment",
    "no data",
    "пробел",
    "gap",
    "отсутству",
    "не хватает",
]
_REVIEW_MARKERS = [
    "литературный обзор",
    "обзор",
    "literature review",
    "review",
    "какие методы",
    "какие способы",
    "какие техническ",
    "покажите все",
]


@dataclass
class QueryIntent:
    raw: str
    lang: str = "unknown"
    entities: list[TaxonomyEntry] = field(default_factory=list)
    numeric_constraints: list[ParsedConstraint] = field(default_factory=list)
    practice_types: list[str] = field(default_factory=list)  # russia / foreign / both
    countries: list[str] = field(default_factory=list)
    domains: list[str] = field(default_factory=list)
    last_n_years: int | None = None
    year_from: int | None = None
    year_to: int | None = None
    is_comparison: bool = False
    is_gap_query: bool = False
    query_type: str = "structured"  # structured | literature_review | comparison | gap

    def entity_ids(self) -> list[str]:
        return [e.node_id for e in self.entities]

    def to_dict(self) -> dict:
        return {
            "raw": self.raw,
            "lang": self.lang,
            "entities": [
                {"id": e.id, "type": e.node_type, "name": e.canonical_en} for e in self.entities
            ],
            "numeric_constraints": [c.as_dict() for c in self.numeric_constraints],
            "practice_types": self.practice_types,
            "countries": self.countries,
            "domains": self.domains,
            "last_n_years": self.last_n_years,
            "year_from": self.year_from,
            "year_to": self.year_to,
            "is_comparison": self.is_comparison,
            "is_gap_query": self.is_gap_query,
            "query_type": self.query_type,
        }


def _detect_lang(text: str) -> str:
    cyr = len(re.findall(r"[а-яё]", text, re.I))
    lat = len(re.findall(r"[a-z]", text, re.I))
    if cyr and lat and min(cyr, lat) / max(cyr, lat) > 0.25:
        return "mixed"
    return "ru" if cyr >= lat else "en"


def _loose_match(a: str, b: str) -> bool:
    """Declension-tolerant word match: exact, or long common prefix (RU endings).

    ``шлак``~``шлаком``, ``никель``~``никеля``, ``циркуляция``~``циркуляции``.
    """
    if a == b:
        return True
    la, lb = len(a), len(b)
    if min(la, lb) < 4:  # short symbols (Ni, Ca, SO4, МПГ) must match exactly
        return False
    if abs(la - lb) > 3:
        return False
    cp = 0
    for x, y in zip(a, b, strict=False):
        if x == y:
            cp += 1
        else:
            break
    return cp >= min(la, lb) - 1


def _tokens(text: str) -> list[str]:
    return [t for t in canonical_key(text).split() if t]


def scan_taxonomy(text: str) -> list[TaxonomyEntry]:
    """Find taxonomy entities mentioned in ``text`` (RU/EN, declension-tolerant)."""
    idx = load_taxonomy()
    q_tokens = _tokens(text)
    q_set = set(q_tokens)
    found: dict[str, TaxonomyEntry] = {}
    for entry in idx.entries:
        for term in entry.all_terms:
            words = _tokens(term)
            if not words:
                continue
            ok = all(w in q_set or any(_loose_match(w, qt) for qt in q_tokens) for w in words)
            if ok:
                found.setdefault(entry.id, entry)
                break
    return list(found.values())


def parse_query(text: str) -> QueryIntent:
    low = text.lower()
    intent = QueryIntent(raw=text, lang=_detect_lang(text))
    intent.entities = scan_taxonomy(text)
    intent.numeric_constraints = parse_numeric_constraints(text)

    # domains from matched entities
    intent.domains = sorted({e.domain for e in intent.entities if e.domain})

    # geography / practice type
    foreign = any(m in low for m in _FOREIGN_MARKERS)
    domestic = any(m in low for m in _DOMESTIC_MARKERS)
    if foreign and domestic:
        intent.practice_types = ["russia", "foreign"]
    elif foreign:
        intent.practice_types = ["foreign"]
    elif domestic:
        intent.practice_types = ["russia"]
    intent.countries = sorted({e.id for e in intent.entities if e.node_type == "Country"})

    # time
    m = _LAST_N_YEARS.search(text)
    if m:
        intent.last_n_years = int(m.group(1))
    years = [int(y.group(0)) for y in _YEAR.finditer(text)]
    if years:
        intent.year_from, intent.year_to = min(years), max(years)

    # flags / type
    intent.is_comparison = (
        any(m in low for m in _COMPARE_MARKERS) or len(intent.practice_types) == 2
    )
    intent.is_gap_query = any(m in low for m in _GAP_MARKERS)
    if intent.is_gap_query:
        intent.query_type = "gap"
    elif intent.is_comparison:
        intent.query_type = "comparison"
    elif any(m in low for m in _REVIEW_MARKERS):
        intent.query_type = "literature_review"
    return intent
