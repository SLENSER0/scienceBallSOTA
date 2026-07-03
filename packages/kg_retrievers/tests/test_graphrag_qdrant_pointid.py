"""Tests for deterministic Qdrant point-id planning (§11.5).

Проверяем (we verify): id stability and level-sensitivity, idempotent collapse of
duplicate tuples, and that re-running :func:`plan_upsert` with produced ids is a
no-op second run.
"""

from __future__ import annotations

import hashlib

from kg_retrievers.graphrag_qdrant_pointid import (
    UpsertPlan,
    plan_upsert,
    point_id,
)

_HEX = set("0123456789abcdef")


def _is_sha256_hex(value: str) -> bool:
    return len(value) == 64 and all(ch in _HEX for ch in value)


def test_point_id_is_sha256_hex() -> None:
    pid = point_id("build-1", "c-42", 0)
    assert _is_sha256_hex(pid)


def test_point_id_matches_expected_digest() -> None:
    material = "build-1\x1fc-42\x1f0"
    expected = hashlib.sha256(material.encode("utf-8")).hexdigest()
    assert point_id("build-1", "c-42", 0) == expected


def test_point_id_stable_across_calls() -> None:
    a = point_id("build-1", "c-42", 2)
    b = point_id("build-1", "c-42", 2)
    assert a == b


def test_point_id_differs_when_level_changes() -> None:
    lvl0 = point_id("build-1", "c-42", 0)
    lvl1 = point_id("build-1", "c-42", 1)
    assert lvl0 != lvl1


def test_point_id_differs_when_community_changes() -> None:
    assert point_id("build-1", "c-1", 0) != point_id("build-1", "c-2", 0)


def test_point_id_differs_when_build_changes() -> None:
    assert point_id("build-1", "c-1", 0) != point_id("build-2", "c-1", 0)


def test_no_separator_ambiguity() -> None:
    # ("a|", "b", 0) must not alias ("a", "|b", 0) — separator is unambiguous.
    assert point_id("a|", "b", 0) != point_id("a", "|b", 0)


def test_plan_upsert_empty_existing_puts_all_in_to_upsert() -> None:
    reports = [
        {"community_id": "c-1", "level": 0},
        {"community_id": "c-2", "level": 0},
        {"community_id": "c-1", "level": 1},
    ]
    plan = plan_upsert("build-1", reports, existing_ids=set())
    assert plan.skipped == []
    assert plan.total == 3
    assert len(plan.to_upsert) == 3
    expected = [
        point_id("build-1", "c-1", 0),
        point_id("build-1", "c-2", 0),
        point_id("build-1", "c-1", 1),
    ]
    assert plan.to_upsert == expected


def test_plan_upsert_idempotent_second_run() -> None:
    reports = [
        {"community_id": "c-1", "level": 0},
        {"community_id": "c-2", "level": 0},
    ]
    first = plan_upsert("build-1", reports, existing_ids=set())
    existing = set(first.to_upsert)
    second = plan_upsert("build-1", reports, existing_ids=existing)
    assert second.to_upsert == []
    assert set(second.skipped) == existing
    assert second.total == 2


def test_plan_upsert_duplicate_reports_collapse_to_one_id() -> None:
    # Same (build_id, community_id, level) three times -> one point id.
    reports = [
        {"community_id": "c-1", "level": 0},
        {"community_id": "c-1", "level": 0},
        {"community_id": "c-1", "level": 0},
    ]
    plan = plan_upsert("build-1", reports, existing_ids=set())
    assert plan.to_upsert == [point_id("build-1", "c-1", 0)]
    assert plan.skipped == []
    assert plan.total == 3  # total counts input reports, not unique ids


def test_plan_upsert_skipped_contains_only_preexisting() -> None:
    reports = [
        {"community_id": "c-1", "level": 0},
        {"community_id": "c-2", "level": 0},
        {"community_id": "c-3", "level": 0},
    ]
    preexisting = point_id("build-1", "c-2", 0)
    plan = plan_upsert("build-1", reports, existing_ids={preexisting})
    assert plan.skipped == [preexisting]
    assert preexisting not in plan.to_upsert
    assert plan.to_upsert == [
        point_id("build-1", "c-1", 0),
        point_id("build-1", "c-3", 0),
    ]
    assert plan.total == 3


def test_plan_upsert_total_equals_len_reports() -> None:
    reports = [{"community_id": f"c-{i}", "level": 0} for i in range(5)]
    plan = plan_upsert("build-1", reports, existing_ids=set())
    assert plan.total == len(reports) == 5


def test_as_dict_to_upsert_is_list_of_hex_strings() -> None:
    reports = [
        {"community_id": "c-1", "level": 0},
        {"community_id": "c-2", "level": 3},
    ]
    plan = plan_upsert("build-1", reports, existing_ids=set())
    d = plan.as_dict()
    assert isinstance(d["to_upsert"], list)
    assert all(isinstance(x, str) and _is_sha256_hex(x) for x in d["to_upsert"])
    assert d["skipped"] == []
    assert d["total"] == 2


def test_as_dict_is_a_plain_copy() -> None:
    plan = UpsertPlan(to_upsert=["a" * 64], skipped=[], total=1)
    d = plan.as_dict()
    d["to_upsert"].append("mutated")
    assert plan.to_upsert == ["a" * 64]  # frozen list not aliased


def test_empty_reports_yields_empty_plan() -> None:
    plan = plan_upsert("build-1", [], existing_ids=set())
    assert plan.to_upsert == []
    assert plan.skipped == []
    assert plan.total == 0
