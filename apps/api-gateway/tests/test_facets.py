"""Tests for facet aggregation of quick-filter value lists (§14.15).

Hermetic and dependency-free. Every assertion is a concrete hand-computed
value: count-desc ordering, alphabetical tie-breaking, skipping of rows that
lack the field, ``top`` truncation, the ``as_dict`` wire forms, multi-field
:func:`compute_facets`, and :func:`numeric_range` including its empty ``None``.
"""

from __future__ import annotations

from api_gateway.facets import Facet, FacetValue, compute_facet, compute_facets, numeric_range


def test_compute_facet_orders_by_count_desc() -> None:
    rows = [{"m": "A"}, {"m": "A"}, {"m": "B"}]
    facet = compute_facet(rows, "m")
    assert facet.values[0] == FacetValue("A", 2)


def test_compute_facet_ties_sort_alphabetically() -> None:
    rows = [{"m": "A"}, {"m": "A"}, {"m": "B"}]
    facet = compute_facet(rows, "m")
    assert facet.values[1].value == "B"


def test_compute_facet_skips_rows_missing_field() -> None:
    rows = [{"m": "A"}, {"other": "Z"}, {"m": "A"}]
    facet = compute_facet(rows, "m")
    assert facet.values == (FacetValue("A", 2),)


def test_compute_facet_pure_tie_is_alphabetical() -> None:
    rows = [{"m": "C"}, {"m": "B"}, {"m": "A"}]
    facet = compute_facet(rows, "m")
    assert [v.value for v in facet.values] == ["A", "B", "C"]


def test_compute_facet_top_truncates() -> None:
    rows = [{"m": "A"}, {"m": "A"}, {"m": "B"}, {"m": "C"}]
    facet = compute_facet(rows, "m", top=1)
    assert len(facet.values) == 1
    assert facet.values[0] == FacetValue("A", 2)


def test_compute_facet_empty_rows_yield_no_values() -> None:
    assert compute_facet([], "m").values == ()


def test_compute_facet_field_attribute_set() -> None:
    assert compute_facet([{"m": "A"}], "m").field == "m"


def test_facet_value_as_dict_shape() -> None:
    assert FacetValue("A", 2).as_dict() == {"value": "A", "count": 2}


def test_facet_as_dict_field() -> None:
    facet = Facet("m", (FacetValue("A", 2),))
    assert facet.as_dict()["field"] == "m"


def test_facet_as_dict_full_shape() -> None:
    facet = Facet("m", (FacetValue("A", 2), FacetValue("B", 1)))
    assert facet.as_dict() == {
        "field": "m",
        "values": [{"value": "A", "count": 2}, {"value": "B", "count": 1}],
    }


def test_numeric_range_min_max() -> None:
    assert numeric_range([{"c": 0.2}, {"c": 0.9}], "c") == (0.2, 0.9)


def test_numeric_range_empty_is_none() -> None:
    assert numeric_range([], "c") is None


def test_numeric_range_skips_rows_missing_field() -> None:
    assert numeric_range([{"c": 0.5}, {"other": 9}, {"c": 0.1}], "c") == (0.1, 0.5)


def test_numeric_range_unordered_input() -> None:
    assert numeric_range([{"c": 5}, {"c": 1}, {"c": 3}], "c") == (1.0, 5.0)


def test_compute_facets_one_per_field() -> None:
    rows = [{"m": "A"}, {"m": "A"}, {"m": "B"}]
    facets = compute_facets(rows, ["m", "x"])
    assert len(facets) == 2


def test_compute_facets_preserves_field_order() -> None:
    rows = [{"m": "A", "lab": "L1"}]
    facets = compute_facets(rows, ["lab", "m"])
    assert [f.field for f in facets] == ["lab", "m"]


def test_compute_facets_missing_field_gives_empty_facet() -> None:
    rows = [{"m": "A"}, {"m": "B"}]
    facets = compute_facets(rows, ["m", "x"])
    assert facets[1].field == "x"
    assert facets[1].values == ()
