"""Gap heat-map — counting gaps across a two-axis grid (§15.15).

Every expected cell count is hand-derivable from the tiny fixtures: each gap adds
``1`` to the cell named by its resolved row/col axis values, and a gap missing a
dimension counts into :data:`MISSING_KEY`. Keys and ``max_count`` are checked
against concrete values so the grid can be verified by eye.
"""

from __future__ import annotations

from kg_retrievers.gap_heatmap import MISSING_KEY, Heatmap, build_heatmap


def _gap(**over: object) -> dict:
    """A gap dict from the given axis fields (material_id / property_id / ...)."""
    return dict(over)


def test_cell_counts_accumulate_per_row_col() -> None:
    # M1×P1 appears twice, M1×P2 once → those exact cell counts (§15.15).
    gaps = [
        _gap(material_id="M1", property_id="P1"),
        _gap(material_id="M1", property_id="P1"),
        _gap(material_id="M1", property_id="P2"),
    ]
    hm = build_heatmap(gaps)
    assert hm.count("M1", "P1") == 2
    assert hm.count("M1", "P2") == 1
    assert hm.count("M2", "P1") == 0  # never observed


def test_row_and_col_keys_are_sorted_and_deduplicated() -> None:
    # Two materials × two properties, keys come out sorted regardless of input order.
    gaps = [
        _gap(material_id="M2", property_id="P2"),
        _gap(material_id="M1", property_id="P1"),
        _gap(material_id="M1", property_id="P2"),
    ]
    hm = build_heatmap(gaps)
    assert hm.row_keys == ("M1", "M2")
    assert hm.col_keys == ("P1", "P2")
    assert hm.rows == "material"
    assert hm.cols == "property"


def test_max_count_is_the_busiest_cell() -> None:
    # Counts are {M1×P1: 3, M2×P1: 1} → max_count is 3 (§15.15).
    gaps = [
        _gap(material_id="M1", property_id="P1"),
        _gap(material_id="M1", property_id="P1"),
        _gap(material_id="M1", property_id="P1"),
        _gap(material_id="M2", property_id="P1"),
    ]
    hm = build_heatmap(gaps)
    assert hm.max_count == 3


def test_missing_dimension_goes_to_missing_bucket() -> None:
    # A gap with no property_id counts into the MISSING_KEY column, nothing dropped.
    gaps = [
        _gap(material_id="M1", property_id="P1"),
        _gap(material_id="M1"),  # no property axis
    ]
    hm = build_heatmap(gaps)
    assert hm.count("M1", MISSING_KEY) == 1
    assert hm.count("M1", "P1") == 1
    assert MISSING_KEY in hm.col_keys
    assert hm.max_count == 1


def test_empty_gaps_give_empty_map() -> None:
    hm = build_heatmap([])
    assert isinstance(hm, Heatmap)
    assert hm.row_keys == ()
    assert hm.col_keys == ()
    assert hm.cells == {}
    assert hm.max_count == 0


def test_custom_axes_group_by_domain_and_type() -> None:
    # rows=domain, cols=type: physics×absent twice, chemistry×contradiction once.
    gaps = [
        _gap(domain="physics", type="absent"),
        _gap(domain="physics", type="absent"),
        _gap(domain="chemistry", type="contradiction"),
    ]
    hm = build_heatmap(gaps, rows="domain", cols="type")
    assert hm.rows == "domain"
    assert hm.cols == "type"
    assert hm.count("physics", "absent") == 2
    assert hm.count("chemistry", "contradiction") == 1
    assert hm.row_keys == ("chemistry", "physics")
    assert hm.col_keys == ("absent", "contradiction")


def test_bare_axis_name_resolves_before_id_suffix() -> None:
    # rows="material" reads gap["material"] when present, else gap["material_id"].
    gaps = [
        _gap(material="bare", property_id="P1"),
        _gap(material_id="ided", property_id="P1"),
    ]
    hm = build_heatmap(gaps)
    assert hm.count("bare", "P1") == 1
    assert hm.count("ided", "P1") == 1


def test_as_dict_serializes_cells_sorted() -> None:
    gaps = [
        _gap(material_id="M2", property_id="P1"),
        _gap(material_id="M1", property_id="P1"),
        _gap(material_id="M1", property_id="P1"),
    ]
    payload = build_heatmap(gaps).as_dict()
    assert payload["rows"] == "material"
    assert payload["cols"] == "property"
    assert payload["row_keys"] == ["M1", "M2"]
    assert payload["col_keys"] == ["P1"]
    assert payload["max_count"] == 2
    assert payload["cells"] == [
        {"row": "M1", "col": "P1", "count": 2},
        {"row": "M2", "col": "P1", "count": 1},
    ]
