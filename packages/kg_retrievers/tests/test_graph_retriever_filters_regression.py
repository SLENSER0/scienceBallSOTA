"""Regression tests for graph_retriever geo/year/numeric filters.

Covers the confirmed bugs:
* H-4a — a geo filter must not drop Measurement/Evidence that carry no country/
  practice_type of their own (absence != violation).
* H-4b — facts tagged practice_type="global" (universal, peer-reviewed) always
  pass any geo filter.
* M-37 — the temporal filter must read node["year"] when node["source_year"] is
  absent (seeded Papers tag the year under "year").
* L-42 — a range whose upper bound is a legitimate 0.0 must not collapse to a
  point via a falsy ``or``.
* L-52 — an exact "=" numeric constraint must actually filter.
"""

from __future__ import annotations

from kg_extractors.query_parser import QueryIntent
from kg_extractors.units import ParsedConstraint
from kg_retrievers.graph_retriever import GraphRetriever


def test_geo_global_always_passes() -> None:  # H-4b
    intent = QueryIntent(raw="", practice_types=["russia"])
    assert GraphRetriever._passes_geo({"practice_type": "global"}, intent) is True
    intent_c = QueryIntent(raw="", countries=["RU"])
    assert (
        GraphRetriever._passes_geo({"practice_type": "global", "country": "US"}, intent_c)
        is True
    )


def test_geo_missing_field_is_not_a_violation() -> None:  # H-4a
    intent = QueryIntent(raw="", practice_types=["russia"])
    assert GraphRetriever._passes_geo({"label": "Measurement"}, intent) is True
    intent_c = QueryIntent(raw="", countries=["RU"])
    assert GraphRetriever._passes_geo({"label": "Evidence"}, intent_c) is True
    assert GraphRetriever._passes_geo({"label": "Paper"}, intent_c) is True


def test_geo_conflicting_value_still_drops() -> None:
    intent = QueryIntent(raw="", practice_types=["russia"])
    assert GraphRetriever._passes_geo({"practice_type": "foreign"}, intent) is False
    intent_c = QueryIntent(raw="", countries=["RU"])
    assert GraphRetriever._passes_geo({"country": "US"}, intent_c) is False


def test_year_falls_back_to_year_key() -> None:  # M-37
    intent = QueryIntent(raw="", year_from=2010)
    assert GraphRetriever._passes_year({"year": 2005}, intent) is False
    assert GraphRetriever._passes_year({"year": 2015}, intent) is True
    # source_year still takes precedence when present
    assert GraphRetriever._passes_year({"source_year": 2015, "year": 2005}, intent) is True


def test_range_upper_bound_zero_not_collapsed() -> None:  # L-42
    c = ParsedConstraint(
        operator="range", normalized_min=-3.0, normalized_max=0.0, normalized_unit="x"
    )
    intent = QueryIntent(raw="", numeric_constraints=[c])
    node = {"value_normalized": -1.0, "normalized_unit": "x"}
    assert GraphRetriever._passes_numeric(node, intent) is True
    out = {"value_normalized": 2.0, "normalized_unit": "x"}
    assert GraphRetriever._passes_numeric(out, intent) is False


def test_exact_equality_constraint_filters() -> None:  # L-52
    c = ParsedConstraint(operator="=", normalized_value=250.0, normalized_unit="mg/l")
    intent = QueryIntent(raw="", numeric_constraints=[c])
    assert (
        GraphRetriever._passes_numeric(
            {"value_normalized": 250.0, "normalized_unit": "mg/l"}, intent
        )
        is True
    )
    assert (
        GraphRetriever._passes_numeric(
            {"value_normalized": 400.0, "normalized_unit": "mg/l"}, intent
        )
        is False
    )
