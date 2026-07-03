"""Tests for §14.6/§5.3 graph ``queryContext`` transparency builder."""

from __future__ import annotations

import dataclasses

import pytest
from api_gateway.query_context import QueryContext, build_query_context


def test_as_dict_keys_are_exact_wire_form() -> None:
    # (1) as_dict() keys are exactly the §5.3 camelCase trio.
    ctx = build_query_context("q", {"a": 1}, "MATCH (n) RETURN n")
    assert set(ctx.as_dict()) == {"userQuery", "filters", "generatedCypher"}


def test_none_and_empty_filter_values_dropped() -> None:
    # (2) None-valued filters vanish; meaningful ones survive.
    ctx = build_query_context("q", {"min_confidence": None, "verified_only": True}, None)
    assert ctx.as_dict()["filters"] == {"verified_only": True}


def test_multiline_cypher_collapsed_to_single_spaces() -> None:
    # (3) newlines + runs of whitespace collapse to single spaces, trimmed.
    ctx = build_query_context("q", None, "MATCH (n)\n  RETURN n")
    assert ctx.as_dict()["generatedCypher"] == "MATCH (n) RETURN n"


def test_none_cypher_becomes_empty_string() -> None:
    # (4) None cypher coerces to ''.
    ctx = build_query_context("q", None, None)
    assert ctx.as_dict()["generatedCypher"] == ""


def test_user_query_preserved_verbatim() -> None:
    # (5) punctuation and spacing in the user query are untouched.
    raw = "What proteins interact with p53? (top-5, verified!)"
    ctx = build_query_context(raw, None, None)
    assert ctx.as_dict()["userQuery"] == raw


def test_none_filters_becomes_empty_dict() -> None:
    # (6) filters=None → {}.
    ctx = build_query_context("q", None, "RETURN 1")
    assert ctx.as_dict()["filters"] == {}


def test_query_context_is_frozen() -> None:
    # (7) reassigning a field on the frozen dataclass raises.
    ctx = build_query_context("q", None, None)
    with pytest.raises(dataclasses.FrozenInstanceError):
        ctx.user_query = "hacked"  # type: ignore[misc]


def test_falsy_but_meaningful_filters_kept() -> None:
    # False / 0 are meaningful and must not be dropped as "empty".
    ctx = build_query_context("q", {"verified_only": False, "limit": 0}, None)
    assert ctx.as_dict()["filters"] == {"verified_only": False, "limit": 0}


def test_empty_string_filter_dropped() -> None:
    # Empty string is droppable like None.
    ctx = build_query_context("q", {"label": "", "kind": "gene"}, None)
    assert ctx.as_dict()["filters"] == {"kind": "gene"}


def test_as_dict_filters_is_a_plain_dict_copy() -> None:
    # Wire form must be a mutable plain dict, not the internal read-only view.
    ctx = build_query_context("q", {"kind": "gene"}, None)
    filters = ctx.as_dict()["filters"]
    assert type(filters) is dict
    filters["extra"] = 1  # mutating the copy must not touch the context
    assert ctx.as_dict()["filters"] == {"kind": "gene"}


def test_whitespace_only_cypher_becomes_empty() -> None:
    ctx = build_query_context("q", None, "   \n\t  ")
    assert ctx.as_dict()["generatedCypher"] == ""


def test_direct_construction_matches_wire_form() -> None:
    ctx = QueryContext(user_query="q", filters={"a": 1}, generated_cypher="RETURN 1")
    assert ctx.as_dict() == {
        "userQuery": "q",
        "filters": {"a": 1},
        "generatedCypher": "RETURN 1",
    }
