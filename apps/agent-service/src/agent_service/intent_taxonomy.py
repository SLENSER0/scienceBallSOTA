"""Spec-named intent taxonomy — the 9 §7.5 intents (§13.8, §7.2 ``ROUTE``).

Companion to :mod:`agent_service.intent_classifier`. That module emits the seven
*heuristic* query classes (``numeric`` / ``comparison`` / ``gap`` / ``geography``
/ ``temporal`` / ``global`` / ``structured``) used for cheap tool routing. This
module instead speaks the **named taxonomy** of §7.5 Node 2 / §13.8 verbatim: the
nine intents the LLM classifier must emit and that :func:`router.select_mode`
(§12.1) maps onto retrieval modes A/B/C/D.

The nine §7.5 intents (:class:`Intent`) and their §12.1 retrieval mode:

* ``material_regime_property_query`` — material X + regime Y + property Z (Mode A,
  структурный запрос «свойство материала при режиме»).
* ``entity_exploration``            — окрестность узла / «расскажи о …» (Mode B).
* ``experiment_lookup``             — поиск экспериментов / опытов (Mode A).
* ``evidence_request``              — «покажи доказательства / источники» (Mode B).
* ``gap_analysis``                  — пробелы в знаниях (Mode A+D, GAP-ветка).
* ``contradiction_analysis``        — противоречия/конфликты данных (Mode A+D).
* ``method_comparison``             — сравнение методов «X vs Y» (Mode B).
* ``literature_summary``            — обзор / «что известно в целом» (Mode C).
* ``schema_help``                   — «какие есть типы узлов» → без retrieval.

:func:`classify_intent_v2` is a deterministic RU/EN keyword+pattern heuristic (no
LLM, offline) that stands in for the §13.8 LLM node in tests and as a fallback: it
collects every matching signal, then picks the highest-precedence intent that
fired (:data:`_PRECEDENCE`). It never raises; a signal-less question degrades to
``material_regime_property_query`` (the primary Mode A structured intent) at a low
confidence. :data:`GOLDEN_INTENTS` is the §13.8 acceptance golden set (≥18 labeled
questions, ≥2 per intent); :func:`accuracy` scores a classifier against it.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum


class Intent(StrEnum):
    """The nine named QA intents of §7.5 Node 2 / §13.8 (девять интентов)."""

    MATERIAL_REGIME_PROPERTY_QUERY = "material_regime_property_query"
    ENTITY_EXPLORATION = "entity_exploration"
    EXPERIMENT_LOOKUP = "experiment_lookup"
    EVIDENCE_REQUEST = "evidence_request"
    GAP_ANALYSIS = "gap_analysis"
    CONTRADICTION_ANALYSIS = "contradiction_analysis"
    METHOD_COMPARISON = "method_comparison"
    LITERATURE_SUMMARY = "literature_summary"
    SCHEMA_HELP = "schema_help"


# All nine intents as an ordered tuple (documentation / iteration helper).
ALL_INTENTS: tuple[Intent, ...] = tuple(Intent)


# --- keyword markers (RU/EN, lowercased substrings) -------------------------
# One marker family per intent. Substrings are matched against the lowercased
# question; the winning intent is chosen by :data:`_PRECEDENCE`, not by order
# here. Markers are deliberately morphology-tolerant prefixes (RU stems) so that
# «противоречи-е/-я/-вые» all match a single «противоречи» entry.
_MARKERS: dict[Intent, tuple[str, ...]] = {
    # Схема графа / schema help — «какие есть типы узлов» (§6.2 /graph/schema).
    Intent.SCHEMA_HELP: (
        "типы узлов",
        "тип узл",  # тип узла / типы узлов
        "виды узлов",
        "какие узлы",
        "типы связ",  # типы связей
        "тип связ",
        "какие связи",
        "схема граф",
        "схему граф",
        "структур граф",  # структура/структуре графа
        "как устроен граф",
        "онтолог",  # онтология
        "что ты умеешь",
        "node type",
        "edge type",
        "relationship type",
        "graph schema",
        "schema",
        "ontology",
    ),
    # Противоречия / contradictions (§11.1 contradiction_analysis).
    Intent.CONTRADICTION_ANALYSIS: (
        "противоречи",  # противоречие / противоречивые
        "конфликт",  # конфликтующие данные
        "не согласуют",
        "расходятся",
        "расхождени",  # расхождения
        "несоответстви",
        "contradict",
        "conflict",
        "disagree",
        "inconsistent",
        "discrepan",  # discrepancy
    ),
    # Пробелы в знаниях / gaps (§11.1 gap_analysis).
    Intent.GAP_ANALYSIS: (
        "пробел",  # пробелы в знаниях
        "нет данных",
        "нет эксперимент",
        "не изучен",
        "не исследов",
        "не хватает",
        "недостаточно изучен",
        "недостаточно данных",
        "отсутству",  # отсутствуют данные
        "белые пятна",
        "малоизучен",
        "мало изучен",
        "gap",
        "no data",
        "missing data",
        "understudied",
        "unexplored",
        "lack of data",
    ),
    # Сравнение методов / method comparison (§7.5 method_comparison).
    Intent.METHOD_COMPARISON: (
        "сравн",  # сравни / сравнить / сравнение
        "по сравнению",
        "против",  # X против Y
        " vs ",
        "vs.",
        " versus ",
        "versus",
        "чем отлич",  # чем отличается
        "в чём разниц",
        "в чем разниц",
        "разница между",
        "разниц между",
        "отличие",
        "отличия",
        "compare",
        "comparison",
        "difference between",
    ),
    # Запрос доказательств / evidence request (§8.3 evidence-first).
    Intent.EVIDENCE_REQUEST: (
        "доказательств",  # доказательства
        "подтвержд",  # чем подтверждается
        "на основании",
        "на чём основан",
        "на чем основан",
        "источник",  # источники утверждения
        "первоисточник",
        "цитат",  # цитата / цитаты
        "пруф",
        "evidence",
        "proof",
        "citation",
        "reference",
        "sources",
        "support",  # supporting data / what supports
    ),
    # Литературный обзор / literature summary (§10.1 Mode C).
    Intent.LITERATURE_SUMMARY: (
        "обзор",  # обзор литературы / литературный обзор
        "в целом",  # что известно в целом
        "основные направлени",
        "основные тенденци",
        "современное состояние",
        "состояние вопроса",
        "литератур",  # литература / литературы
        "суммир",  # суммируй
        "summary",
        "overview",
        "state of the art",
        "landscape",
        "review of",
        "literature",
    ),
    # Поиск экспериментов / experiment lookup (§12.2 experiment_lookup).
    Intent.EXPERIMENT_LOOKUP: (
        "эксперимент",  # эксперименты / эксперимента
        "испытани",  # испытания
        "опыты",
        "experiment",
    ),
    # Исследование сущности / entity exploration (§10.1 Mode B, neighbors).
    Intent.ENTITY_EXPLORATION: (
        "расскажи о",
        "расскажи про",
        "что такое",
        "что за ",
        "информация о",
        "информацию о",
        "покажи связи",
        "соседи",  # соседние узлы
        "связанные с",
        "относящиеся к",
        "все свойства",
        "tell me about",
        "explore",
        "neighbors",
        "related to",
        "what is ",
    ),
    # Материал+режим+свойство / structured query (§10.1 Mode A, primary).
    Intent.MATERIAL_REGIME_PROPERTY_QUERY: (
        # свойства / properties
        "твёрдост",
        "твердост",
        "прочност",
        "предел текучест",
        "модул",  # модуль упругости
        "теплопровод",
        "электропровод",
        "проводимост",
        "коррозионн",
        "пластичност",
        "вязкост",
        "плотност",
        "hardness",
        "strength",
        "conductivity",
        "yield",
        "modulus",
        "ductility",
        "toughness",
        # режимы / processing regimes
        "старени",  # старение
        "отжиг",
        "закалк",
        "отпуск",
        "прокатк",
        "деформац",
        "термообработк",
        "режим",
        "при температур",
        "aging",
        "ageing",
        "annealing",
        "quench",
        "temper",
        "heat treatment",
    ),
}

# A number immediately followed by a physical unit (число + единица) — an extra
# ``material_regime_property_query`` signal (measurement constraint). The unit
# allowlist excludes time words so «3 года» is NOT read as a measurement.
_NUM_UNIT = re.compile(
    r"\d+(?:[.,]\d+)?\s?"
    r"(?:а/м²?|a/m²?|°\s?[cс]|мпа|гпа|кпа|па|бар|атм|"
    r"мг/л|г/л|моль/л|ppm|%|м³/ч|м³|мм|см|нм|мкм|"
    r"кв|мв|ма|вт|квт|гц|hv|hrc|hb)",
    re.IGNORECASE,
)

# Precedence for picking a single intent when several fire (§13.8). Most-specific
# / narrowest intents first; ``material_regime_property_query`` is last because it
# is also the signal-less fallback (the primary Mode A structured query).
_PRECEDENCE: tuple[Intent, ...] = (
    Intent.SCHEMA_HELP,
    Intent.CONTRADICTION_ANALYSIS,
    Intent.GAP_ANALYSIS,
    Intent.METHOD_COMPARISON,
    Intent.EVIDENCE_REQUEST,
    Intent.LITERATURE_SUMMARY,
    Intent.EXPERIMENT_LOOKUP,
    Intent.ENTITY_EXPLORATION,
    Intent.MATERIAL_REGIME_PROPERTY_QUERY,
)

_FALLBACK_INTENT = Intent.MATERIAL_REGIME_PROPERTY_QUERY

_BASE_CONFIDENCE = 0.55  # one matching signal
_SIGNAL_BONUS = 0.10  # per corroborating signal of the chosen intent
_MAX_CONFIDENCE = 0.95  # cap (heuristics are never certain)
_FALLBACK_CONFIDENCE = 0.30  # signal-less → structured fallback


@dataclass(frozen=True)
class IntentResult:
    """Result of the §13.8 named-intent classifier (§7.5 Node 2).

    Fields
    ------
    intent
        One of the nine §7.5 :class:`Intent` values (интент запроса).
    confidence
        Heuristic confidence in ``[0.0, 1.0]`` — higher when more signals of the
        chosen intent corroborate (уверенность).
    matched
        Human-readable ``"intent:marker"`` tags for *every* detected signal
        (across all intents), in detection order — the audit trail of *why* this
        intent was picked (сработавшие сигналы).
    """

    intent: Intent
    confidence: float
    matched: list[str]

    def as_dict(self) -> dict[str, object]:
        """Full structured view for agent state / logging (§7.3)."""
        return {
            "intent": self.intent.value,
            "confidence": self.confidence,
            "matched": list(self.matched),
        }


def classify_intent_v2(question: str) -> IntentResult:
    """Classify a RU/EN question into one of the nine §7.5 intents (§13.8).

    Deterministic keyword + pattern heuristic (see module docstring): collects
    every matching signal across all intents, then picks the highest-precedence
    intent that fired (:data:`_PRECEDENCE`). Confidence grows with the number of
    corroborating signals for the chosen intent. Signal-less / empty input yields
    ``material_regime_property_query`` at :data:`_FALLBACK_CONFIDENCE` and never
    raises.
    """
    low = (question or "").lower()
    matched: list[str] = []
    scores: dict[Intent, int] = {}

    def _hit(intent: Intent, marker: str) -> None:
        matched.append(f"{intent.value}:{marker}")
        scores[intent] = scores.get(intent, 0) + 1

    for intent, markers in _MARKERS.items():
        for marker in markers:
            if marker in low:
                _hit(intent, marker.strip())

    # число + единица → extra structured (material_regime_property_query) signal.
    if _NUM_UNIT.search(low):
        _hit(Intent.MATERIAL_REGIME_PROPERTY_QUERY, "number+unit")

    chosen: Intent | None = None
    for intent in _PRECEDENCE:
        if scores.get(intent):
            chosen = intent
            break

    if chosen is None:
        return IntentResult(
            intent=_FALLBACK_INTENT, confidence=_FALLBACK_CONFIDENCE, matched=matched
        )

    n = scores[chosen]
    confidence = min(_MAX_CONFIDENCE, _BASE_CONFIDENCE + _SIGNAL_BONUS * (n - 1))
    return IntentResult(intent=chosen, confidence=round(confidence, 2), matched=matched)


# --- golden set (§13.8 acceptance: ≥18 labeled questions, ≥2 per intent) -----
# Hand-labeled RU/EN questions used to measure classifier accuracy. Every one of
# the nine :class:`Intent` values appears as an expected label at least twice.
GOLDEN_INTENTS: list[tuple[str, Intent]] = [
    # material_regime_property_query
    (
        "Какая твёрдость сплава Al-Cu после старения при 180°C?",
        Intent.MATERIAL_REGIME_PROPERTY_QUERY,
    ),
    ("Предел прочности стали 40Х после закалки и отпуска", Intent.MATERIAL_REGIME_PROPERTY_QUERY),
    (
        "Electrical conductivity of copper alloy after annealing",
        Intent.MATERIAL_REGIME_PROPERTY_QUERY,
    ),
    # entity_exploration
    ("Расскажи о материале Al-Cu", Intent.ENTITY_EXPLORATION),
    ("Что такое обратный осмос?", Intent.ENTITY_EXPLORATION),
    ("Покажи связи узла лаборатория Гипроникель", Intent.ENTITY_EXPLORATION),
    # experiment_lookup
    ("Какие эксперименты проводились со сплавом Al-Cu при старении?", Intent.EXPERIMENT_LOOKUP),
    ("Найди испытания на коррозионную стойкость титановых сплавов", Intent.EXPERIMENT_LOOKUP),
    ("List experiments on membrane desalination", Intent.EXPERIMENT_LOOKUP),
    # evidence_request
    ("Покажи доказательства для утверждения о твёрдости Al-Cu", Intent.EVIDENCE_REQUEST),
    ("На основании чего сделан вывод о прочности?", Intent.EVIDENCE_REQUEST),
    ("What sources support this hardness value?", Intent.EVIDENCE_REQUEST),
    # gap_analysis
    ("Какие пробелы в изучении коррозии алюминиевых сплавов?", Intent.GAP_ANALYSIS),
    ("Где нет данных по усталостной прочности титана?", Intent.GAP_ANALYSIS),
    ("What is understudied in membrane fouling research?", Intent.GAP_ANALYSIS),
    # contradiction_analysis
    ("Есть ли противоречия в данных о твёрдости Al-Cu?", Intent.CONTRADICTION_ANALYSIS),
    ("Найди конфликтующие результаты по прочности стали", Intent.CONTRADICTION_ANALYSIS),
    ("Are there conflicting measurements for this alloy?", Intent.CONTRADICTION_ANALYSIS),
    # method_comparison
    ("Сравни обратный осмос и ионный обмен по энергозатратам", Intent.METHOD_COMPARISON),
    ("Reverse osmosis vs ion exchange for desalination", Intent.METHOD_COMPARISON),
    ("Чем отличается отжиг от закалки?", Intent.METHOD_COMPARISON),
    # literature_summary
    ("Сделай обзор литературы по старению алюминиевых сплавов", Intent.LITERATURE_SUMMARY),
    ("Что в целом известно о мембранных технологиях водоподготовки?", Intent.LITERATURE_SUMMARY),
    ("Overview of recent research on titanium alloys", Intent.LITERATURE_SUMMARY),
    # schema_help
    ("Какие есть типы узлов в графе?", Intent.SCHEMA_HELP),
    ("Покажи схему графа и типы связей", Intent.SCHEMA_HELP),
    ("What node types and relationships exist?", Intent.SCHEMA_HELP),
]


def accuracy(golden: Sequence[tuple[str, Intent]] | None = None) -> float:
    """Fraction of ``golden`` pairs :func:`classify_intent_v2` labels correctly.

    Defaults to :data:`GOLDEN_INTENTS`. Returns ``0.0`` for an empty set (§13.8
    acceptance target: ``accuracy(GOLDEN_INTENTS) >= 0.85``).
    """
    pairs = GOLDEN_INTENTS if golden is None else golden
    if not pairs:
        return 0.0
    correct = sum(
        1 for question, expected in pairs if classify_intent_v2(question).intent == expected
    )
    return correct / len(pairs)
