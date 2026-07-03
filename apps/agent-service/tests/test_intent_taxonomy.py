"""Tests for the §7.5 named intent taxonomy (§13.8, §7.2 ``ROUTE``).

Deterministic, dependency-light: exercises :func:`classify_intent_v2` and the
:data:`GOLDEN_INTENTS` acceptance set on hand-checkable RU/EN inputs. Companion to
``test_intent_classifier.py`` (the seven heuristic classes) — here the assertions
are against the nine *named* §7.5 intents (never edits the sibling module).
"""

from __future__ import annotations

import dataclasses

import pytest
from agent_service.intent_taxonomy import (
    GOLDEN_INTENTS,
    Intent,
    IntentResult,
    accuracy,
    classify_intent_v2,
)

# The exact nine §7.5 / §13.8 intent strings (frozen expectation).
_NINE_INTENTS = {
    "material_regime_property_query",
    "entity_exploration",
    "experiment_lookup",
    "evidence_request",
    "gap_analysis",
    "contradiction_analysis",
    "method_comparison",
    "literature_summary",
    "schema_help",
}


def test_enum_is_exactly_the_nine_intents() -> None:
    # §13.8: EXACTLY the nine named §7.5 intents, no more, no fewer.
    assert {i.value for i in Intent} == _NINE_INTENTS
    assert len(Intent) == 9


def test_material_regime_property_query() -> None:
    # material X + regime Y + property Z → the primary Mode A structured intent.
    r = classify_intent_v2("Какая твёрдость сплава Al-Cu после старения при 180°C?")
    assert r.intent is Intent.MATERIAL_REGIME_PROPERTY_QUERY
    # твёрдость (property) + старение (regime) + 180°C (number+unit) all corroborate.
    assert "material_regime_property_query:твёрдост" in r.matched
    assert "material_regime_property_query:number+unit" in r.matched


def test_entity_exploration() -> None:
    # «расскажи о …» → entity neighborhood exploration (Mode B), not a structured query.
    r = classify_intent_v2("Расскажи о материале Al-Cu")
    assert r.intent is Intent.ENTITY_EXPLORATION


def test_experiment_lookup() -> None:
    # «эксперименты …» outranks the regime signal «старении» (structured) by precedence.
    r = classify_intent_v2("Какие эксперименты проводились со сплавом Al-Cu при старении?")
    assert r.intent is Intent.EXPERIMENT_LOOKUP


def test_evidence_request() -> None:
    # «доказательства …» → evidence request, not the «твёрдости» structured query.
    r = classify_intent_v2("Покажи доказательства для утверждения о твёрдости Al-Cu")
    assert r.intent is Intent.EVIDENCE_REQUEST


def test_literature_summary() -> None:
    # «обзор литературы …» outranks the «старению» regime signal by precedence.
    r = classify_intent_v2("Сделай обзор литературы по старению алюминиевых сплавов")
    assert r.intent is Intent.LITERATURE_SUMMARY


def test_comparison_maps_to_method_comparison() -> None:
    # A comparison question → method_comparison (the §7.5 name for the sibling
    # module's coarse «comparison» class). Both RU «сравни» and «чем отличается»
    # forms, and the regime words «отжиг/закалки» must NOT win over the comparison.
    ro = classify_intent_v2("Сравни обратный осмос и ионный обмен")
    vs = classify_intent_v2("Reverse osmosis vs ion exchange")
    diff = classify_intent_v2("Чем отличается отжиг от закалки?")
    assert ro.intent is Intent.METHOD_COMPARISON
    assert vs.intent is Intent.METHOD_COMPARISON
    assert diff.intent is Intent.METHOD_COMPARISON


def test_gap_vs_contradiction_distinguished() -> None:
    # gap_analysis (пробелы / нет данных) and contradiction_analysis (противоречия)
    # are distinct intents, not merged into one «gap» bucket.
    gap = classify_intent_v2("Какие пробелы в изучении коррозии алюминиевых сплавов?")
    contra = classify_intent_v2("Есть ли противоречия в данных о твёрдости Al-Cu?")
    assert gap.intent is Intent.GAP_ANALYSIS
    assert contra.intent is Intent.CONTRADICTION_ANALYSIS
    assert gap.intent is not contra.intent


def test_schema_help_types_of_nodes() -> None:
    # «какие есть типы узлов» → schema_help (§6.2 /graph/schema, no retrieval).
    r = classify_intent_v2("какие есть типы узлов")
    assert r.intent is Intent.SCHEMA_HELP


def test_each_of_nine_intents_hit_by_an_example() -> None:
    # Every named intent is both an expected label AND actually produced by the
    # classifier on ≥1 golden question.
    expected_labels = {intent for _, intent in GOLDEN_INTENTS}
    assert expected_labels == set(Intent)
    predicted = {classify_intent_v2(q).intent for q, _ in GOLDEN_INTENTS}
    assert predicted == set(Intent)


def test_golden_set_size_and_accuracy() -> None:
    # §13.8 acceptance: ≥18 labeled questions (≥2 per intent), accuracy ≥ 0.85.
    assert len(GOLDEN_INTENTS) >= 18
    per_intent = dict.fromkeys(Intent, 0)
    for _, intent in GOLDEN_INTENTS:
        per_intent[intent] += 1
    assert all(count >= 2 for count in per_intent.values())
    assert accuracy(GOLDEN_INTENTS) >= 0.85


def test_accuracy_helper_defaults_and_empty() -> None:
    # accuracy() defaults to GOLDEN_INTENTS; a perfect hand-picked subset scores 1.0.
    assert accuracy() == accuracy(GOLDEN_INTENTS)
    subset = [
        ("какие есть типы узлов", Intent.SCHEMA_HELP),
        ("Сравни X и Y", Intent.METHOD_COMPARISON),
    ]
    assert accuracy(subset) == pytest.approx(1.0)
    assert accuracy([]) == 0.0


def test_confidence_in_unit_interval() -> None:
    # Confidence is always a probability in [0, 1] for any input, including empty.
    for question, _ in [*GOLDEN_INTENTS, ("", Intent.MATERIAL_REGIME_PROPERTY_QUERY)]:
        r = classify_intent_v2(question)
        assert 0.0 <= r.confidence <= 1.0


def test_more_signals_raise_confidence() -> None:
    # Two corroborating property+regime signals beat a single-marker classification.
    two = classify_intent_v2("твёрдость после старения")
    one = classify_intent_v2("какие есть типы узлов")
    assert two.intent is Intent.MATERIAL_REGIME_PROPERTY_QUERY
    assert two.confidence > one.confidence


def test_empty_input_graceful_fallback() -> None:
    # Empty / signal-less input → no crash, structured fallback, low confidence.
    r = classify_intent_v2("")
    assert r.intent is Intent.MATERIAL_REGIME_PROPERTY_QUERY
    assert r.matched == []
    assert r.confidence == pytest.approx(0.30)
    # A signal-less but non-empty question also falls back cleanly.
    assert classify_intent_v2("...").intent is Intent.MATERIAL_REGIME_PROPERTY_QUERY


def test_as_dict_shape_and_frozen() -> None:
    r = classify_intent_v2("Какие есть типы узлов в графе?")
    d = r.as_dict()
    assert set(d) == {"intent", "confidence", "matched"}
    assert d["intent"] == "schema_help"
    assert isinstance(d["intent"], str)
    assert isinstance(d["matched"], list)
    # Frozen dataclass: attributes are immutable.
    assert isinstance(r, IntentResult)
    with pytest.raises(dataclasses.FrozenInstanceError):
        r.intent = Intent.GAP_ANALYSIS  # type: ignore[misc]
