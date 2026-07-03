"""Тесты цепочки происхождения слияний — merge/split lineage walk (§16.6/§16.7)."""

from __future__ import annotations

import pytest

from kg_common.storage.merge_provenance import (
    ProvenanceChain,
    build_chain,
    resolve_canonical,
)


def _linear() -> dict[str, dict[str, object]]:
    # a -> b -> c, with c the canonical (live) head.
    return {
        "a": {"id": "a", "superseded_by": "b"},
        "b": {"id": "b", "superseded_by": "c"},
        "c": {"id": "c"},
    }


def test_resolve_canonical_follows_to_head() -> None:
    assert resolve_canonical("a", _linear()) == "c"


def test_build_chain_ancestors_and_head() -> None:
    chain = build_chain("a", _linear())
    assert chain.ancestors == ("a", "b")
    assert chain.canonical_id == "c"
    assert chain.depth == 2


def test_canonical_node_resolves_to_itself() -> None:
    chain = build_chain("c", _linear())
    assert chain.canonical_id == "c"
    assert chain.depth == 0
    assert chain.ancestors == ()
    assert resolve_canonical("c", _linear()) == "c"


def test_superseded_by_list_follows_first_element() -> None:
    nodes = {
        "a": {"id": "a", "superseded_by": ["x", "y"]},
        "x": {"id": "x"},
        "y": {"id": "y"},
    }
    assert resolve_canonical("a", nodes) == "x"
    assert build_chain("a", nodes).ancestors == ("a",)


def test_cycle_raises_value_error() -> None:
    nodes = {
        "a": {"id": "a", "superseded_by": "b"},
        "b": {"id": "b", "superseded_by": "a"},
    }
    with pytest.raises(ValueError):
        resolve_canonical("a", nodes)
    with pytest.raises(ValueError):
        build_chain("a", nodes)


def test_missing_intermediate_raises_key_error() -> None:
    nodes = {"a": {"id": "a", "superseded_by": "gone"}}
    with pytest.raises(KeyError):
        resolve_canonical("a", nodes)
    with pytest.raises(KeyError):
        build_chain("a", nodes)


def test_as_dict_exposes_canonical_id() -> None:
    d = build_chain("a", _linear()).as_dict()
    assert d["canonical_id"] == "c"
    assert d["ancestors"] == ["a", "b"]
    assert d["depth"] == 2
    assert d["entity_id"] == "a"


def test_empty_list_superseded_by_is_canonical() -> None:
    nodes = {"a": {"id": "a", "superseded_by": []}}
    chain = build_chain("a", nodes)
    assert chain.canonical_id == "a"
    assert chain.depth == 0


def test_none_superseded_by_is_canonical() -> None:
    nodes = {"a": {"id": "a", "superseded_by": None}}
    assert resolve_canonical("a", nodes) == "a"


def test_chain_is_frozen() -> None:
    chain = ProvenanceChain("a", "c", ("a", "b"), 2)
    with pytest.raises((AttributeError, TypeError)):
        chain.canonical_id = "z"  # type: ignore[misc]


def test_depth_equals_len_ancestors() -> None:
    chain = build_chain("a", _linear())
    assert chain.depth == len(chain.ancestors)
