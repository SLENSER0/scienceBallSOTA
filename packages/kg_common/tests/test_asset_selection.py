"""Tests for asset-selection resolution — тесты выбора ассетов (§9.2)."""

from __future__ import annotations

import pytest

from kg_common.asset_selection import SelectionResult, parse_token, resolve

# A small hand-checkable dependency map — key -> its upstream deps (§9.2).
#   schema_validation <- graph_upsert <- gap_scan
_DEPS: dict[str, list[str]] = {
    "graph_upsert": ["schema_validation"],
    "gap_scan": ["graph_upsert"],
}

# A flat two-asset map used for the plain (no-sigil) selection case (§9.2).
_FLAT: dict[str, list[str]] = {
    "qdrant_indexing": ["graph_upsert"],
    "opensearch_indexing": ["graph_upsert"],
}


def test_parse_trailing_plus_is_downstream() -> None:
    assert parse_token("graph_upsert+") == ("graph_upsert", 0, 1)


def test_parse_leading_plus_is_upstream() -> None:
    assert parse_token("+graph_upsert") == ("graph_upsert", 1, 0)


def test_parse_leading_star_is_unbounded_upstream() -> None:
    assert parse_token("*qdrant_indexing") == ("qdrant_indexing", -1, 0)


def test_parse_repeated_plus_counts_hops() -> None:
    # Two leading '+' -> two upstream hops; the base survives intact.
    assert parse_token("++graph_upsert") == ("graph_upsert", 2, 0)


def test_resolve_plain_tokens_keep_order() -> None:
    result = resolve("qdrant_indexing,opensearch_indexing", _FLAT)
    assert result.keys == ("qdrant_indexing", "opensearch_indexing")


def test_resolve_downstream_pulls_dependents() -> None:
    keys = resolve("graph_upsert+", _DEPS).keys
    assert "graph_upsert" in keys
    assert "gap_scan" in keys


def test_resolve_upstream_pulls_dependencies() -> None:
    keys = resolve("+graph_upsert", _DEPS).keys
    assert "schema_validation" in keys


def test_resolve_star_pulls_full_upstream_chain() -> None:
    keys = resolve("*gap_scan", _DEPS).keys
    # The whole upstream closure of gap_scan is present, in dependency order.
    assert set(keys) == {"gap_scan", "graph_upsert", "schema_validation"}


def test_as_dict_keys_is_a_list() -> None:
    result = resolve("gap_scan", _DEPS)
    payload = result.as_dict()
    assert payload == {"query": "gap_scan", "keys": ["gap_scan"]}
    assert isinstance(payload["keys"], list)


def test_selection_result_is_frozen() -> None:
    result = SelectionResult(query="x", keys=("x",))
    with pytest.raises((AttributeError, TypeError)):
        result.query = "y"  # type: ignore[misc]


def test_unknown_base_key_raises_keyerror() -> None:
    with pytest.raises(KeyError):
        resolve("does_not_exist", _DEPS)


def test_resolve_dedups_across_tokens() -> None:
    # gap_scan's upstream and graph_upsert's own selection overlap on graph_upsert.
    keys = resolve("*gap_scan,+graph_upsert", _DEPS).keys
    assert len(keys) == len(set(keys))
