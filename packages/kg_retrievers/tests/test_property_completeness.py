"""Per-label required-property fill-rate matrix tests (§3.18/§8).

Hand-checkable graphs built over a fresh temp Kuzu store. Required properties come from
:data:`kg_schema.node_validation.REQUIRED_PROPS` — Measurement needs ``value_normalized``
and ``property_name``; Unit needs ``symbol``; Material declares none.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from kg_retrievers.graph_store import KuzuGraphStore
from kg_retrievers.property_completeness import (
    CompletenessMatrix,
    LabelCompleteness,
    property_completeness,
)


def _store() -> KuzuGraphStore:
    d = tempfile.mkdtemp()
    return KuzuGraphStore(str(Path(d) / "g"))


def test_measurement_half_filled() -> None:
    store = _store()
    # both Measurements carry property_name; only m1 carries value_normalized.
    store.upsert_node("m1", "Measurement", property_name="hardness", value_normalized=3.0)
    store.upsert_node("m2", "Measurement", property_name="hardness")
    matrix = property_completeness(store)
    lc = matrix.by_label["Measurement"]
    assert lc.n_nodes == 2
    assert lc.fill_rate["value_normalized"] == 0.5
    assert lc.fill_rate["property_name"] == 1.0
    assert lc.missing_counts["value_normalized"] == 1
    assert "property_name" not in lc.missing_counts
    assert lc.complete is False


def test_all_required_present_is_complete() -> None:
    store = _store()
    store.upsert_node("m1", "Measurement", property_name="hardness", value_normalized=3.0)
    store.upsert_node("m2", "Measurement", property_name="strength", value_normalized=9.0)
    lc = property_completeness(store).by_label["Measurement"]
    assert lc.fill_rate == {"value_normalized": 1.0, "property_name": 1.0}
    assert lc.missing_counts == {}
    assert lc.complete is True


def test_unit_missing_symbol_zero_fill() -> None:
    store = _store()
    # 'symbol' is a custom prop (not a base column) -> absent entirely from get_node().
    store.upsert_node("u1", "Unit", name="megapascal")
    lc = property_completeness(store).by_label["Unit"]
    assert lc.required == ("symbol",)
    assert lc.fill_rate["symbol"] == 0.0
    assert lc.missing_counts["symbol"] == 1
    assert lc.complete is False


def test_label_without_required_is_complete_and_empty() -> None:
    store = _store()
    store.upsert_node("mat1", "Material", name="steel")
    store.upsert_node("mat2", "Material", name="copper")
    lc = property_completeness(store).by_label["Material"]
    assert lc.required == ()
    assert lc.fill_rate == {}
    assert lc.missing_counts == {}
    assert lc.complete is True


def test_total_nodes_matches_count() -> None:
    store = _store()
    store.upsert_node("m1", "Measurement", property_name="p", value_normalized=1.0)
    store.upsert_node("mat1", "Material", name="steel")
    store.upsert_node("u1", "Unit", symbol="MPa")
    matrix = property_completeness(store)
    assert matrix.total_nodes == 3
    assert matrix.total_nodes == store.counts()["nodes"]


def test_overall_complete_false_when_any_label_incomplete() -> None:
    store = _store()
    # Material is complete (no requirements); Unit missing symbol drags overall down.
    store.upsert_node("mat1", "Material", name="steel")
    store.upsert_node("u1", "Unit", name="pascal")
    matrix = property_completeness(store)
    assert matrix.by_label["Material"].complete is True
    assert matrix.by_label["Unit"].complete is False
    assert matrix.overall_complete is False


def test_overall_complete_true_when_all_labels_complete() -> None:
    store = _store()
    store.upsert_node("mat1", "Material", name="steel")
    store.upsert_node("u1", "Unit", symbol="MPa")
    store.upsert_node("m1", "Measurement", property_name="p", value_normalized=1.0)
    matrix = property_completeness(store)
    assert matrix.overall_complete is True


def test_as_dict_keys_match_observed_labels() -> None:
    store = _store()
    store.upsert_node("m1", "Measurement", property_name="p", value_normalized=1.0)
    store.upsert_node("mat1", "Material", name="steel")
    matrix = property_completeness(store)
    d = matrix.as_dict()
    assert set(d["by_label"].keys()) == {"Measurement", "Material"}
    assert set(d["by_label"].keys()) == set(matrix.by_label.keys())
    assert d["total_nodes"] == 2
    assert d["overall_complete"] is True


def test_types_and_serialisation_shape() -> None:
    store = _store()
    store.upsert_node("u1", "Unit", name="pascal")
    matrix = property_completeness(store)
    assert isinstance(matrix, CompletenessMatrix)
    lc = matrix.by_label["Unit"]
    assert isinstance(lc, LabelCompleteness)
    assert lc.as_dict() == {
        "label": "Unit",
        "n_nodes": 1,
        "required": ["symbol"],
        "fill_rate": {"symbol": 0.0},
        "missing_counts": {"symbol": 1},
        "complete": False,
    }
