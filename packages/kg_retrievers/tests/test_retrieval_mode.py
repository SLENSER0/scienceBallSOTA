"""Hand-checked tests for retrieval-mode selection (§12.11 / §10.1 / §13.8).

Every expected value is derived by hand from the fixed rules in
:mod:`kg_retrievers.retrieval_mode`:

    * intent (§13.8) overrides the query heuristic when it is a known class;
    * otherwise: material+property+numeric → structured (Mode A, graph+vector),
      broad/thematic wording → global (Mode C, community+vector),
      everything else → semantic (Mode B, vector+keyword).
"""

from __future__ import annotations

import pytest

from kg_retrievers.retrieval_mode import (
    MODE_GLOBAL,
    MODE_SEMANTIC,
    MODE_STRUCTURED,
    ModeDecision,
    select_mode,
)


def test_numeric_material_property_is_structured_with_graph_vector() -> None:
    # Al-Cu (material) + hardness (property) + 180 / 2 (numeric) → Mode A structured.
    d = select_mode(None, "Hardness of Al-Cu alloy after aging at 180 C for 2 h?")

    assert d.mode == MODE_STRUCTURED
    assert d.strategies == ("graph", "vector")
    assert "graph" in d.strategies and "vector" in d.strategies


def test_broad_overview_query_is_global_with_community() -> None:
    # Broad wording ("overview", "directions"), no numeric → Mode C global.
    d = select_mode(None, "Give an overview of the research directions in aluminum alloys")

    assert d.mode == MODE_GLOBAL
    assert d.strategies == ("community", "vector")
    assert "community" in d.strategies


def test_generic_query_is_semantic_with_vector_keyword() -> None:
    # No numeric, no broad wording → Mode B semantic hybrid.
    d = select_mode(None, "Explain the mechanism behind solid-solution strengthening")

    assert d.mode == MODE_SEMANTIC
    assert d.strategies == ("vector", "keyword")


def test_reason_is_non_empty_for_every_branch() -> None:
    for intent, query in [
        (None, "Hardness of Al-Cu alloy at 180 C for 2 h?"),
        (None, "Give an overview of what is known about steel"),
        (None, "How does work hardening occur?"),
        ("material_regime_property_query", "x"),
        ("banana", "y"),
    ]:
        d = select_mode(intent, query)
        assert isinstance(d.reason, str)
        assert d.reason.strip() != ""


def test_strategies_are_non_empty_for_every_branch() -> None:
    for intent, query in [
        (None, "Al-Cu hardness at 180 C for 2 h"),
        (None, "landscape and trends overview"),
        (None, "some generic question"),
        ("schema_help", ""),
        ("unknown_intent_xyz", ""),
    ]:
        d = select_mode(intent, query)
        assert len(d.strategies) >= 1


def test_intent_overrides_query_heuristic() -> None:
    # Query wording is broad (heuristic → global) but the intent forces structured.
    broad_query = "Give a general overview of the whole field"
    heuristic = select_mode(None, broad_query)
    forced = select_mode("material_regime_property_query", broad_query)

    assert heuristic.mode == MODE_GLOBAL
    assert forced.mode == MODE_STRUCTURED  # intent wins over the query heuristic


def test_unknown_intent_falls_back_to_query_heuristic() -> None:
    # An unrecognised intent string is ignored; the query text decides the mode.
    broad = select_mode("totally_made_up_intent", "overview of directions in the field")
    structured = select_mode("", "Al-Cu alloy hardness measured at 200 C")

    assert broad.mode == MODE_GLOBAL
    assert structured.mode == MODE_STRUCTURED
    assert "fell back" in broad.reason  # provenance records the fallback


def test_as_dict_shape_and_types() -> None:
    d = select_mode("literature_summary", "anything")
    payload = d.as_dict()

    assert payload == {
        "mode": "global",
        "reason": "intent 'literature_summary' routed to global retrieval (§13.8/§12.11)",
        "strategies": ["community", "vector"],
    }
    assert isinstance(payload["strategies"], list)


@pytest.mark.parametrize(
    ("intent", "expected"),
    [
        ("material_regime_property_query", MODE_STRUCTURED),
        ("experiment_lookup", MODE_STRUCTURED),
        ("entity_exploration", MODE_STRUCTURED),
        ("gap_analysis", MODE_STRUCTURED),
        ("contradiction_analysis", MODE_STRUCTURED),
        ("method_comparison", MODE_SEMANTIC),
        ("evidence_request", MODE_SEMANTIC),
        ("schema_help", MODE_SEMANTIC),
        ("literature_summary", MODE_GLOBAL),
    ],
)
def test_taxonomy_intents_map_to_expected_mode(intent: str, expected: str) -> None:
    # Intent decides the mode regardless of the (empty) query text.
    assert select_mode(intent, "").mode == expected


def test_intent_is_case_and_whitespace_insensitive() -> None:
    d = select_mode("  Literature_Summary  ", "anything")

    assert d.mode == MODE_GLOBAL


def test_mode_decision_is_frozen() -> None:
    d = select_mode("schema_help", "x")

    with pytest.raises((AttributeError, TypeError)):
        d.mode = MODE_STRUCTURED  # type: ignore[misc]


def test_mode_decision_type() -> None:
    assert isinstance(select_mode(None, "x"), ModeDecision)
