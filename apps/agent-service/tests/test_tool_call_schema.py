"""Hand-checked tests for §13.6 tool-call schema generation.

Pure-python, no store / no LLM: build :class:`ArgSpec` / :class:`ToolSchema`
directly and assert the exact OpenAI / LangChain function-calling shape produced by
:func:`function_schema`, the ``validate_call`` violation cases (missing required,
unknown key, wrong JSON type, well-typed → no violations) and the ``as_dict`` /
orjson round-trip. Every expected value is spelled out for by-hand verification.
"""

from __future__ import annotations

import orjson
import pytest
from agent_service.tool_call_schema import (
    ArgSpec,
    ToolSchema,
    all_function_schemas,
    function_schema,
    validate_call,
)


def _two_arg_schema() -> ToolSchema:
    """A tool with one required ``string`` arg and one optional ``integer`` arg."""
    return ToolSchema(
        name="graph_search",
        description="Find candidate nodes by term.",
        args=(
            ArgSpec("term", "string", required=True, description="surface term"),
            ArgSpec("limit", "integer", required=False, description="max hits"),
        ),
    )


# ---------------------------------------------------------------------------
# function_schema: OpenAI / LangChain function-calling shape
# ---------------------------------------------------------------------------
def test_function_schema_top_level_shape() -> None:
    fs = function_schema(_two_arg_schema())
    assert fs["name"] == "graph_search"
    assert fs["description"] == "Find candidate nodes by term."
    assert fs["parameters"]["type"] == "object"
    assert set(fs["parameters"]) == {"type", "properties", "required"}


def test_required_lists_exactly_required_names() -> None:
    # Assertion (1): parameters.required lists exactly the required arg names.
    fs = function_schema(_two_arg_schema())
    assert fs["parameters"]["required"] == ["term"]


def test_optional_arg_in_properties_not_required() -> None:
    # Assertion (2): an optional arg appears in properties but not in required.
    fs = function_schema(_two_arg_schema())
    props = fs["parameters"]["properties"]
    assert "limit" in props
    assert "limit" not in fs["parameters"]["required"]
    assert "term" in props  # required arg is also a property


def test_each_property_carries_mapped_json_type() -> None:
    # Assertion (3): each property carries the mapped JSON type string.
    fs = function_schema(_two_arg_schema())
    props = fs["parameters"]["properties"]
    assert props["term"]["type"] == "string"
    assert props["limit"]["type"] == "integer"
    assert props["term"]["description"] == "surface term"


def test_all_json_types_map_through() -> None:
    ts = ToolSchema(
        name="t",
        description="all types",
        args=(
            ArgSpec("s", "string"),
            ArgSpec("i", "integer"),
            ArgSpec("n", "number"),
            ArgSpec("b", "boolean"),
            ArgSpec("a", "array"),
        ),
    )
    props = function_schema(ts)["parameters"]["properties"]
    assert [props[k]["type"] for k in ("s", "i", "n", "b", "a")] == [
        "string",
        "integer",
        "number",
        "boolean",
        "array",
    ]


def test_all_function_schemas_maps_each_tool() -> None:
    a = _two_arg_schema()
    b = ToolSchema(name="gap_check", description="gaps", args=(ArgSpec("domain", "string"),))
    out = all_function_schemas([a, b])
    assert [fs["name"] for fs in out] == ["graph_search", "gap_check"]
    assert out[1]["parameters"]["required"] == ["domain"]


# ---------------------------------------------------------------------------
# validate_call: violations
# ---------------------------------------------------------------------------
def test_validate_well_typed_returns_empty() -> None:
    # Assertion (4): validate_call returns [] for a well-typed dict.
    assert validate_call(_two_arg_schema(), {"term": "membrane", "limit": 5}) == []


def test_validate_missing_required_one_violation() -> None:
    # Assertion (5): a missing required arg yields exactly one violation naming it.
    v = validate_call(_two_arg_schema(), {"limit": 5})
    assert len(v) == 1
    assert "term" in v[0]
    assert "missing required" in v[0]


def test_validate_optional_omitted_is_ok() -> None:
    assert validate_call(_two_arg_schema(), {"term": "membrane"}) == []


def test_validate_unknown_key_violation() -> None:
    # Assertion (6): passing an unknown key yields a violation naming it.
    v = validate_call(_two_arg_schema(), {"term": "membrane", "bogus": 1})
    assert len(v) == 1
    assert "bogus" in v[0]
    assert "unknown arg" in v[0]


def test_validate_wrong_type_violation() -> None:
    # Assertion (7): a string where integer is expected yields a type violation.
    v = validate_call(_two_arg_schema(), {"term": "membrane", "limit": "five"})
    assert len(v) == 1
    assert "limit" in v[0]
    assert "must be integer" in v[0]
    assert "str" in v[0]


def test_validate_bool_is_not_integer() -> None:
    # bool is an int subclass in Python — reject it where integer is expected.
    v = validate_call(_two_arg_schema(), {"term": "membrane", "limit": True})
    assert len(v) == 1
    assert "limit" in v[0]
    assert "must be integer" in v[0]


def test_validate_number_accepts_int_and_float() -> None:
    ts = ToolSchema(name="t", description="d", args=(ArgSpec("x", "number"),))
    assert validate_call(ts, {"x": 3}) == []
    assert validate_call(ts, {"x": 3.5}) == []
    assert validate_call(ts, {"x": "3"}) == ["arg 'x' must be number, got str"]


def test_validate_null_present_arg_is_ok() -> None:
    # A JSON null for a present arg is not a type violation (treated as unsupplied).
    assert validate_call(_two_arg_schema(), {"term": "membrane", "limit": None}) == []


def test_validate_array_type() -> None:
    ts = ToolSchema(name="t", description="d", args=(ArgSpec("ids", "array"),))
    assert validate_call(ts, {"ids": [1, 2]}) == []
    assert validate_call(ts, {"ids": "x"}) == ["arg 'ids' must be array, got str"]


def test_validate_multiple_violations_stable_order() -> None:
    # missing required first, then unknown-key / type in args iteration order.
    v = validate_call(_two_arg_schema(), {"limit": "no", "extra": 1})
    assert v[0] == "missing required arg 'term'"
    assert "must be integer" in v[1]
    assert v[2] == "unknown arg 'extra'"


# ---------------------------------------------------------------------------
# as_dict / orjson round-trip
# ---------------------------------------------------------------------------
def test_argspec_as_dict_shape() -> None:
    d = ArgSpec("term", "string", required=True, description="surface term").as_dict()
    assert d == {
        "name": "term",
        "type": "string",
        "required": True,
        "description": "surface term",
    }


def test_toolschema_as_dict_shape() -> None:
    d = _two_arg_schema().as_dict()
    assert d["name"] == "graph_search"
    assert d["description"] == "Find candidate nodes by term."
    assert d["args"] == [
        {"name": "term", "type": "string", "required": True, "description": "surface term"},
        {"name": "limit", "type": "integer", "required": False, "description": "max hits"},
    ]


def test_argspec_as_dict_orjson_round_trip() -> None:
    # Assertion (8): as_dict round-trips through orjson without loss.
    spec = ArgSpec("limit", "integer", required=False, description="max hits")
    assert orjson.loads(orjson.dumps(spec.as_dict())) == spec.as_dict()


def test_toolschema_as_dict_orjson_round_trip() -> None:
    # Assertion (8): as_dict round-trips through orjson without loss.
    ts = _two_arg_schema()
    assert orjson.loads(orjson.dumps(ts.as_dict())) == ts.as_dict()


def test_function_schema_orjson_round_trip() -> None:
    fs = function_schema(_two_arg_schema())
    assert orjson.loads(orjson.dumps(fs)) == fs


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
