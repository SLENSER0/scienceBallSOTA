"""Tests for the §6.2 structured graph-query body (§14.6).

Проверяют разбор канонического примера §6.2, валидацию ``query_type`` и
``min_confidence``, значения по умолчанию фильтров и флагов, а также
опускание ``None`` при сериализации.

Exercise parsing the canonical §6.2 example, ``query_type`` /
``min_confidence`` validation, filter/flag defaults, and ``None`` omission.
"""

from __future__ import annotations

import pytest
from api_gateway.graph_query_body import (
    GraphQueryBody,
    Processing,
    QueryFilters,
    parse_graph_query,
)

# Канонический пример тела §6.2 / the canonical §6.2 example body.
_EXAMPLE: dict[str, object] = {
    "query_type": "material_regime_property",
    "material": "Ti-6Al-4V",
    "processing": {"operation": "aging", "temperature_c": 540.0, "time_h": 4.0},
    "property": "yield_strength",
    "filters": {"min_confidence": 0.7, "verified_only": True, "date_from": "2020-01-01"},
    "include_evidence": True,
    "include_graph": False,
}


def test_example_body_parses_and_round_trips_key_fields() -> None:
    """(1) §6.2 example parses and round-trips its key fields."""
    body = parse_graph_query(_EXAMPLE)
    assert body.query_type == "material_regime_property"
    assert body.material == "Ti-6Al-4V"
    assert body.property == "yield_strength"
    assert body.processing == Processing(operation="aging", temperature_c=540.0, time_h=4.0)
    assert body.filters == QueryFilters(
        min_confidence=0.7, verified_only=True, date_from="2020-01-01"
    )
    assert body.include_evidence is True
    assert body.include_graph is False

    wire = body.as_dict()
    assert wire["query_type"] == "material_regime_property"
    assert wire["material"] == "Ti-6Al-4V"
    assert wire["property"] == "yield_strength"
    assert wire["processing"] == {"operation": "aging", "temperature_c": 540.0, "time_h": 4.0}
    assert wire["include_graph"] is False


def test_unknown_query_type_raises() -> None:
    """(2) An unknown ``query_type`` raises ``ValueError``."""
    with pytest.raises(ValueError, match="unknown query_type"):
        parse_graph_query({"query_type": "teleport"})


def test_out_of_range_min_confidence_raises() -> None:
    """(3) ``min_confidence=1.5`` raises ``ValueError``."""
    with pytest.raises(ValueError, match="min_confidence"):
        parse_graph_query({"query_type": "material_property", "filters": {"min_confidence": 1.5}})


def test_missing_filters_yields_defaults() -> None:
    """(4) Missing ``filters`` → ``QueryFilters(0.0, False, None)``."""
    body = parse_graph_query({"query_type": "material_property"})
    assert body.filters == QueryFilters(min_confidence=0.0, verified_only=False, date_from=None)


def test_as_dict_omits_none_processing_and_property() -> None:
    """(5) ``as_dict()`` omits ``None`` ``processing`` and ``property``."""
    body = parse_graph_query({"query_type": "material_property", "material": "Cu"})
    wire = body.as_dict()
    assert "processing" not in wire
    assert "property" not in wire
    assert wire["material"] == "Cu"


def test_include_evidence_defaults_true_when_absent() -> None:
    """(6) ``include_evidence`` defaults to ``True`` when absent."""
    body = parse_graph_query({"query_type": "material_property"})
    assert body.include_evidence is True
    assert body.include_graph is True


def test_partial_processing_leaves_missing_fields_none() -> None:
    """(7) Partial ``{'operation': 'aging'}`` → other fields ``None``."""
    body = parse_graph_query(
        {"query_type": "material_property", "processing": {"operation": "aging"}}
    )
    assert body.processing == Processing(operation="aging", temperature_c=None, time_h=None)
    assert body.processing is not None
    assert body.processing.as_dict() == {"operation": "aging"}


def test_as_dict_filters_reflect_verified_only_input() -> None:
    """(8) ``as_dict()['filters']['verified_only']`` reflects the input."""
    body = parse_graph_query(
        {"query_type": "material_property", "filters": {"verified_only": True}}
    )
    assert body.as_dict()["filters"]["verified_only"] is True

    body_false = parse_graph_query(
        {"query_type": "material_property", "filters": {"verified_only": False}}
    )
    assert body_false.as_dict()["filters"]["verified_only"] is False


def test_empty_processing_dict_omitted_from_wire() -> None:
    """An all-``None`` processing block is omitted from ``as_dict``."""
    body = GraphQueryBody(
        query_type="path",
        material=None,
        processing=Processing(),
        property=None,
        filters=QueryFilters(),
        include_evidence=True,
        include_graph=True,
    )
    assert "processing" not in body.as_dict()
