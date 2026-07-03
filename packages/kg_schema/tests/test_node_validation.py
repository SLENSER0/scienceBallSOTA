"""Hand-checked tests for §3.18 node required-property validation.

Required-property expectations below are read straight from
:data:`kg_schema.node_validation.REQUIRED_PROPS`, so every case is hand-verifiable:
Measurement requires ``value_normalized`` + ``property_name``; Evidence requires ``doc_id``.
"""

from __future__ import annotations

from kg_schema.node_validation import (
    REQUIRED_PROPS,
    NodeValidation,
    known_labels,
    missing_fields,
    required_props,
    validate_node,
)


def test_complete_measurement_passes() -> None:
    node = {
        "label": "Measurement",
        "value_normalized": 1180.0,
        "property_name": "yield_strength",
    }
    result = validate_node(node)
    assert isinstance(result, NodeValidation)
    assert result.ok is True
    assert result.label == "Measurement"
    assert result.missing == []
    assert result.errors == []


def test_measurement_missing_value_normalized_is_listed() -> None:
    node = {"label": "Measurement", "property_name": "yield_strength"}
    result = validate_node(node)
    assert result.ok is False
    assert result.missing == ["value_normalized"]
    assert result.errors == []


def test_measurement_missing_both_required_props() -> None:
    # Order follows REQUIRED_PROPS: value_normalized then property_name.
    result = validate_node({"label": "Measurement"})
    assert result.ok is False
    assert result.missing == ["value_normalized", "property_name"]


def test_evidence_missing_doc_id() -> None:
    node = {"label": "Evidence", "text": "as measured in Table 2"}
    result = validate_node(node)
    assert result.ok is False
    assert result.missing == ["doc_id"]
    # A complete Evidence (doc_id present) passes.
    assert validate_node({"label": "Evidence", "doc_id": "doc-42"}).ok is True


def test_unknown_label_has_no_constraints() -> None:
    # A label with no declared required props validates as ok (nothing is required).
    result = validate_node({"label": "Banana"})
    assert result.ok is True
    assert result.label == "Banana"
    assert result.missing == []
    assert result.errors == []


def test_node_without_label_is_structural_error() -> None:
    result = validate_node({"value_normalized": 1.0})
    assert result.ok is False
    assert result.label is None
    assert result.missing == []
    assert result.errors == ["node has no 'label'"]


def test_missing_fields_helper() -> None:
    assert missing_fields({"label": "Measurement", "property_name": "hardness"}) == [
        "value_normalized"
    ]
    # Complete node → no missing fields.
    complete = {"label": "Measurement", "value_normalized": 5, "property_name": "hardness"}
    assert missing_fields(complete) == []
    # No label / unknown label → nothing required.
    assert missing_fields({}) == []
    assert missing_fields({"label": "Banana"}) == []


def test_blank_string_counts_as_missing() -> None:
    # A blank / whitespace-only string is treated as absent (§3.18).
    node = {"label": "Evidence", "doc_id": "   "}
    assert missing_fields(node) == ["doc_id"]
    assert validate_node(node).ok is False


def test_none_value_counts_as_missing() -> None:
    node = {"label": "Measurement", "value_normalized": None, "property_name": "x"}
    assert missing_fields(node) == ["value_normalized"]


def test_labels_list_form_is_tolerated() -> None:
    # Node may carry a `labels` list instead of a scalar `label`.
    node = {"labels": ["Evidence"], "doc_id": "doc-7"}
    result = validate_node(node)
    assert result.label == "Evidence"
    assert result.ok is True


def test_as_dict_shape() -> None:
    result = validate_node({"label": "Measurement", "property_name": "hardness"})
    assert result.as_dict() == {
        "ok": False,
        "label": "Measurement",
        "missing": ["value_normalized"],
        "errors": [],
    }
    # as_dict copies lists — mutating the copy must not touch the frozen result.
    d = result.as_dict()
    d["missing"].append("bogus")
    assert result.missing == ["value_normalized"]


def test_required_props_and_known_labels() -> None:
    assert required_props("Measurement") == ("value_normalized", "property_name")
    assert required_props("Evidence") == ("doc_id",)
    assert required_props("Banana") == ()
    assert required_props(None) == ()
    assert "Measurement" in known_labels()
    assert "Evidence" in known_labels()
    assert REQUIRED_PROPS["Evidence"] == ("doc_id",)
