"""Tests for per-tag run concurrency limits (§9.7)."""

from __future__ import annotations

import dataclasses

import pytest

from kg_common.tag_concurrency import TagLimit, can_admit, slots_used


def test_slots_used_counts_matching_run() -> None:
    limit = TagLimit("llm", "true", 1)
    assert slots_used([{"llm": "true"}], limit) == 1


def test_can_admit_blocks_when_full() -> None:
    limit = TagLimit("llm", "true", 1)
    assert can_admit({"llm": "true"}, [{"llm": "true"}], [limit]) == (False, ("llm",))


def test_candidate_lacking_tag_is_admitted() -> None:
    limit = TagLimit("llm", "true", 1)
    # In-flight already saturates the pool, but the candidate has no `llm` tag.
    ok, violated = can_admit({"neo4j": "true"}, [{"llm": "true"}], [limit])
    assert ok is True
    assert violated == ()


def test_value_none_counts_each_value_separately() -> None:
    # limit=2 per distinct value: two *different* values don't crowd each other.
    limit = TagLimit("pool", None, 2)
    in_flight = [{"pool": "a"}, {"pool": "b"}]
    # Candidate pool=a shares only the single pool=a run -> 1 + 1 = 2 <= 2.
    ok, violated = can_admit({"pool": "a"}, in_flight, [limit])
    assert ok is True
    assert violated == ()
    # slots_used reports the busiest value's occupancy (here 1 each).
    assert slots_used(in_flight, limit) == 1


def test_value_specific_limit_ignores_other_values() -> None:
    limit = TagLimit("env", "prod", 1)
    # An in-flight run with env=staging is not counted against env=prod.
    assert slots_used([{"env": "staging"}], limit) == 0
    ok, violated = can_admit({"env": "prod"}, [{"env": "staging"}], [limit])
    assert ok is True
    assert violated == ()


def test_empty_limits_always_admit() -> None:
    assert can_admit({"llm": "true"}, [{"llm": "true"}], []) == (True, ())


def test_multiple_violations_all_reported() -> None:
    limits = [TagLimit("llm", "true", 1), TagLimit("neo4j", "true", 1)]
    in_flight = [{"llm": "true", "neo4j": "true"}]
    ok, violated = can_admit({"llm": "true", "neo4j": "true"}, in_flight, limits)
    assert ok is False
    assert set(violated) == {"llm", "neo4j"}


def test_as_dict_and_frozen() -> None:
    limit = TagLimit("llm", "true", 1)
    assert limit.as_dict()["limit"] == 1
    assert limit.as_dict() == {"key": "llm", "value": "true", "limit": 1}
    with pytest.raises(dataclasses.FrozenInstanceError):
        limit.limit = 5  # type: ignore[misc]


def test_value_none_pool_can_saturate() -> None:
    limit = TagLimit("pool", None, 2)
    in_flight = [{"pool": "a"}, {"pool": "a"}]
    assert slots_used(in_flight, limit) == 2
    ok, violated = can_admit({"pool": "a"}, in_flight, [limit])
    assert ok is False
    assert violated == ("pool",)


def test_rejects_bad_construction() -> None:
    with pytest.raises(ValueError):
        TagLimit("", "true", 1)
    with pytest.raises(ValueError):
        TagLimit("llm", "true", -1)
