"""Agent intent classifier + tool routing (§13.8, §7.5 Node 2).

Implements Node 2 of the LangGraph QA workflow (§7.5 ``classify_intent``): the
cheap, deterministic step that runs *after* the §13.7 preprocess node and
*before* retrieval planning. It reads the normalized RU/EN question and picks a
coarse ``query_type`` plus a tool plan, using only substring keywords and a
couple of regex patterns — no LLM call, no ``pint``/``langdetect`` — so routing
stays fast and offline.

Классы запроса / query classes (§13.8):

* ``numeric``     — число с единицей / a number with a physical unit
  (``250 А/м²`` current density, ``5 МПа``, ``30 %``) or an inequality bound.
* ``comparison``  — ``сравни`` / ``vs`` / ``versus`` / ``против`` (сравнение).
* ``gap``         — ``пробел`` / ``нет данных`` / ``gap`` (пробелы в знаниях).
* ``geography``   — ``отечествен`` / ``зарубеж`` / ``россия`` / ``foreign``
  (география практики: отечественная vs зарубежная, §24.13).
* ``temporal``    — ``за последние N лет`` / an explicit year (временное окно).
* ``global``      — ``основные`` / ``обзор`` / ``main clusters`` (тематический
  обзор → GraphRAG Mode C, §11.7).
* ``structured``  — fallback when no strong signal fires (структурный запрос).

The classifier never raises: empty / signal-less input degrades gracefully to
``structured`` with a low confidence. ``route_after_classify`` maps the chosen
class onto an ordered plan of the explicit tools from
:mod:`agent_service.tools`, always bracketed evidence-first (§8.3): candidate
discovery (``graph_search`` / ``global_search``) first, provenance assembly
(``evidence_lookup``) last.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from agent_service.tools import (
    COMPARE_PRACTICE,
    EVIDENCE_LOOKUP,
    GAP_CHECK,
    GLOBAL_SEARCH,
    GRAPH_SEARCH,
    NUMERIC_FILTER,
)

# The seven query classes of §13.8 (order here is only documentation).
QUERY_TYPES: tuple[str, ...] = (
    "numeric",
    "comparison",
    "gap",
    "geography",
    "temporal",
    "global",
    "structured",
)

# --- keyword markers (RU/EN, lowercased substrings) -------------------------
# Aligned with :mod:`kg_extractors.query_parser` markers so the cheap node and
# the full parser agree on terminology (сравнение / пробел / география / обзор).
_MARKERS: dict[str, tuple[str, ...]] = {
    # Сравнение / comparison (§7.5 method_comparison).
    "comparison": (
        "сравн",  # сравни / сравнить / сравнение / сравниваем
        "по сравнению",
        "против",
        " vs ",
        "vs.",
        " versus ",
        "versus",
        "compare",
        "comparison",
    ),
    # Пробел / gap (§11.1 gap_analysis).
    "gap": (
        "пробел",  # пробелы в знаниях
        "нет данных",
        "нет эксперимент",
        "не изучен",
        "не исследов",
        "не хватает",
        "отсутству",
        "gap",
        "no data",
        "missing data",
    ),
    # География практики / geography (отечественная vs зарубежная, §24.13).
    "geography": (
        "отечествен",  # отечественная практика
        "зарубеж",  # зарубежный / за рубежом
        "росси",  # россия / российск / в россии
        "в рф",
        "foreign",
        "domestic",
        "world practice",
        "мировая практика",
        "мировой практике",
        "international",
        "за границей",
    ),
    # Тематический обзор / global (GraphRAG Mode C, §11.7).
    "global": (
        "основны",  # основные кластеры / основные направления
        "обзор",  # обзор / литературный обзор
        "кластер",  # кластеры технологий / main clusters
        "main cluster",
        "overview",
        "landscape",
        "какие методы",
        "какие способы",
    ),
}

# --- regex patterns (temporal + numeric) ------------------------------------
# «за последние N лет» / «last N years» (cf. query_parser ``_LAST_N_YEARS``).
_LAST_N_YEARS = re.compile(
    r"(?:за\s+)?(?:последни[а-я]+|last)\s+(\d+)\s+(?:лет|года?|год|years?)",
    re.IGNORECASE,
)
# A bare 4-digit year (1900–2099) — an explicit temporal anchor.
_YEAR = re.compile(r"\b(?:19|20)\d{2}\b")
# A number immediately followed by a physical unit (число + единица). The unit
# allowlist is explicit (electrical / temperature / pressure / concentration /
# flow) and deliberately excludes time words (год/лет/year) so temporal windows
# like «3 года» do NOT read as measurements.
_NUM_UNIT = re.compile(
    r"\d+(?:[.,]\d+)?\s?"
    r"(?:а/м²?|a/m²?|°\s?[cс]|°|мпа|гпа|кпа|па|бар|атм|"
    r"мг/л|г/л|моль/л|ppm|%|м³/ч|м³|м3|м/с|мм|см|нм|мкм|"
    r"кв|мв|ма|вт|квт|гц|об/мин|рн)",
    re.IGNORECASE,
)
# An inequality bound around a number (≤ 250, > 3) — also a numeric constraint.
_INEQ = re.compile(r"[<>≤≥]\s?\d|\d\s?[<>≤≥]")

# Precedence for picking a single class when several signals fire (§13.8). A
# specific *intent* (gap / comparison) or scoped *facet* (geography / temporal /
# global) outranks a bare ``numeric`` reading, which outranks ``structured``.
_PRECEDENCE: tuple[str, ...] = (
    "gap",
    "comparison",
    "geography",
    "temporal",
    "global",
    "numeric",
)

# Ordered tool plans per class (§13.6 tool layer), reusing the tool-name
# constants from :mod:`agent_service.tools`. Every plan is evidence-first (§8.3):
# discovery first, ``evidence_lookup`` last.
_ROUTES: dict[str, list[str]] = {
    "numeric": [GRAPH_SEARCH, NUMERIC_FILTER, EVIDENCE_LOOKUP],
    "comparison": [GRAPH_SEARCH, COMPARE_PRACTICE, EVIDENCE_LOOKUP],
    "geography": [GRAPH_SEARCH, COMPARE_PRACTICE, EVIDENCE_LOOKUP],
    "gap": [GRAPH_SEARCH, GAP_CHECK, EVIDENCE_LOOKUP],
    "global": [GLOBAL_SEARCH, EVIDENCE_LOOKUP],
    "temporal": [GRAPH_SEARCH, EVIDENCE_LOOKUP],
    "structured": [GRAPH_SEARCH, EVIDENCE_LOOKUP],
}

_BASE_CONFIDENCE = 0.55  # one matching signal
_SIGNAL_BONUS = 0.10  # per corroborating signal
_MAX_CONFIDENCE = 0.95  # cap (heuristics are never certain)
_FALLBACK_CONFIDENCE = 0.30  # ``structured`` with no signal


@dataclass(frozen=True)
class IntentClass:
    """Result of the §13.8 intent classifier (§7.5 Node 2).

    Fields
    ------
    query_type
        One of ``numeric`` | ``comparison`` | ``gap`` | ``geography`` |
        ``temporal`` | ``global`` | ``structured`` (класс запроса).
    confidence
        Heuristic confidence in ``[0.0, 1.0]`` — higher when more signals of the
        chosen class corroborate (уверенность).
    signals
        Human-readable ``"category:marker"`` tags for *every* detected signal
        (across all classes), in detection order — the audit trail of *why* this
        class was picked (сигналы).
    """

    query_type: str
    confidence: float
    signals: list[str]

    def as_dict(self) -> dict[str, object]:
        """Full structured view for agent state / logging (§7.3)."""
        return {
            "query_type": self.query_type,
            "confidence": self.confidence,
            "signals": list(self.signals),
        }


def classify_intent(text: str) -> IntentClass:
    """Classify a normalized RU/EN question into a §13.8 query class.

    Uses cheap keyword + pattern heuristics (see module docstring). Collects
    every matching signal, then picks the highest-precedence class that fired
    (:data:`_PRECEDENCE`); confidence grows with the number of corroborating
    signals for that class. Empty / signal-less input yields ``structured`` at
    :data:`_FALLBACK_CONFIDENCE` and never raises.
    """
    low = (text or "").lower()
    signals: list[str] = []
    scores: dict[str, int] = {}

    def _hit(category: str, marker: str) -> None:
        signals.append(f"{category}:{marker}")
        scores[category] = scores.get(category, 0) + 1

    # keyword categories (comparison / gap / geography / global)
    for category, markers in _MARKERS.items():
        for marker in markers:
            if marker in low:
                _hit(category, marker.strip())

    # temporal: «за последние N лет» / explicit year
    tm = _LAST_N_YEARS.search(low)
    if tm:
        _hit("temporal", f"last_{tm.group(1)}_years")
    if _YEAR.search(text or ""):
        _hit("temporal", "year")

    # numeric: число + единица / inequality bound
    if _NUM_UNIT.search(low):
        _hit("numeric", "number+unit")
    if _INEQ.search(low):
        _hit("numeric", "inequality")

    query_type = "structured"
    for category in _PRECEDENCE:
        if scores.get(category):
            query_type = category
            break

    if query_type == "structured":
        confidence = _FALLBACK_CONFIDENCE
    else:
        n = scores[query_type]
        confidence = min(_MAX_CONFIDENCE, _BASE_CONFIDENCE + _SIGNAL_BONUS * (n - 1))
    return IntentClass(query_type=query_type, confidence=round(confidence, 2), signals=signals)


def route_after_classify(intent_class: IntentClass) -> list[str]:
    """Map a classified intent onto an ordered tool plan (§13.6 / §13.8).

    Returns the ordered list of tool names (constants from
    :mod:`agent_service.tools`) to run for ``intent_class.query_type``. Unknown /
    unexpected classes fall back to the ``structured`` plan so routing is total.
    Every plan is evidence-first (§8.3): candidate discovery first,
    ``evidence_lookup`` last.
    """
    return list(_ROUTES.get(intent_class.query_type, _ROUTES["structured"]))
