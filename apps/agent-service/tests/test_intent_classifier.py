"""Tests for the §13.8 intent classifier + routing (§7.5 Node 2).

Deterministic, dependency-light: exercises the coarse query-class heuristics
(numeric / comparison / gap / geography / temporal / global / structured) and the
tool-routing map on hand-checkable RU/EN inputs. Tool-name assertions reuse the
constants from :mod:`agent_service.tools` (never edited here).
"""

from __future__ import annotations

import dataclasses

import pytest
from agent_service.intent_classifier import (
    IntentClass,
    classify_intent,
    route_after_classify,
)
from agent_service.tools import (
    COMPARE_PRACTICE,
    EVIDENCE_LOOKUP,
    GAP_CHECK,
    GLOBAL_SEARCH,
    GRAPH_SEARCH,
    NUMERIC_FILTER,
)


def test_numeric_number_plus_unit() -> None:
    # «250 А/м²» = число + единица (плотность тока) → numeric.
    ic = classify_intent("250 А/м² плотность тока")
    assert ic.query_type == "numeric"
    assert "numeric:number+unit" in ic.signals


def test_comparison_ru_sravni() -> None:
    # «сравни …» → comparison (сравнение методов).
    ic = classify_intent("сравни осмос и ионный обмен")
    assert ic.query_type == "comparison"


def test_comparison_en_vs() -> None:
    # English «vs» is a comparison marker too.
    ic = classify_intent("reverse osmosis vs ion exchange")
    assert ic.query_type == "comparison"


def test_gap_ru_probely() -> None:
    # «какие пробелы» → gap (пробелы в знаниях).
    ic = classify_intent("какие пробелы")
    assert ic.query_type == "gap"


def test_geography_ru_otechestvennaya() -> None:
    # «отечественная практика» → geography (география практики).
    ic = classify_intent("отечественная практика")
    assert ic.query_type == "geography"


def test_geography_en_foreign() -> None:
    # English «foreign» → geography.
    ic = classify_intent("foreign practice for desalination")
    assert ic.query_type == "geography"


def test_global_ru_klastery() -> None:
    # «основные кластеры технологий» → global (тематический обзор, Mode C).
    ic = classify_intent("основные кластеры технологий")
    assert ic.query_type == "global"


def test_temporal_last_n_years() -> None:
    # «за последние 3 года» → temporal, NOT numeric (год ≠ физическая единица).
    ic = classify_intent("за последние 3 года")
    assert ic.query_type == "temporal"
    assert not any(s.startswith("numeric:") for s in ic.signals)


def test_temporal_explicit_year() -> None:
    # A bare 4-digit year is a temporal anchor.
    ic = classify_intent("публикации 2021 по мембранам")
    assert ic.query_type == "temporal"


def test_structured_fallback() -> None:
    # No strong signal → structured fallback with low confidence.
    ic = classify_intent("мембранные технологии водоподготовки")
    assert ic.query_type == "structured"
    assert ic.signals == []
    assert ic.confidence == pytest.approx(0.30)


def test_confidence_in_unit_interval() -> None:
    # Confidence is always a probability in [0, 1] for any input.
    for q in [
        "250 А/м² плотность тока",
        "сравни осмос и ионный обмен",
        "какие пробелы",
        "отечественная практика",
        "основные кластеры технологий",
        "за последние 3 года",
        "",
        "мембранные технологии",
    ]:
        ic = classify_intent(q)
        assert 0.0 <= ic.confidence <= 1.0


def test_more_signals_raise_confidence() -> None:
    # «основные кластеры» fires two global markers → above single-signal base.
    two = classify_intent("основные кластеры технологий")
    one = classify_intent("сравни осмос и ионный обмен")
    assert two.confidence > one.confidence


def test_route_comparison_includes_compare_practice() -> None:
    ic = classify_intent("сравни осмос и ионный обмен")
    plan = route_after_classify(ic)
    assert COMPARE_PRACTICE in plan
    # Evidence-first bracketing (§8.3): discovery first, evidence last.
    assert plan[0] == GRAPH_SEARCH
    assert plan[-1] == EVIDENCE_LOOKUP


def test_route_numeric_includes_numeric_filter() -> None:
    ic = classify_intent("250 А/м² плотность тока")
    plan = route_after_classify(ic)
    assert plan == [GRAPH_SEARCH, NUMERIC_FILTER, EVIDENCE_LOOKUP]


def test_route_gap_includes_gap_check() -> None:
    ic = classify_intent("какие пробелы")
    assert GAP_CHECK in route_after_classify(ic)


def test_route_global_uses_global_search() -> None:
    ic = classify_intent("основные кластеры технологий")
    plan = route_after_classify(ic)
    assert plan[0] == GLOBAL_SEARCH
    assert GRAPH_SEARCH not in plan  # Mode C skips node-by-node graph search


def test_route_geography_compares_practice() -> None:
    ic = classify_intent("отечественная практика")
    assert COMPARE_PRACTICE in route_after_classify(ic)


def test_as_dict_shape_and_frozen() -> None:
    ic = classify_intent("250 А/м² плотность тока")
    d = ic.as_dict()
    assert set(d) == {"query_type", "confidence", "signals"}
    assert d["query_type"] == "numeric"
    assert isinstance(d["signals"], list)
    # Frozen dataclass: attributes are immutable.
    assert isinstance(ic, IntentClass)
    with pytest.raises(dataclasses.FrozenInstanceError):
        ic.query_type = "gap"  # type: ignore[misc]


def test_empty_input_graceful() -> None:
    # Empty input → no crash, structured, empty signals.
    ic = classify_intent("")
    assert ic.query_type == "structured"
    assert ic.signals == []
