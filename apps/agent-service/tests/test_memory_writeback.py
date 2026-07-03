"""Tests for §13.20 long-term Store writeback derivation / memory_writeback."""

from __future__ import annotations

import pytest
from agent_service.memory_writeback import (
    MemoryWrite,
    collect_writes,
    from_confirmed_entities,
    from_filter_history,
)


def test_entity_above_threshold_yields_entity_alias() -> None:
    """(1) confidence 0.9 → one entity_alias write with value==canonical_id."""
    entities = [{"mention": "Асп", "canonical_id": "CHEBI:1", "confidence": 0.9}]
    writes = from_confirmed_entities(entities, threshold=0.8)
    assert len(writes) == 1
    w = writes[0]
    assert w.kind == "entity_alias"
    assert w.key == "alias:Асп"
    assert w.value == "CHEBI:1"
    assert w.confidence == 0.9


def test_entity_below_threshold_is_skipped() -> None:
    """(2) confidence 0.5 below threshold 0.8 is skipped."""
    entities = [{"mention": "x", "canonical_id": "CHEBI:2", "confidence": 0.5}]
    assert from_confirmed_entities(entities, threshold=0.8) == []


def test_filter_seen_three_of_five_yields_preferred_filter() -> None:
    """(3) a filter appearing 3 of 5 times → preferred_filter, confidence 0.6."""
    a = {"field": "year", "op": ">=", "val": 2020}
    b = {"field": "kind", "op": "=", "val": "paper"}
    history = [a, a, a, b, b]
    writes = from_filter_history(history, min_count=2)
    # b appears twice (>= min_count) too, so filter for a must be present with 0.6.
    a_writes = [w for w in writes if w.value == a]
    assert len(a_writes) == 1
    w = a_writes[0]
    assert w.kind == "preferred_filter"
    assert w.confidence == pytest.approx(0.6)


def test_filter_seen_once_below_min_count_is_skipped() -> None:
    """(4) a filter appearing once with min_count 2 is skipped."""
    history = [{"field": "year", "op": "=", "val": 2021}]
    assert from_filter_history(history, min_count=2) == []


def test_invalid_kind_raises_value_error() -> None:
    """(5) constructing MemoryWrite with kind='foo' raises ValueError."""
    with pytest.raises(ValueError):
        MemoryWrite(key="k", value="v", kind="foo", confidence=1.0)


def test_collect_writes_empty_state_returns_empty() -> None:
    """(6) collect_writes on an empty state returns []."""
    assert collect_writes({}) == []


def test_as_dict_round_trips_fields() -> None:
    """(7) as_dict round-trips key/value/kind/confidence."""
    w = MemoryWrite(key="alias:Asp", value="CHEBI:1", kind="entity_alias", confidence=0.9)
    d = w.as_dict()
    assert d == {
        "key": "alias:Asp",
        "value": "CHEBI:1",
        "kind": "entity_alias",
        "confidence": 0.9,
    }
    w2 = MemoryWrite(**{k: d[k] for k in ("key", "value", "kind", "confidence")})
    assert w2 == w


def test_collect_writes_combines_both_sources() -> None:
    """collect_writes merges entity_alias and preferred_filter candidates in order."""
    f = {"field": "year", "op": ">=", "val": 2020}
    state = {
        "confirmed_entities": [
            {"mention": "Asp", "canonical_id": "CHEBI:1", "confidence": 0.95},
            {"mention": "lo", "canonical_id": "CHEBI:9", "confidence": 0.2},
        ],
        "filter_history": [f, f, {"field": "kind", "op": "=", "val": "paper"}],
    }
    writes = collect_writes(state, threshold=0.8)
    kinds = [w.kind for w in writes]
    assert kinds == ["entity_alias", "preferred_filter"]
    assert writes[0].value == "CHEBI:1"
    assert writes[1].confidence == pytest.approx(2 / 3)
