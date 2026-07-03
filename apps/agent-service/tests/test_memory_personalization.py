"""Tests for §13.20 personalization read (memory_personalization)."""

from __future__ import annotations

from agent_service.memory_personalization import (
    PersonalizedQuery,
    apply_aliases,
    inject_default_filters,
    personalize,
)


def test_apply_aliases_replaces_present_and_keeps_absent() -> None:
    """(1) present mention → canonical id; absent mention unchanged."""
    out = apply_aliases(["p53", "BRCA1"], {"p53": "HGNC:11998"})
    assert out == ["HGNC:11998", "BRCA1"]


def test_inject_default_filters_does_not_override_existing_key() -> None:
    """(2) an existing key is never overridden by a default."""
    out = inject_default_filters({"organism": "human"}, {"organism": "mouse"})
    assert out == {"organism": "human"}


def test_inject_default_filters_adds_missing_key() -> None:
    """(3) a missing key is added from defaults."""
    out = inject_default_filters({"organism": "human"}, {"year": 2024})
    assert out == {"organism": "human", "year": 2024}


def test_personalize_records_alias_when_substituted() -> None:
    """(4) 'alias' in applied when an alias was substituted."""
    memory = [{"kind": "entity_alias", "mention": "p53", "canonical": "HGNC:11998"}]
    result = personalize(["p53"], {}, memory)
    assert result.mentions == ("HGNC:11998",)
    assert "alias" in result.applied


def test_personalize_records_filter_when_default_injected() -> None:
    """(5) 'filter' in applied when a default filter was injected."""
    memory = [{"kind": "preferred_filter", "key": "organism", "value": "human"}]
    result = personalize([], {}, memory)
    assert result.filters == {"organism": "human"}
    assert "filter" in result.applied


def test_personalize_empty_memory_is_identity() -> None:
    """(6) empty memory leaves mentions/filters unchanged with empty applied."""
    result = personalize(["p53"], {"organism": "human"}, [])
    assert result.mentions == ("p53",)
    assert result.filters == {"organism": "human"}
    assert result.applied == ()


def test_as_dict_filters_is_distinct_object() -> None:
    """(7) as_dict()['filters'] is a distinct object from the input filters dict."""
    src = {"organism": "human"}
    pq = PersonalizedQuery(mentions=("p53",), filters=src, applied=())
    out = pq.as_dict()
    assert out["filters"] == src
    assert out["filters"] is not src
    out["filters"]["organism"] = "mouse"
    assert src["organism"] == "human"


def test_personalize_filter_not_applied_when_key_exists() -> None:
    """A preferred_filter whose key already exists does not count as applied."""
    memory = [{"kind": "preferred_filter", "key": "organism", "value": "mouse"}]
    result = personalize([], {"organism": "human"}, memory)
    assert result.filters == {"organism": "human"}
    assert "filter" not in result.applied
