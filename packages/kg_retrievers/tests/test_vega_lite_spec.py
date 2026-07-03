"""Tests for the Vega-Lite v5 spec builder (§22 reporting).

Hand-checkable: every expected dict is written out in full and compared exactly.
"""

from __future__ import annotations

import json

from kg_retrievers.vega_lite_spec import (
    VegaLiteSpec,
    bar_chart,
    scatter_chart,
    to_json,
)

# Small, hand-verifiable coverage table: property name -> measurement count.
COVERAGE_ROWS = [
    {"property": "bandgap", "count": 12},
    {"property": "density", "count": 7},
    {"property": "hardness", "count": 3},
]

# Metric-vs-metric rows for scatter plots.
METRIC_ROWS = [
    {"precision": 0.9, "recall": 0.8, "community": "A"},
    {"precision": 0.7, "recall": 0.95, "community": "B"},
]


def test_schema_is_vega_lite_v5() -> None:
    spec = bar_chart(COVERAGE_ROWS, x="property", y="count")
    assert "vega-lite/v5" in spec.as_dict()["$schema"]


def test_bar_mark_and_encoding_fields() -> None:
    spec = bar_chart(COVERAGE_ROWS, x="property", y="count")
    d = spec.as_dict()
    assert d["mark"] == "bar"
    assert d["encoding"]["x"]["field"] == "property"
    assert d["encoding"]["x"]["type"] == "nominal"
    assert d["encoding"]["y"]["field"] == "count"
    assert d["encoding"]["y"]["type"] == "quantitative"


def test_bar_data_values_equal_input_rows() -> None:
    spec = bar_chart(COVERAGE_ROWS, x="property", y="count")
    assert spec.as_dict()["data"]["values"] == COVERAGE_ROWS


def test_bar_custom_types() -> None:
    spec = bar_chart(
        COVERAGE_ROWS,
        x="count",
        y="property",
        x_type="quantitative",
        y_type="nominal",
    )
    enc = spec.as_dict()["encoding"]
    assert enc["x"]["type"] == "quantitative"
    assert enc["y"]["type"] == "nominal"


def test_bar_full_dict_hand_checked() -> None:
    spec = bar_chart([{"property": "bandgap", "count": 12}], x="property", y="count")
    assert spec.as_dict() == {
        "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
        "data": {"values": [{"property": "bandgap", "count": 12}]},
        "mark": "bar",
        "encoding": {
            "x": {"field": "property", "type": "nominal"},
            "y": {"field": "count", "type": "quantitative"},
        },
    }


def test_scatter_mark_is_point() -> None:
    spec = scatter_chart(METRIC_ROWS, x="precision", y="recall")
    d = spec.as_dict()
    assert d["mark"] == "point"
    assert d["encoding"]["x"]["field"] == "precision"
    assert d["encoding"]["x"]["type"] == "quantitative"
    assert d["encoding"]["y"]["field"] == "recall"


def test_scatter_with_color_adds_color_channel() -> None:
    spec = scatter_chart(METRIC_ROWS, x="precision", y="recall", color="community")
    enc = spec.as_dict()["encoding"]
    assert enc["color"]["field"] == "community"
    assert enc["color"]["type"] == "nominal"


def test_scatter_without_color_has_no_color_key() -> None:
    spec = scatter_chart(METRIC_ROWS, x="precision", y="recall")
    assert "color" not in spec.as_dict()["encoding"]


def test_title_present_when_given() -> None:
    spec = bar_chart(COVERAGE_ROWS, x="property", y="count", title="Coverage")
    assert spec.as_dict()["title"] == "Coverage"


def test_title_none_omits_key() -> None:
    spec = bar_chart(COVERAGE_ROWS, x="property", y="count")
    assert "title" not in spec.as_dict()
    scat = scatter_chart(METRIC_ROWS, x="precision", y="recall")
    assert "title" not in scat.as_dict()


def test_to_json_roundtrips_to_same_dict() -> None:
    spec = scatter_chart(METRIC_ROWS, x="precision", y="recall", color="community")
    text = to_json(spec)
    # Valid JSON, parseable back to exactly the source dict.
    assert json.loads(text) == spec.as_dict()


def test_to_json_is_sorted() -> None:
    spec = bar_chart(COVERAGE_ROWS, x="property", y="count", title="Coverage")
    text = to_json(spec)
    # sort_keys=True -> top-level keys appear alphabetically.
    assert text.index('"$schema"') < text.index('"data"') < text.index('"encoding"')
    assert text.index('"encoding"') < text.index('"mark"') < text.index('"title"')


def test_frozen_dataclass_immutable() -> None:
    spec = VegaLiteSpec(mark="bar", encoding={}, data_values=(), title=None)
    try:
        spec.mark = "point"  # type: ignore[misc]
    except AttributeError:
        pass
    else:
        raise AssertionError("VegaLiteSpec must be frozen")


def test_data_values_snapshot_independent_of_input() -> None:
    rows = [{"property": "bandgap", "count": 1}]
    spec = bar_chart(rows, x="property", y="count")
    rows.append({"property": "density", "count": 2})
    # The spec captured a tuple snapshot, so later mutation of ``rows`` is ignored.
    assert spec.as_dict()["data"]["values"] == [{"property": "bandgap", "count": 1}]
