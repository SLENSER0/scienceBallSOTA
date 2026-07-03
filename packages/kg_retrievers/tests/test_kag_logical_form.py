"""Tests for KAG-style logical-form query decomposition (§11/§12).

Hand-checkable cases over :mod:`kg_retrievers.kag_logical_form`: property /
constraint / comparison / aggregation parsing into an ordered symbolic plan.
"""

from __future__ import annotations

import pytest

from kg_retrievers import kag_logical_form as klf
from kg_retrievers.kag_logical_form import (
    AGGREGATE,
    COMPARE,
    FILTER,
    RETRIEVAL,
    LogicalForm,
    NumericConstraint,
    Op,
    decompose,
)


def _ops_by_type(lf: LogicalForm, op_type: str) -> list[Op]:
    return [op for op in lf.ops if op.op == op_type]


def test_docstring_cites_kag_source() -> None:
    # RULE: module docstring must cite the paper/repo.
    doc = klf.__doc__ or ""
    assert "KAG" in doc
    assert "github.com/OpenSPG/KAG" in doc
    assert "arXiv:2409.13731" in doc


def test_material_property_query_yields_retrieval_op() -> None:
    # "tensile strength of steel" -> a single retrieval op naming the property.
    lf = decompose("tensile strength of steel")
    assert len(lf.ops) == 1
    op = lf.ops[0]
    assert op.op == RETRIEVAL
    assert op.args["properties"] == ["tensile_strength"]
    assert "steel" in op.args["entities"]


def test_numeric_constraint_yields_filter_op() -> None:
    # A comparator constraint -> a filter op carrying operator/value/unit/param.
    lf = decompose("steel with tensile strength greater than 300 MPa")
    filters = _ops_by_type(lf, FILTER)
    assert len(filters) == 1
    args = filters[0].args
    assert args["operator"] == ">"
    assert args["value"] == 300.0
    assert args["unit"] == "MPa"  # original casing preserved
    assert args["parameter"] == "tensile_strength"
    # And it is recorded as a NumericConstraint on the form.
    assert len(lf.constraints) == 1
    assert lf.constraints[0].operator == ">"


def test_range_constraint_yields_range_filter() -> None:
    # "between 300 and 500 HB" -> a range filter with min/max.
    lf = decompose("materials with hardness between 300 and 500 HB")
    filters = _ops_by_type(lf, FILTER)
    assert len(filters) == 1
    args = filters[0].args
    assert args["operator"] == "range"
    assert args["min"] == 300.0
    assert args["max"] == 500.0
    assert args["unit"] == "HB"
    assert args["parameter"] == "hardness"


def test_comparison_query_yields_compare_op() -> None:
    # An explicit "compare ... and ..." -> a compare op over both entities.
    lf = decompose("compare tensile strength of steel and titanium")
    compares = _ops_by_type(lf, COMPARE)
    assert len(compares) == 1
    assert compares[0].args["entities"] == ["steel", "titanium"]
    assert compares[0].args["properties"] == ["tensile_strength"]


def test_aggregation_query_yields_aggregate_op() -> None:
    # "average hardness of steel" -> an aggregate op (avg over hardness).
    lf = decompose("average hardness of steel")
    aggs = _ops_by_type(lf, AGGREGATE)
    assert len(aggs) == 1
    assert aggs[0].args == {"function": "avg", "property": "hardness"}


def test_entities_extracted_without_property_or_stopwords() -> None:
    # Property phrase + stopwords are stripped; only the subjects remain.
    lf = decompose("tensile strength of steel and titanium")
    assert lf.entities == ("steel", "titanium")


def test_empty_query_yields_no_ops() -> None:
    for blank in ("", "   ", "\n\t"):
        lf = decompose(blank)
        assert lf.ops == ()
        assert lf.entities == ()
        assert lf.constraints == ()


def test_ops_ordered_retrieval_filter_compare() -> None:
    # A query needing all three: ops come out in canonical execution order.
    lf = decompose("compare tensile strength of steel and titanium above 300 MPa")
    names = [op.op for op in lf.ops]
    assert names == [RETRIEVAL, FILTER, COMPARE]
    ranks = [klf._OP_RANK[op.op] for op in lf.ops]
    assert ranks == sorted(ranks)


def test_as_dict_shape_and_isolation() -> None:
    lf = decompose("steel with tensile strength greater than 300 MPa")
    d = lf.as_dict()
    assert set(d) == {"ops", "entities", "constraints"}
    assert all(set(op) == {"op", "args"} for op in d["ops"])
    assert d["ops"][0]["op"] == RETRIEVAL
    assert d["constraints"][0]["operator"] == ">"
    # as_dict returns copies: mutating the result does not touch the form.
    d["entities"].append("copper")
    d["ops"][0]["args"]["entities"].append("copper")
    assert "copper" not in lf.entities
    assert "copper" not in lf.ops[0].args["entities"]


def test_logical_form_is_frozen() -> None:
    lf = decompose("steel")
    with pytest.raises(AttributeError):
        lf.entities = ("iron",)  # type: ignore[misc]


def test_numeric_constraint_as_dict_drops_unset_fields() -> None:
    c = NumericConstraint(parameter="hardness", operator=">=", value=90.0, unit="hb")
    d = c.as_dict()
    assert d == {
        "parameter": "hardness",
        "operator": ">=",
        "value": 90.0,
        "unit": "hb",
        "source_span": "",
    }
    assert "min" not in d and "max" not in d


def test_bare_word_after_number_not_treated_as_unit() -> None:
    # "over 300 apples" -> apples is not a unit and stays an entity.
    lf = decompose("steel over 300 apples")
    filters = _ops_by_type(lf, FILTER)
    assert len(filters) == 1
    assert filters[0].args["operator"] == ">"
    assert "unit" not in filters[0].args  # rejected -> dropped by as_dict
    assert "apples" in lf.entities
